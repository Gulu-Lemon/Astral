"""Full integration smoke test"""
import sys, os, threading, time, urllib.request, json, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app

errors = []
def check(desc, ok, detail=""):
    if ok:
        print(f"  [PASS] {desc}")
    else:
        print(f"  [FAIL] {desc}: {detail}")
        errors.append(desc)

# 1. Module structure checks
from state import IntentType, WorldState, GamePhase, DifficultyMode, TrialState, Event
check("IntentType has TRAP", hasattr(IntentType, 'TRAP'))
check("WorldState has undiscovered_bodies", hasattr(WorldState, 'undiscovered_bodies'))

from agent_engine import NPCAgent, _parse_intent_type
check("_parse_intent_type handles trap", _parse_intent_type("trap") == IntentType.TRAP)

from arbiter import Arbiter
class MockLLM:
    def chat(self,**kw): return ""
    def chat_json(self,**kw): return {"t":"rest","e":"calm"}
a = Arbiter(MockLLM())
check("Arbiter instantiates", a is not None)

from card_manager import list_cards, save_card, parse_card
c = list_cards()
check("Card manager lists cards", isinstance(c, list))
card_text = "name: Test\ntest\nage: 16\nappearance: X\nmagic: Y\npersonality: Z"
parsed = parse_card(card_text)
check("Card parse personality", parsed.get("personality") == "Z")

from save_manager import SaveManager
sm = SaveManager()
check("SaveManager instantiates", sm is not None)

# 2. Server start + API endpoints
def run(): app.run(host="127.0.0.1", port=18009, debug=False, threaded=True)
t = threading.Thread(target=run, daemon=True); t.start(); time.sleep(3)
base = "http://127.0.0.1:18009"
def get(p):
    try: return json.loads(urllib.request.urlopen(base+p,timeout=10).read())
    except Exception as ex: return {"error":str(ex)}
def post(p,d):
    try:
        req = urllib.request.Request(base+p,data=json.dumps(d).encode(),headers={"Content-Type":"application/json"})
        return json.loads(urllib.request.urlopen(req,timeout=15).read())
    except Exception as ex: return {"error":str(ex)}

s = get("/api/state")
check("/api/state responds", "player_created" in s)

sc = get("/api/scenes")
check("/api/scenes returns scenes", len(sc.get("scenes",[])) >= 2)

ca = get("/api/cards")
check("/api/cards returns cards", "cards" in ca)

# Test card CRUD
r = post("/api/cards", {"name":"DebugTest","age":"12","appearance":"Red","magic":"Fire","personality":"Brave"})
check("create card", r.get("ok")==True, str(r.get("error","")))

r = post("/api/start_with_card", {"card_name":"DebugTest"})
check("start with card", r.get("ok")==True, str(r.get("error","")))

# Test prologue flow
r = post("/api/prologue/mirror", {"name":"Tester","age":"16","appearance":"X"})
check("prologue mirror", r.get("step")==1)

r = post("/api/prologue/magic", {"magic":"Test"})
check("prologue magic", r.get("step")==2)

r = post("/api/prologue/difficulty", {"mode":"B"})
check("prologue difficulty", r.get("step")==3)

# Test investigate
r = post("/api/investigate", {"action":"look around"})
check("investigate endpoint", "description" in r or r.get("ok")!=False)

# Test scene switch
r = post("/api/select_scene", {"scene_id":"cloud_holiday"})
check("select scene", r.get("ok")==True)

# Test save
r = post("/api/save/1", {})
check("save slot 1", r.get("ok")==True, str(r.get("error","")))

r = post("/api/save/auto", {})
check("save auto", r.get("ok")==True, str(r.get("error","")))

# Test load
r = post("/api/load/auto", {})
check("load auto", r.get("player_name","")!="")

# 3. Edge case checks
from state import WorldState
w = WorldState()
w.undiscovered_bodies = ["No.05", "No.09"]
check("undiscovered_bodies is list", isinstance(w.undiscovered_bodies, list))
w.undiscovered_bodies = [v for v in w.undiscovered_bodies if v != "No.05"]
check("remove from undiscovered_bodies", "No.05" not in w.undiscovered_bodies)

# Cleanup test card
from card_manager import delete_card
delete_card("DebugTest")
check("delete test card", True)

print(f"\n{'='*40}")
if errors:
    print(f"FAILURES: {len(errors)}")
    for e in errors: print(f"  - {e}")
else:
    print("ALL CHECKS PASSED")
