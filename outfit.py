"""Daily outdoor-school outfit: fetch Kingston NY weather, pick gear, write page, push via ntfy."""
import datetime as dt
import html
import json
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
LAT, LON = 41.927, -73.997  # Kingston, NY
SCHOOL_HOURS = range(8, 17)  # 8am–4pm hourly readings cover 8:30–4:30
FULL_WEEK_START = dt.date(2027, 1, 4)  # before this: Mon/Wed/Fri only
PAGE_URL = os.environ.get("PAGE_URL", "")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

WMO = {0: ("☀️", "Sunny"), 1: ("🌤️", "Mostly sunny"), 2: ("⛅", "Partly cloudy"), 3: ("☁️", "Cloudy"),
       45: ("🌫️", "Fog"), 48: ("🌫️", "Fog"), 51: ("🌦️", "Drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌧️", "Drizzle"),
       56: ("🧊", "Freezing drizzle"), 57: ("🧊", "Freezing drizzle"), 61: ("🌧️", "Light rain"), 63: ("🌧️", "Rain"),
       65: ("🌧️", "Heavy rain"), 66: ("🧊", "Freezing rain"), 67: ("🧊", "Freezing rain"), 71: ("🌨️", "Light snow"),
       73: ("🌨️", "Snow"), 75: ("❄️", "Heavy snow"), 77: ("🌨️", "Snow grains"), 80: ("🌦️", "Showers"),
       81: ("🌧️", "Showers"), 82: ("⛈️", "Heavy showers"), 85: ("🌨️", "Snow showers"), 86: ("❄️", "Snow showers"),
       95: ("⛈️", "Thunderstorms"), 96: ("⛈️", "Thunderstorms"), 99: ("⛈️", "Thunderstorms")}


def is_school_day(d):
    days = {0, 1, 2, 3, 4} if d >= FULL_WEEK_START else {0, 2, 4}
    return d.weekday() in days


def fetch(today):
    q = ("https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&timezone=America%2FNew_York"
         "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&past_days=1&forecast_days=1"
         "&hourly=temperature_2m,apparent_temperature,precipitation_probability,precipitation,snowfall,"
         "snow_depth,weather_code,wind_speed_10m").format(LAT, LON)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(q, timeout=30) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(20 * (attempt + 1))


def summarize(data, today):
    h = data["hourly"]
    rows, yesterday_rain = [], 0.0
    for i, t in enumerate(h["time"]):
        ts = dt.datetime.fromisoformat(t)
        if ts.date() < today:
            yesterday_rain += h["precipitation"][i] or 0
        elif ts.date() == today and ts.hour in SCHOOL_HOURS:
            rows.append({k: h[k][i] for k in h if k != "time"} | {"hour": ts.hour})
    feels = [r["apparent_temperature"] for r in rows]
    core = [r["apparent_temperature"] for r in rows if r["hour"] >= 9]  # dress for drop-off onward
    temps = [r["temperature_2m"] for r in rows]
    wet_hours = [r["hour"] for r in rows if (r["precipitation_probability"] or 0) >= 50 or (r["precipitation"] or 0) >= 0.02]
    snowing = any((r["snowfall"] or 0) > 0 for r in rows)
    snow_ground = max((r["snow_depth"] or 0) for r in rows) * 12 >= 1  # feet → inches
    codes = [r["weather_code"] or 0 for r in rows]
    worst = max(codes) if max(codes) >= 45 else max(set(codes), key=codes.count)
    return {
        "rows": rows, "lo": round(min(temps)), "hi": round(max(temps)),
        "flo": round(min(core)), "fhi": round(max(feels)),
        "am": round(sum(feels[:3]) / 3), "pm": round(sum(feels[-3:]) / 3),
        "wet": bool(wet_hours), "wet_hours": wet_hours, "snowing": snowing, "snow_ground": snow_ground,
        "muddy": bool(wet_hours) or yesterday_rain >= 0.2, "yesterday_rain": yesterday_rain,
        "wind": round(max(r["wind_speed_10m"] for r in rows)), "code": worst,
        "rain_pct": max((r["precipitation_probability"] or 0) for r in rows),
    }


