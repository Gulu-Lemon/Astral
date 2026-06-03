"""
角色卡管理 — 读取/写入/列出 cards/*.txt
支持格式：star流（『』章节）、Ajisai（<#> markdown）、旧 key:value
"""
import os
import re
from typing import Optional

CARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards")


def ensure_dir():
    os.makedirs(CARDS_DIR, exist_ok=True)


# === 格式检测 ===

def _detect_format(text: str) -> str:
    if '<Ajisai_Character_Loader>' in text:
        return "ajisai"
    if re.search(r'『[^』]+』', text):
        return "star"
    if re.search(r'^##\s*', text, re.MULTILINE):
        return "star"
    return "legacy"


# === 通用章节提取 ===

_STAR_SECTION_RE = re.compile(r'^『([^』]+)』\s*$', re.MULTILINE)
_AJISAI_SECTION_RE = re.compile(r'^(?:##?\s+|#\s+)([^#\n]+)$', re.MULTILINE)
_HASH_SECTION_RE = re.compile(r'^##\s*(.+?)\s*$', re.MULTILINE)
_FIELD_RE = re.compile(r'^([^：:\s]+)\s*[：:]\s*(.*)$')


def _clean_name(raw: str) -> str:
    """去掉日文括号注音和多余空白。"""
    return re.sub(r'\s*[（(][^)）]*[)）]\s*', '', raw).strip()


def _clean_age(raw: str) -> str:
    """从混合文本中提取数字年龄。"""
    m = re.findall(r'\d+', str(raw))
    return m[0] if m else "16"

# 已知章节名 → 归一化键名
_SECTION_MAP = {
    "个人档案": "profile", "個": "profile",
    "外貌形象": "appearance_section", "衣装": "appearance_section",
    "背景经历": "background",
    "性格调色盘": "personality_detail", "性格核心": "personality_detail",
    "语料库": "dialogue_corpus", "Character_Dialogue_Corpus": "dialogue_corpus",
    "重要关系": "relationships",
    "行为边界": "boundaries",
    "魔法能力": "magic_detail",
}

_VALID_FIELDS = frozenset({
    "姓名", "名字", "name", "年龄", "age", "性别", "sex",
    "生日", "birthday", "身高", "魔法", "magic", "魔法能力",
    "身份", "identity", "血型", "体重",
})


def _extract_sections(text: str, section_re, strip_wrapper: str = None) -> dict[str, str]:
    """用正则匹配章节标题的位置切分文本，返回 {章节名: 内容}。"""
    if strip_wrapper:
        text = re.sub(rf'</?{re.escape(strip_wrapper)}>', '', text)
    matches = list(section_re.finditer(text))
    if not matches:
        return {"_preamble": text.strip()}
    sections: dict[str, str] = {}
    first_title = matches[0].group(1).strip()
    if matches[0].start() > 0:
        sections["_preamble"] = text[:matches[0].start()].strip()
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections[title] = content
    return sections


def _normalize_sections(raw_sections: dict[str, str]) -> dict[str, str]:
    """将章节名归一化为英文键名。未知章节保留原文键名。"""
    result: dict[str, str] = {}
    for title, content in raw_sections.items():
        normalized = title.strip().lstrip('#').strip()
        mapped = None
        for known, key in _SECTION_MAP.items():
            if known in normalized:
                mapped = key
                break
        if mapped:
            result[mapped] = content
        else:
            result[normalized] = content
    return result


def _parse_profile_fields(section_text: str) -> dict[str, str]:
    """从『个人档案』中提取结构化字段。支持多行续接。"""
    fields: dict[str, str] = {}
    current_key = None
    for line in section_text.split('\n'):
        m = _FIELD_RE.match(line.strip())
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key in _VALID_FIELDS:
                if key in ("姓名", "名字"): fields["name"] = _clean_name(val); current_key = "name"
                elif key in ("年龄", "age"): fields["age"] = _clean_age(val); current_key = "age"
                elif key in ("魔法", "魔法能力", "magic"):
                    if "magic" not in fields:
                        fields["magic"] = val
                    elif val:
                        fields["magic"] += "\n" + val
                    current_key = "magic"
                elif key in ("性别", "sex"): fields["gender"] = val; current_key = None
                elif key in ("身高",): fields["height"] = val; current_key = None
                elif key in ("身份", "identity"): fields["identity"] = val; current_key = None
                elif key in ("生日", "birthday"): fields["birthday"] = val; current_key = None
                elif key in ("血型",): fields["blood_type"] = val; current_key = None
                elif key in ("体重",): fields["weight"] = val; current_key = None
            else:
                current_key = None
        elif current_key and line.strip():
            fields[current_key] += "\n" + line.strip()
    return fields


