"""Step 4 smoke test: NPC perception equality."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_engine import _display_id, _reverse_id, NPCAgent
from state import WorldState, AgentState

def test_display_id():
    assert _display_id("player") == "No.13"
    assert _display_id("No.01") == "No.01"
    assert _display_id("No.13") == "No.13"
    print("_display_id: OK")

def test_reverse_id():
    assert _reverse_id("No.13") == "player"
    assert _reverse_id("No.01") == "No.01"
    assert _reverse_id("player") == "player"  # doesn't double-convert
    print("_reverse_id: OK")

def test_agent_prompt_uses_no13():
    # Verify agent perception uses No.13
    from llm import LLMClient
    # We can't test the full LLM chain, but verify the helper is imported
    from agent_engine import _display_id as d
    assert d("player") == "No.13"
    
    # Verify Perception uses display IDs
    world = WorldState()
    world.npc_locations["player"] = "大厅"
    world.npc_locations["No.01"] = "大厅"
    world.npc_locations["No.02"] = "大厅"
    
    llm = LLMClient("")
    agent = NPCAgent("No.01", llm, {
        "No.01": type('obj', (object,), {'name': 'A', 'system_prompt': 'test', 'personality': 'calm', 'appearance': 'tall', 'play_core': 'test', 'magic': 'test'})(),
        "No.02": type('obj', (object,), {'name': 'B', 'system_prompt': 'test', 'personality': 'calm', 'appearance': 'short', 'play_core': 'test', 'magic': 'test'})(),
    }, player_name="玩家")
    
    p = agent.perceive(world)
    # nearby_npcs should use No.13 instead of "player"
    assert "No.13" in p.nearby_npcs or "No.13" in p.nearby_npcs, f"Expected No.13 in {p.nearby_npcs}"
    # "player" should NOT appear
    assert "player" not in p.nearby_npcs, f"Found 'player' in {p.nearby_npcs}"
    print("Agent perception: OK (player hidden as No.13)")

def test_gm_npc_label():
    from gm import GMNarrator
    from llm import LLMClient
    gm = GMNarrator(LLMClient(""), player_name="小坂爱莲")
    label = gm._npc_label("player")
    assert "小坂爱莲" in label or "玩家" in label
    print(f"GM _npc_label: OK ({label})")

if __name__ == '__main__':
    test_display_id()
    test_reverse_id()
    test_agent_prompt_uses_no13()
    test_gm_npc_label()
    print("\n=== Step 4 ALL TESTS PASSED ===")
