"""Test API key preservation"""
import sys,os,json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_profiles import save_profile, activate

save_profile("KeyTest", "https://x.com", "sk-secret-123", "m1")
activate("KeyTest")
# Update: base_url and model change, key left empty (should preserve)
save_profile("KeyTest", "https://y.com", "", "m2")

with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config_profiles.json"), "r", encoding="utf-8") as f:
    data = json.load(f)
for p in data["profiles"]:
    if p["name"] == "KeyTest":
        print(f"  url={p['base_url']} key={p['api_key'][:20]}... model={p['model']}")
        assert p["api_key"] == "sk-secret-123", "Key was NOT preserved!"
        print("  KEY PRESERVED: OK")
        break
