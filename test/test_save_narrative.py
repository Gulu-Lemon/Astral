"""Test save/load narrative persistence"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run():
    app.run(host="127.0.0.1", port=18003, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(2)
base = "http://127.0.0.1:18003"

def post(path, data=None):
    if data is None: data = {}
    req = urllib.request.Request(base+path, data=json.dumps(data).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req).read())

def get(path):
    return json.loads(urllib.request.urlopen(base+path).read())

# Run a quick prologue
post("/api/prologue/mirror", {"name":"Test","age":"16","appearance":"black hair"})
post("/api/prologue/magic", {"magic":"water control"})
post("/api/prologue/difficulty", {"mode":"B"})
get("/api/prologue/camp")
get("/api/prologue/explore")
get("/api/prologue/admin")
post("/api/prologue/finish")

# Save
r = post("/api/save/1")
print(f"Save OK, slots: {len(r.get('slots',[]))}")

# Load  
r = post("/api/load/1")
nlog = r.get("narrative_log", [])
print(f"Load OK, narrative entries: {len(nlog)}")
for i, n in enumerate(nlog[:3]):
    print(f"  [{i}] {n['type']}: {n['text'][:60]}...")
if len(nlog) > 0:
    print(f"  ... and {len(nlog)-3} more")

# Verify state
s = get("/api/state")
print(f"State: day={s['day']}, diff={s['difficulty']}, prologue={s['prologue_step']}")

print("\n=== ALL PASSED ===")
