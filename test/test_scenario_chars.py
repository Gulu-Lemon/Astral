import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scenarios import load, get
load("cloud_holiday")
load("tianji_maze")
load("snow_train")
for sid in ["cloud_holiday", "tianji_maze", "snow_train"]:
    s = get(sid)
    c = s.get("characters", {})
    names = [v.name for v in c.values()]
    print(f"{sid}: {len(c)} chars, first 3: {names[:3]}")
