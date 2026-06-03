import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from card_manager import load_npc_library_card, load_all_npc_library_cards

# Test single card
card = load_npc_library_card('魔法少女的云端假期', 'No.01')
assert card is not None, 'Failed to load No.01'
print(f"No.01: name={card['name']}")
print(f"  personality: {len(card.get('personality',''))} chars")
print(f"  dialogue: {len(card.get('dialogue_corpus',''))} chars")
print(f"  relationships: {len(card.get('relationships',''))} chars")
print(f"  background: {len(card.get('background',''))} chars")
print(f"  boundaries: {len(card.get('boundaries',''))} chars")

# Test batch loading
cards = load_all_npc_library_cards('魔法少女的云端假期', [f'No.{i:02d}' for i in range(1, 13)])
print(f"\nBatch loaded: {len(cards)} of 12 NPCs")
for aid in sorted(cards.keys()):
    c = cards[aid]
    print(f"  {aid}: {c['name']}")

# Test tianji_maze (same characters)
cards2 = load_all_npc_library_cards('魔法少女的天际迷宫', ['No.01', 'No.02'])
print(f"\n天际迷宫: {len(cards2)} cards loaded")

# Test snow_train
cards3 = load_all_npc_library_cards('魔法少女的风雪列车', ['No.01', 'No.02'])
print(f"风雪列车: {len(cards3)} cards loaded")
for aid in cards3:
    c = cards3[aid]
    print(f"  {aid}: {c['name']}")

# Test from_rich_card
from characters import from_rich_card
profile = from_rich_card(card, agent_id="No.01")
print(f"\nfrom_rich_card: name={profile.name}")
print(f"  system_prompt length: {len(profile.system_prompt)} chars")
print(f"  system_prompt first 200: {profile.system_prompt[:200]}...")

print("\n=== ALL OK ===")
