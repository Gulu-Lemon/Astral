"""Verify scenarios load and basic endpoints work"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FLASK_ENV"] = "development"

# Check imports
from scenarios import list_scenarios, load
load("tianji_maze")
load("cloud_holiday")
scenes = list_scenarios()
print(f"Scenarios: {len(scenes)}")
for s in scenes:
    print(f"  {s['id']}: {s['name']}")

# Quick server test
from server import app
def run():
    app.run(host="127.0.0.1", port=18006, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(3)

# Get initial state
resp = urllib.request.urlopen("http://127.0.0.1:18006/api/state")
data = json.loads(resp.read())
print(f"\nDefault scene: {data.get('scene_id')} -> {data.get('scene_name','')}")
print(f"Default rooms: {len(data.get('room_items',{}))} items in starting room")

# Test scene list
resp = urllib.request.urlopen("http://127.0.0.1:18006/api/scenes")
data = json.loads(resp.read())
print(f"API scene list: {len(data.get('scenes',[]))} scenes")

# Test scene select
req = urllib.request.Request("http://127.0.0.1:18006/api/select_scene",
    data=json.dumps({"scene_id":"cloud_holiday"}).encode(),
    headers={"Content-Type":"application/json"})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"Switch to: {data.get('scene_name','')}")

# Verify state after switch
resp = urllib.request.urlopen("http://127.0.0.1:18006/api/state")
data = json.loads(resp.read())
print(f"After switch: {data.get('scene_id')} -> {data.get('scene_name','')}")
print(f"Start room: {data.get('location','')}")

# Test prologue with cloud_holiday
req = urllib.request.Request("http://127.0.0.1:18006/api/prologue/mirror",
    data=json.dumps({"name":"测试","age":"16","appearance":"银发红瞳"}).encode(),
    headers={"Content-Type":"application/json"})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"Prologue 1 (cloud_holiday): {len(data.get('text',''))} chars")

print("\n[Done]")
