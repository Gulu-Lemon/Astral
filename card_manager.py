"""
角色卡管理 — 读取/写入/列出 cards/*.txt
"""
import os
import re
from typing import Optional

CARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards")


def ensure_dir():
    os.makedirs(CARDS_DIR, exist_ok=True)


def parse_card(text: str) -> dict:
    card = {"name": "", "age": "16", "appearance": "", "magic": "", "personality": "", "raw": text}
    current_key = None
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("name:"):
            card["name"] = line[5:].strip(); current_key = None
        elif line.startswith("age:"):
            card["age"] = line[4:].strip(); current_key = None
        elif line.startswith("appearance:"):
            card["appearance"] = line[11:].strip(); current_key = "appearance"
        elif line.startswith("magic:"):
            card["magic"] = line[6:].strip(); current_key = "magic"
        elif line.startswith("personality:"):
            card["personality"] = line[12:].strip(); current_key = "personality"
        elif current_key and line:
            card[current_key] += "\n" + line
    return card


def format_card(name: str, age: str, appearance: str, magic: str, personality: str = "") -> str:
    result = f"name: {name}\nage: {age}\nappearance: {appearance}\nmagic: {magic}\n"
    if personality:
        result += f"personality: {personality}\n"
    return result


def list_cards() -> list[dict]:
    ensure_dir()
    cards = []
    for fname in sorted(os.listdir(CARDS_DIR)):
        if fname.endswith(".txt"):
            path = os.path.join(CARDS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                card = parse_card(raw)
                card["filename"] = fname
                cards.append(card)
            except Exception:
                pass
    return cards


def get_card(name: str) -> Optional[dict]:
    if not name: return None
    for card in list_cards():
        if card["name"] == name:
            return card
    return None


def save_card(name: str, age: str, appearance: str, magic: str, personality: str = "") -> str:
    ensure_dir()
    safe = re.sub(r'[\\/:*?"<>|]', "", name)[:30]
    if not safe:
        safe = "unnamed"
    fname = f"{safe}.txt"
    path = os.path.join(CARDS_DIR, fname)
    content = format_card(name, age, appearance, magic, personality)
    counter = 1
    while os.path.exists(path):
        fname = f"{safe}_{counter}.txt"
        path = os.path.join(CARDS_DIR, fname)
        counter += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return fname


def delete_card(name: str) -> bool:
    if not name: return False
    for card in list_cards():
        if card["name"] == name:
            path = os.path.join(CARDS_DIR, card.get("filename") or f"{name}.txt")
            if os.path.exists(path):
                os.remove(path)
                return True
    # fallback: try exact name match
    fallback_path = os.path.join(CARDS_DIR, f"{name}.txt")
    if os.path.exists(fallback_path):
        os.remove(fallback_path)
        return True
    return False
