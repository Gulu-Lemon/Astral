"""Test debug module works"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import debug
from server import app

# Install debug BEFORE starting server
debug.install_all(app)

def run():
    app.run(host="127.0.0.1", port=18003, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True)
t.start()
time.sleep(3)

base = "http://127.0.0.1:18003"

# Make some requests to generate logs
urllib.request.urlopen(base + "/api/state").read()
urllib.request.urlopen(base + "/api/slots").read()

# Quick prologue + investigate
req = urllib.request.Request(base+"/api/prologue/mirror",
    data=json.dumps({"name":"Test","age":"16","appearance":"blue hair"}).encode(),
    headers={"Content-Type":"application/json"})
urllib.request.urlopen(req).read()

req = urllib.request.Request(base+"/api/investigate",
    data=json.dumps({"action":"check wall"}).encode(),
    headers={"Content-Type":"application/json"})
urllib.request.urlopen(req).read()

time.sleep(1)

# Check log files
log_dir = os.path.join(os.path.dirname(__file__), "logs")
for fname in ["requests.log", "errors.log", "agents.log"]:
    path = os.path.join(log_dir, fname)
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"  {fname}: {size} bytes")
        if size > 0 and fname != "errors.log":
            with open(path, "r", encoding="utf-8") as f:
                first = f.readline().strip()[:120]
            print(f"    first line: {first}")
    else:
        print(f"  {fname}: not found")

print("\n[OK] Debug module working")
