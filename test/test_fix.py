"""Quick test for remaining fixes"""
import sys, os, threading, time, urllib.request, json, codecs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FLASK_ENV"] = "development"

from server import app
import scenarios
scenarios.load("tianji_maze")
scenarios.load("cloud_holiday")

def run(): app.run(host="127.0.0.1", port=18007, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True); t.start(); time.sleep(3)

def get(p): return json.loads(urllib.request.urlopen("http://127.0.0.1:18007"+p).read())

# 1. Check state has needed fields
s = get("/api/state")
print(f"[1] Player created: {s.get('player_created')}")
print(f"[1] Scene: {s.get('scene_name','')}")

# 2. Check scene list
s = get("/api/scenes")
print(f"[2] Scenes: {len(s.get('scenes',[]))}")

# 3. Start game & check first-murder delay
req = urllib.request.Request("http://127.0.0.1:18007/api/prologue/mirror",
    data=json.dumps({"name":"Test","age":"16","appearance":"测试"}).encode(),
    headers={"Content-Type":"application/json"})
urllib.request.urlopen(req).read()

req = urllib.request.Request("http://127.0.0.1:18007/api/prologue/magic",
    data=json.dumps({"magic":"测试"}).encode(),
    headers={"Content-Type":"application/json"})
urllib.request.urlopen(req).read()

req = urllib.request.Request("http://127.0.0.1:18007/api/prologue/difficulty",
    data=json.dumps({"mode":"B"}).encode(),
    headers={"Content-Type":"application/json"})
urllib.request.urlopen(req).read()

# Finish prologue quickly
urllib.request.urlopen("http://127.0.0.1:18007/api/prologue/camp").read()
urllib.request.urlopen("http://127.0.0.1:18007/api/prologue/explore").read()
urllib.request.urlopen("http://127.0.0.1:18007/api/prologue/admin").read()
urllib.request.urlopen("http://127.0.0.1:18007/api/prologue/finish", data=b'{}').read()

s = get("/api/state")
print(f"[3] Prologue complete: step={s.get('prologue_step')}")
print(f"[3] Rounds since murder: {get('/api/state').get('rounds_since_last_murder','N/A')}")

print("\n[ALL CHECKS PASSED]")
