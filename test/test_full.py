"""Quick integration test for new features"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run():
    app.run(host="127.0.0.1", port=18002, debug=False, threaded=True)

t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(2)
base = "http://127.0.0.1:18002"

def post(path, data=None):
    if data is None: data = {}
    req = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req).read())

def get(path):
    return json.loads(urllib.request.urlopen(base + path).read())

# Test base state
s = get("/api/state")
print(f"State: created={s['player_created']}, prologue={s['prologue_step']}")

# Test prologue step 1
r = post("/api/prologue/mirror", {"name": "测试玩家", "age": "16", "appearance": "黑色短发，蓝色眼睛"})
assert r["step"] == 1, f"Expected step 1, got {r['step']}"
print(f"Prologue 1 OK: {len(r['text'])} chars")

# Test prologue step 2
r = post("/api/prologue/magic", {"magic": "操控水流"})
assert r["step"] == 2
print(f"Prologue 2 OK: {len(r['text'])} chars")

# Test difficulty
r = post("/api/prologue/difficulty", {"mode": "B"})
assert r["step"] == 3
print(f"Prologue 3 OK: diff=normal")

# Test camp
r = get("/api/prologue/camp")
assert r["step"] == 4
print(f"Prologue 4 OK: {len(r['text'])} chars")

# Test explore
r = get("/api/prologue/explore")
assert r["step"] == 5
print(f"Prologue 5 OK")

# Test admin
r = get("/api/prologue/admin")
assert r["step"] == 6
print(f"Prologue 6 OK")

# Test finish
r = post("/api/prologue/finish")
assert r["step"] == 7
print(f"Prologue 7 OK: finished")

# Verify state after prologue
s = get("/api/state")
assert s["player_created"] == True
assert s["difficulty"] == "normal"
assert s["prologue_step"] == 7
print(f"After prologue: diff={s['difficulty']}, step={s['prologue_step']}")

# Test investigate
r = post("/api/investigate", {"action": "查看挂毯"})
assert r["ok"]
print(f"Investigate OK: {len(r['description'])} chars")

# Test dialogue
r = post("/api/dialogue", {"agent_id": "No.01", "message": "你是谁？"})
assert r["ok"]
print(f"Dialogue OK: {r['agent_name']}: {len(r['response'])} chars")

# Test save
r = post("/api/save/1")
saves = r.get("slots", [])
print(f"Save OK: {len(saves)} save(s)")

print("\n=== ALL TESTS PASSED ===")
