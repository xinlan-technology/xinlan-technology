#!/usr/bin/env python3
"""Refresh activity.json from the public contribution calendar, then re-run build.py.

    design/tools/.venv/bin/python refresh_activity.py [login]

Reads https://github.com/users/<login>/contributions - the same calendar GitHub draws on the profile
page - so the heatmap matches it. (The GraphQL `viewer` query returns a different, lower total.)
"""
import datetime, json, pathlib, re, sys, urllib.request

login = sys.argv[1] if len(sys.argv) > 1 else "xinlan-technology"
url = f"https://github.com/users/{login}/contributions"
html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode()
tips = {m.group(1): m.group(2) for m in re.finditer(r'<tool-tip[^>]*for="([^"]+)"[^>]*>(.*?)</tool-tip>', html, re.S)}
days = {}
for m in re.finditer(r'data-date="(\d{4}-\d{2}-\d{2})"\s+id="([^"]+)"\s+data-level="(\d)"', html):
    date, cid, _ = m.groups()
    n = re.match(r"(\d+)\s+contribution", tips.get(cid, "").strip())
    days[date] = int(n.group(1)) if n else 0
if not days:
    sys.exit("could not parse the calendar - GitHub changed its markup")
ds = sorted(days)
weeks, cur = [], []
d, end = datetime.date.fromisoformat(ds[0]), datetime.date.fromisoformat(ds[-1])
while d <= end:
    cur.append(days.get(d.isoformat(), 0))
    if len(cur) == 7:
        weeks.append(cur)
        cur = []
    d += datetime.timedelta(days=1)
if cur:
    weeks.append(cur)
out = dict(fetched=ds[-1], total=sum(days.values()), weeks=weeks, start=ds[0], end=ds[-1])
pathlib.Path(__file__).with_name("activity.json").write_text(json.dumps(out) + "\n")
print(f"{out['total']} contributions, {sum(1 for v in days.values() if v)} active days, {ds[0]} -> {ds[-1]}")
print("now re-run build.py")