def pick(w):
    L, wet, snow = w["flo"], w["wet"], w["snowing"] or w["snow_ground"]
    o = {}
    # Base
    if L < 40 or (wet and L < 48):
        o["Base"] = ["Merino long-sleeve top", "Merino bottoms"]
    elif L < 55:
        o["Base"] = ["Cotton long-sleeve tee", "Thermo leggings"]
    elif L < 68:
        o["Base"] = ["Cotton long-sleeve tee", "Cotton leggings"]
    else:
        o["Base"] = ["Cotton tee", "Cotton leggings"]
    o["Base"].append("Wool socks" if L < 55 or wet else "Cotton socks")
    # Outer and mid
    if snow or L < 28:
        o["Outer"] = ["Reima snowsuit"]
        o["Mid"] = ["Joha wool suit"] if L < 15 else ["Joha wool pants", "Cotton turtleneck"]
    elif wet:
        o["Outer"] = ["Wheat rain jacket", "Wheat rain pants"]
        if L < 38:
            o["Mid"] = ["Joha wool suit"]
        elif L < 50:
            o["Mid"] = ["Kuling wind fleece", "Joha wool pants"]
        elif L < 60:
            o["Mid"] = ["Kuling wind fleece"]
    elif L < 45:
        o["Outer"] = ["Wheat thermo jacket", "Wheat thermo pants"]
        if L < 35:
            o["Mid"] = ["Joha wool pants", "Cotton turtleneck"]
    elif L < 58:
        o["Outer"] = ["Kuling wind fleece"]
    else:
        o["Outer"] = ["None needed (fleece in bag)"]
    # Feet
    if snow or L < 25:
        o["Feet"] = ["Reima winter boots"]
    elif w["muddy"] and L < 40:
        o["Feet"] = ["Mikk-line fur-lined rubber boots"]
    elif w["muddy"] and L < 70:
        o["Feet"] = ["Kuling Viken rain boots"]
    elif w["muddy"]:
        o["Feet"] = ["Keen sandals"]
    elif L < 40:
        o["Feet"] = ["Bisgaard wool-lined boots"]
    elif L < 55:
        o["Feet"] = ["Lofoten waterproof boot sneakers"]
    elif L < 70:
        o["Feet"] = ["New Balance sneakers"]
    else:
        o["Feet"] = ["Keen sandals"]
    # Head and neck
    if L < 20:
        o["Head"] = ["Joha thick wool balaclava"]
    elif L < 32:
        o["Head"] = ["Joha merino balaclava"]
        if w["wind"] >= 12:
            o["Head"].append("Kuling sherpa neck gaiter")
    elif wet and L >= 40:
        o["Head"] = ["Kuling rain hat"]
    elif L < 48:
        o["Head"] = ["Reima wool beanie"]
        if L < 40 or w["wind"] >= 15:
            o["Head"].append("Wool neck gaiter")
    elif L < 58:
        o["Head"] = ["Light beanie"]
    # Hands
    if L < 20:
        o["Hands"] = ["Kuling shell mittens", "Wool stretch gloves underneath"]
    elif L < 32:
        o["Hands"] = ["Kuling shell mittens"] if (wet or snow) else ["Boiled wool mittens on string"]
    elif L < 45:
        o["Hands"] = ["Kuling shell mittens", "Cotton stretch mittens underneath"] if wet else ["Joha merino mittens on string"]
    elif L < 55:
        o["Hands"] = ["Wool stretch gloves"]
    # Spare bag
    bag = ["Full change: long-sleeve tee, leggings, underwear", "Extra socks"]
    if wet or snow:
        bag += ["2nd pair of wool socks", "Spare dry mittens", "Spare merino base layer"]
    elif L < 40:
        bag += ["Spare dry mittens"]
    if w["fhi"] - L >= 15:
        bag.append("Lighter hat/gloves for the afternoon")
    o["Spare bag"] = bag
    return o


def notes(w):
    n = []
    if w["pm"] - w["am"] >= 12:
        n.append(f"Warms up a lot: feels {w['am']}° at drop-off, {w['pm']}° by pick-up. Easy-off layers.")
    elif w["am"] - w["pm"] >= 10:
        n.append(f"Cools down: feels {w['am']}° at drop-off, {w['pm']}° by pick-up.")
    if w["wet"]:
        hrs = w["wet_hours"]
        n.append(f"Rain likely {fmt_h(hrs[0])}–{fmt_h(hrs[-1] + 1)} ({w['rain_pct']}%).")
    elif w["yesterday_rain"] >= 0.2:
        n.append(f"Dry today, but {w['yesterday_rain']:.1f}\" fell yesterday, so expect mud.")
    if w["wind"] >= 15:
        n.append(f"Windy, gusting to {w['wind']} mph. Cover his neck.")
    return n


def fmt_h(h):
    return f"{(h - 1) % 12 + 1}{'a' if h < 12 else 'p'}"


def push_text(w, o, today):
    icon, desc = WMO.get(w["code"], ("🌡️", ""))
    title = f"{icon} {today:%a}: {w['lo']}→{w['hi']}°F, {desc.lower()}"
    key = [o["Outer"][0]] + ([o["Mid"][0]] if "Mid" in o else []) + [o["Feet"][0]]
    body = " · ".join(x for x in key if not x.startswith("None"))
    if w["wet"]:
        body += " · Extra socks + mittens"
    return title, body


