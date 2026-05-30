"""Test item state persistence through investigation"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run():
    app.run(host="127.0.0.1", port=18005, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(2)
base = "http://127.0.0.1:18005"

def post(path, data={}):
    req = urllib.request.Request(base+path,
        data=json.dumps(data).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req).read())

# Check initial state
s = json.loads(urllib.request.urlopen(base+"/api/state").read())
inv = s.get("inventory", [])
items = s.get("room_items", {})
print(f"Initial: inventory={inv}")
print(f"Room items (starting camp): {len(items)} items")

# Investigate "take the wood from fireplace"
result = post("/api/investigate", {"action": "拿起壁炉里的木柴"})
print(f"\nInvestigate 1: {result.get('description','')[:80]}...")
print(f"  inventory now: {result.get('inventory', [])}")

# Check state
s = json.loads(urllib.request.urlopen(base+"/api/state").read())
print(f"  state inventory: {s.get('inventory', [])}")

# Do another investigate to check state persistence
result2 = post("/api/investigate", {"action": "检查壁炉"})
print(f"\nInvestigate 2 (check fireplace again): {result2.get('description','')[:100]}...")
print(f"  inventory: {result2.get('inventory', [])}")

# Check final room state
s = json.loads(urllib.request.urlopen(base+"/api/state").read())
room_state = s.get("room_items", {})
print(f"\nRoom state: {room_state}")

print("\n[Done]")
