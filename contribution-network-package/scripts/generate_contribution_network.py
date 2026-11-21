#!/usr/bin/env python3
"""Render the public GitHub contribution calendar as an animated neural-network GIF."""
import json
import math
import os
import urllib.request
from datetime import date
from PIL import Image, ImageDraw, ImageFilter

USERNAME = "mohamed1-0"
TOKEN = os.environ["GH_TOKEN"]
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
          }
        }
      }
    }
  }
}
"""

request = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode(),
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "contribution-neural-visual",
    },
)
with urllib.request.urlopen(request, timeout=30) as response:
    payload = json.load(response)

if payload.get("errors"):
    raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
user = payload.get("data", {}).get("user")
if not user:
    raise RuntimeError(f"GitHub user '{USERNAME}' was not found or is not accessible")
calendar = user["contributionsCollection"]["contributionCalendar"]
weeks = calendar["weeks"]
total = calendar["totalContributions"]
days = [day for week in weeks for day in week["contributionDays"]]
active = sum(day["contributionCount"] > 0 for day in days)

W, H = 1120, 286
LEFT, TOP = 44, 105
DX, DY = 19.5, 22
BG = (7, 17, 31)
CYAN = (0, 217, 255)
BLUE = (20, 105, 180)
CRIMSON = (255, 75, 92)
LEVELS = {
    "NONE": 0.0,
    "FIRST_QUARTILE": 0.25,
    "SECOND_QUARTILE": 0.50,
    "THIRD_QUARTILE": 0.75,
    "FOURTH_QUARTILE": 1.0,
}

grid = []
for wi, week in enumerate(weeks):
    column = []
    for di, day in enumerate(week["contributionDays"]):
        count = day["contributionCount"]
        intensity = LEVELS.get(day["contributionLevel"], 0.0)
        if count:
            intensity = max(intensity, min(1.0, 0.25 + count / 12))
        column.append({
            "x": LEFT + wi * DX,
            "y": TOP + di * DY,
            "count": count,
            "intensity": intensity,
            "date": day["date"],
        })
    grid.append(column)

# Subtle links between adjacent days turn the contribution calendar into a network.
edges = []
for wi, column in enumerate(grid):
    for di, node in enumerate(column):
        for next_w, next_d in ((wi + 1, di), (wi, di + 1), (wi + 1, di + 1)):
            if next_w < len(grid) and next_d < len(grid[next_w]):
                other = grid[next_w][next_d]
                edges.append((node, other, max(node["intensity"], other["intensity"])))

# Month labels are placed above the first week containing each month.
month_labels = []
seen_months = set()
for wi, column in enumerate(grid):
    if not column:
        continue
    for node in column:
        month = date.fromisoformat(node["date"]).strftime("%b").upper()
        if month not in seen_months:
            month_labels.append((LEFT + wi * DX - 2, month))
            seen_months.add(month)
            break

frames = []
for frame_no in range(20):
    base = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    draw = ImageDraw.Draw(base)

    draw.text((LEFT, 24), "CONTRIBUTION NETWORK", fill=(226, 244, 255))
    draw.text((LEFT, 49), "LAST 12 MONTHS  /  LIVE FROM GITHUB", fill=(104, 151, 177))
    draw.text((W - 330, 26), f"{total:,} CONTRIBUTIONS", fill=CYAN)
    draw.text((W - 330, 50), f"{active} ACTIVE DAYS", fill=(142, 178, 199))

    for x, label in month_labels:
        draw.text((x, 78), label, fill=(75, 112, 133))

    for a, b, strength in edges:
        if strength <= 0:
            color, width = (18, 49, 70, 28), 1
        else:
            pulse = 0.65 + 0.35 * ((1 + math.sin(frame_no * 0.55 + a["x"] * 0.025)) / 2)
            alpha = int((35 + 105 * strength) * pulse)
            color, width = (*CYAN, alpha), (1 if strength < 0.5 else 2)
        gd.line((a["x"], a["y"], b["x"], b["y"]), fill=color, width=width)

    for column in grid:
        for node in column:
            intensity = node["intensity"]
            x, y = node["x"], node["y"]
            if intensity <= 0:
                r = 2.1
                draw.ellipse((x-r, y-r, x+r, y+r), fill=(20, 43, 59))
                continue
            phase = frame_no * 0.48 + x * 0.035 + y * 0.04
            pulse = 0.78 + 0.22 * ((1 + math.sin(phase)) / 2)
            radius = 2.3 + 3.0 * intensity
            color = tuple(int(BLUE[i] * (1-intensity) + CYAN[i] * intensity) for i in range(3))
            alpha = int(95 + 150 * intensity * pulse)
            gd.ellipse((x-radius*2.7, y-radius*2.7, x+radius*2.7, y+radius*2.7),
                       fill=(*color, int(alpha * 0.18)))
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)

    glow = glow.filter(ImageFilter.GaussianBlur(7))
    frame = Image.alpha_composite(base.convert("RGBA"), glow)
    draw = ImageDraw.Draw(frame)

    # Crisp foreground nodes over the glow.
    for column in grid:
        for node in column:
            intensity = node["intensity"]
            if intensity <= 0:
                continue
            x, y = node["x"], node["y"]
            color = tuple(int(BLUE[i] * (1-intensity) + CYAN[i] * intensity) for i in range(3))
            radius = 2.3 + 3.0 * intensity
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*color, 255))

    # A restrained crimson accent marks the most active day.
    strongest = max((node for column in grid for node in column),
                    key=lambda node: node["count"], default=None)
    if strongest and strongest["count"]:
        x, y = strongest["x"], strongest["y"]
        draw.ellipse((x-2.5, y-2.5, x+2.5, y+2.5), fill=(*CRIMSON, 255))

    for label, row in (("MON", 1), ("WED", 3), ("FRI", 5)):
        draw.text((LEFT-36, TOP + row*DY - 5), label, fill=(75, 112, 133))
    frames.append(frame.convert("RGB"))

os.makedirs("assets", exist_ok=True)
frames[0].save(
    "assets/contribution-network.gif",
    save_all=True,
    append_images=frames[1:],
    duration=140,
    loop=0,
    optimize=True,
)
print(f"Rendered {len(days)} days, {total} contributions, {active} active days.")
