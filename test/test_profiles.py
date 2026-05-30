"""Test profile API"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run(): app.run(host="127.0.0.1", port=18011, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True); t.start(); time.sleep(3)
base = "http://127.0.0.1:18011"
def get(p):
    return json.loads(urllib.request.urlopen(base+p).read())
def post(p, d):
    req = urllib.request.Request(base+p,data=json.dumps(d).encode(),headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req).read())

# Test profiles list (empty initially)
r = get("/api/profiles")
print(f"[1] Profiles: {r}")
assert r.get("profiles") is not None, "profiles key missing"

# Create a profile
r = post("/api/profiles", {"name":"TestConfig","base_url":"https://api.test.com","api_key":"sk-test","model":"test-model"})
print(f"[2] Create: ok={r.get('ok')}")
assert r.get("ok") == True

# Activate
r = post("/api/profiles/activate", {"name":"TestConfig"})
print(f"[3] Activate: ok={r.get('ok')}")
assert r.get("ok") == True

# List again
r = get("/api/profiles")
print(f"[4] Profiles: {len(r.get('profiles',[]))} profiles, active={r.get('active')}")
assert len(r.get('profiles',[])) == 1

# Delete
r = post("/api/profiles/delete", {"name":"TestConfig"})
print(f"[5] Delete: ok={r.get('ok')}")
assert r.get("ok") == True

# Verify empty
r = get("/api/profiles")
print(f"[6] After delete: {len(r.get('profiles',[]))} profiles")
assert len(r.get('profiles',[])) == 0

print("\n[ALL PASSED]")
