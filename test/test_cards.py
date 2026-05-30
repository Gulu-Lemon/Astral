"""Test card API endpoints"""
import sys, os, threading, time, urllib.request, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run(): app.run(host="127.0.0.1", port=18008, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True); t.start(); time.sleep(3)
base = "http://127.0.0.1:18008"
def get(p): return json.loads(urllib.request.urlopen(base+p).read())
def post(p, d): 
    req = urllib.request.Request(base+p, data=json.dumps(d).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req).read())

# List cards
r = get("/api/cards")
print(f"[1] Cards: {len(r.get('cards',[]))}")
for c in r.get("cards",[]):
    print(f"    {c['name']}: {c['magic'][:40]}")

# Create card
r = post("/api/cards", {"name":"测试角色","age":"14","appearance":"红发双马尾","magic":"操控火焰"})
print(f"[2] Created: {r.get('ok')}, total={len(r.get('cards',[]))}")

# Start with card
r = post("/api/start_with_card", {"card_name":"测试角色"})
print(f"[3] Start with card: ok={r.get('ok')}, name={r.get('name','')}")

print("\n[OK]")