def render(w, o, today):
    icon, desc = WMO.get(w["code"], ("🌡️", ""))
    tmin, tmax = min(r["temperature_2m"] for r in w["rows"]), max(r["temperature_2m"] for r in w["rows"])
    span = max(tmax - tmin, 1)
    hours = "".join(
        f'<div class="hr"><span class="t">{round(r["temperature_2m"])}°</span>'
        f'<div class="bar" style="--h:{25 + 75 * (r["temperature_2m"] - tmin) / span:.0f}%"></div>'
        f'<span class="ic">{WMO.get(r["weather_code"], ("·",))[0]}</span>'
        f'<span class="p">{r["precipitation_probability"] or 0}%</span><span class="lab">{fmt_h(r["hour"])}</span></div>'
        for r in w["rows"])
    emoji = {"Base": "👕", "Mid": "🧶", "Outer": "🧥", "Head": "🧢", "Hands": "🧤", "Feet": "🥾", "Spare bag": "🎒"}
    order = ["Outer", "Mid", "Base", "Head", "Hands", "Feet", "Spare bag"]
    cards = "".join(
        f'<div class="card{" bag" if k == "Spare bag" else ""}"><div class="k">{emoji[k]} {k}</div>'
        f'<ul>{"".join(f"<li>{html.escape(x)}</li>" for x in o[k])}</ul></div>'
        for k in order if k in o)
    note = "".join(f"<li>{html.escape(x)}</li>" for x in notes(w))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Today's Outfit</title>
<style>
:root{{--bg:#f7f3ec;--fg:#2a2622;--mut:#7a7068;--card:#fff;--acc:#d9822b;--bar:#f0b77a;--line:#e8e0d4}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1a18;--fg:#f2ede6;--mut:#a59b91;--card:#272421;--acc:#f0a050;--bar:#a8682c;--line:#3a3530}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 -apple-system,system-ui,sans-serif}}
main{{max-width:560px;margin:0 auto;padding:20px 16px 40px}}
.date{{color:var(--mut);font-size:14px;text-transform:uppercase;letter-spacing:.06em}}
.hero{{display:flex;align-items:center;gap:16px;margin:6px 0 4px}}.big{{font-size:64px;line-height:1}}
.temp{{font-size:44px;font-weight:700;letter-spacing:-.02em}}.desc{{color:var(--mut)}}
.feels{{font-size:15px;color:var(--mut);margin-bottom:12px}}
.notes{{margin:0 0 16px;padding:10px 14px 10px 30px;background:var(--card);border-left:4px solid var(--acc);border-radius:8px}}
.hours{{display:flex;gap:4px;background:var(--card);border-radius:14px;padding:12px 8px;margin-bottom:18px}}
.hr{{flex:1;display:flex;flex-direction:column;align-items:center;font-size:12px;gap:3px;min-width:0}}
.hr .t{{font-weight:600;font-size:13px}}.bar{{width:10px;height:48px;display:flex;align-items:flex-end}}
.bar::after{{content:"";width:100%;height:var(--h);background:var(--bar);border-radius:5px}}
.hr .p,.hr .lab{{color:var(--mut)}}h2{{font-size:18px;margin:0 0 10px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.card{{background:var(--card);border-radius:14px;padding:12px 14px}}.card.bag{{grid-column:1/-1}}
.k{{font-size:13px;font-weight:700;color:var(--acc);text-transform:uppercase;letter-spacing:.05em}}
ul{{margin:6px 0 0;padding-left:18px}}li{{margin:2px 0}}
</style></head><body><main>
<div class="date">{today:%A, %B %-d} · Kingston</div>
<div class="hero"><div class="big">{icon}</div><div><div class="temp">{w['lo']}° → {w['hi']}°</div><div class="desc">{desc}</div></div></div>
<div class="feels">Feels like {w['flo']}°–{w['fhi']}° · wind up to {w['wind']} mph</div>
{f'<ul class="notes">{note}</ul>' if note else ''}
<div class="hours">{hours}</div>
<h2>What to wear</h2><div class="grid">{cards}</div>
</main></body></html>"""


def push(title, body):
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}", data=body.encode(), method="POST",
                                 headers={"Title": title.encode(), "Tags": "school", "Click": PAGE_URL})
    urllib.request.urlopen(req, timeout=30)


def main():
    now = dt.datetime.now(TZ)
    if "--send" in sys.argv:  # second step, after the page is deployed
        title, body = json.load(open("push.json"))
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now < target:
            time.sleep((target - now).total_seconds())
        push(title, body)
        return
    today = now.date()
    sample = "--sample" in sys.argv
    if not (is_school_day(today) or sample or "--force" in sys.argv):
        print("Not a school day")
        return
    data = json.load(open(sys.argv[sys.argv.index("--sample") + 1])) if sample else fetch(today)
    if sample:
        today = dt.date.fromisoformat(data["hourly"]["time"][-1][:10])
    w = summarize(data, today)
    o = pick(w)
    os.makedirs("site", exist_ok=True)
    open("site/index.html", "w").write(render(w, o, today))
    title, body = push_text(w, o, today)
    json.dump([title, body], open("push.json", "w"))
    print(title, "\n", body)


if __name__ == "__main__":
    main()
