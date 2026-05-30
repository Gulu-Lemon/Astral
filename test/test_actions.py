"""Test investigation and room interaction endpoints"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run():
    app.run(host="127.0.0.1", port=18001, debug=False, threaded=True)

t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(2)

base = "http://127.0.0.1:18001"

# Test room investigation
resp = urllib.request.urlopen(base + "/api/state")
print(f"State: {resp.status}")

# Test explore
req = urllib.request.Request(
    base + "/api/explore",
    data=json.dumps({"room": "藏书室"}).encode(),
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"Explore: {data['room']} -> ({len(data['description'])} chars)")

# Test investigate
req = urllib.request.Request(
    base + "/api/investigate",
    data=json.dumps({"action": "阅读《魔法概述》"}).encode(),
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"Investigate: \"{data['action']}\" -> ({len(data['description'])} chars) {data['description'][:80]}")

# Test investigate 2
req = urllib.request.Request(
    base + "/api/investigate",
    data=json.dumps({"action": "查看书架排列"}).encode(),
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(f"Investigate: \"{data['action']}\" -> ({len(data['description'])} chars)")

print("\nAll action system tests OK")