# === star流 解析器 ===

def _parse_star_card(text: str) -> dict:
    """解析 star流 格式（『』章节）及 `##` 变体。"""
    # 将 ## 标题 转换为 『标题』，统一格式
    if re.search(r'^##\s*', text, re.MULTILINE) and not re.search(r'『[^』]+』', text):
        text = _HASH_SECTION_RE.sub(r'『\1』', text)
    raw = _extract_sections(text, _STAR_SECTION_RE)
    sections = _normalize_sections(raw)

    card: dict = {"name": "", "age": "16", "appearance": "", "magic": "", "personality": "",
                  "background": "", "dialogue_corpus": "", "relationships": "",
                  "boundaries": "", "other_sections": {}, "raw": text}

    if "profile" in sections:
        pf = _parse_profile_fields(sections["profile"])
        card.update(pf)

    if "appearance_section" in sections:
        card["appearance"] = sections["appearance_section"]

    if "background" in sections:
        card["background"] = sections["background"]

    if "personality_detail" in sections:
        card["personality"] = sections["personality_detail"]

    if "dialogue_corpus" in sections:
        card["dialogue_corpus"] = sections["dialogue_corpus"]

    if "relationships" in sections:
        card["relationships"] = sections["relationships"]

    if "boundaries" in sections:
        card["boundaries"] = sections["boundaries"]

    if "magic_detail" in sections:
        card["magic"] = card.get("magic", "") or sections["magic_detail"]
        if card["magic"] and sections["magic_detail"] and card["magic"] != sections["magic_detail"]:
            card["magic"] += "\n\n" + sections["magic_detail"]

    # 未知章节一律收集
    known_keys = {"profile", "appearance_section", "background", "personality_detail",
                  "dialogue_corpus", "relationships", "boundaries", "magic_detail"}
    for key, content in sections.items():
        if key not in known_keys and key != "_preamble":
            card["other_sections"][key] = content

    return card


# === Ajisai 解析器 ===

def _parse_ajisai_card(text: str) -> dict:
    """解析 Ajisai 格式（<#> markdown 章节）。"""
    stripped = re.sub(r'</?Ajisai_Character_Loader>', '', text)
    # 提取 <tag> 包裹的内容块
    tag_blocks: dict[str, str] = {}
    for m in re.finditer(r'<([^>]+)>(.*?)</\1>', stripped, re.DOTALL):
        tag_blocks[m.group(1)] = m.group(2).strip()
    if "Character_Dialogue_Corpus" in tag_blocks:
        stripped = re.sub(
            r'<Character_Dialogue_Corpus>.*?</Character_Dialogue_Corpus>',
            '', stripped, flags=re.DOTALL)

    raw = _extract_sections(stripped, _AJISAI_SECTION_RE)
    sections = _normalize_sections(raw)

    card: dict = {"name": "", "age": "16", "appearance": "", "magic": "", "personality": "",
                  "background": "", "dialogue_corpus": "", "relationships": "",
                  "boundaries": "", "other_sections": {}, "raw": text}

    if "profile" in sections:
        pf = _parse_profile_fields(sections["profile"])
        card.update(pf)

    if "appearance_section" in sections:
        card["appearance"] = sections["appearance_section"]

    if "background" in sections:
        card["background"] = sections["background"]

    if "personality_detail" in sections:
        card["personality"] = sections["personality_detail"]

    # 语料库：优先用 <tag> 块，回退到章节
    if "dialogue_corpus" in tag_blocks:
        card["dialogue_corpus"] = tag_blocks["dialogue_corpus"]
    elif "dialogue_corpus" in sections:
        card["dialogue_corpus"] = sections["dialogue_corpus"]

    for k in ("relationships", "boundaries", "magic_detail"):
        if k in sections:
            card[k] = sections[k]

    # 合并 magic_detail 到 magic
    if "magic_detail" in sections:
        card["magic"] = card.get("magic", "") or sections["magic_detail"]
        if card["magic"] and card.get("magic") != sections.get("magic_detail", ""):
            card["magic"] += "\n\n" + sections["magic_detail"]

    known_keys = {"profile", "appearance_section", "background", "personality_detail",
                  "dialogue_corpus", "relationships", "boundaries", "magic_detail"}
    for key, content in sections.items():
        if key not in known_keys and key != "_preamble":
            card["other_sections"][key] = content

    return card


