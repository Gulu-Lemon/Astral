"""Quick server test - starts server and hits API"""
import sys, os, threading, time, urllib.request, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

def run_server():
    app.run(host="127.0.0.1", port=18000, debug=False, threaded=True)

t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(2)

try:
    resp = urllib.request.urlopen("http://127.0.0.1:18000/api/state")
    data = json.loads(resp.read())
    npcs = data.get("npcs", [])
    print(f"API OK: {len(npcs)} NPCs")
    for n in npcs[:3]:
        print(f"  {n['agent_id']} {n['name']}: aff={n['affection']}")
except Exception as ex:
    print(f"API error: {ex}")

print("Server test complete")