# === 旧格式解析器 ===

def _parse_legacy_card(text: str) -> dict:
    card = {"name": "", "age": "16", "appearance": "", "magic": "", "personality": "",
            "background": "", "dialogue_corpus": "", "relationships": "",
            "boundaries": "", "other_sections": {}, "raw": text}
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


# === 统一入口 ===

def parse_card(text: str) -> dict:
    fmt = _detect_format(text)
    if fmt == "star":
        return _parse_star_card(text)
    elif fmt == "ajisai":
        return _parse_ajisai_card(text)
    else:
        return _parse_legacy_card(text)


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


def save_card(name: str, age: str, appearance: str, magic: str, personality: str = "",
              raw_text: str = "") -> str:
    ensure_dir()
    safe = re.sub(r'[\\/:*?"<>|]', "", name)[:30]
    if not safe:
        safe = "unnamed"
    fname = f"{safe}.txt"
    # 如果有星流原文，保留原格式；否则用旧格式
    content = raw_text.strip() if raw_text.strip() else format_card(name, age, appearance, magic, personality)
    counter = 1
    # 按文件名查找已有文件来覆盖（而非自动递增）
    fn_to_delete = None
    for existing in os.listdir(CARDS_DIR):
        if existing.endswith(".txt"):
            epath = os.path.join(CARDS_DIR, existing)
            try:
                with open(epath, "r", encoding="utf-8") as f:
                    ecard = parse_card(f.read())
                if ecard.get("name") == name:
                    fn_to_delete = epath
                    break
            except Exception:
                pass
    if fn_to_delete:
        os.remove(fn_to_delete)
        path = fn_to_delete
    else:
        path = os.path.join(CARDS_DIR, fname)
        while os.path.exists(path):
            fname = f"{safe}_{counter}.txt"
            path = os.path.join(CARDS_DIR, fname)
            counter += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.basename(path)


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


def get_cards_mtime() -> float:
    """返回 cards/ 目录下所有 .txt 文件的最新修改时间之和（用于变更检测）。"""
    ensure_dir()
    total = 0.0
    for fname in os.listdir(CARDS_DIR):
        if fname.endswith(".txt"):
            try:
                total += os.path.getmtime(os.path.join(CARDS_DIR, fname))
            except OSError:
                pass
    return total


_NPC_LIBRARY_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NPC_cards")


def load_npc_library_card(scene_name: str, agent_id: str) -> Optional[dict]:
    """从 NPC角色库 目录加载指定场景的 NPC 角色卡。
    scene_name: 场景全名，如 '魔法少女的云端假期'
    agent_id: 如 'No.01'
    返回 parse_card() 的 dict 结果，不存则返回 None。
    """
    lib_dir = os.path.join(_NPC_LIBRARY_ROOT, scene_name)
    if not os.path.isdir(lib_dir):
        return None
    prefix = f"{agent_id} "
    for fname in os.listdir(lib_dir):
        if fname.startswith(prefix) and fname.endswith(".txt"):
            path = os.path.join(lib_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return parse_card(f.read())
            except Exception:
                return None
    return None


def load_all_npc_library_cards(scene_name: str, npc_ids: list[str]) -> dict[str, dict]:
    """批量加载场景所有 NPC 角色卡。返回 {agent_id: card_dict}。"""
    result: dict[str, dict] = {}
    for aid in npc_ids:
        card = load_npc_library_card(scene_name, aid)
        if card:
            result[aid] = card
    return result
