"""
角色定义 — 从场景文件中提取的角色档案
"""
from dataclasses import dataclass, field
from typing import Optional
import logging
import re


@dataclass
class CharacterProfile:
    agent_id: str
    name: str
    name_jp: str
    age: int
    appearance: str
    personality: str
    magic: str
    daily_habits: str
    play_core: str
    secret: str
    witch_motive: str  # 魔女动机
    system_prompt: str  # agent 运行时的 system prompt

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "name_jp": self.name_jp,
            "age": self.age,
            "appearance": self.appearance,
            "personality": self.personality,
            "magic": self.magic,
            "daily_habits": self.daily_habits,
            "play_core": self.play_core,
            "secret": self.secret,
            "witch_motive": self.witch_motive,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CharacterProfile":
        p = cls(
            agent_id=d.get("agent_id", ""),
            name=d.get("name", ""),
            name_jp=d.get("name_jp", ""),
            age=d.get("age", 16),
            appearance=d.get("appearance", ""),
            personality=d.get("personality", ""),
            magic=d.get("magic", ""),
            daily_habits=d.get("daily_habits", ""),
            play_core=d.get("play_core", ""),
            secret=d.get("secret", ""),
            witch_motive=d.get("witch_motive", ""),
            system_prompt="",
        )
        p.system_prompt = cls.build_system_prompt(p)
        # 注册到全局字典
        if p.agent_id:
            import characters as _mod
            _mod.CHARACTERS[p.agent_id] = p
        return p

    @staticmethod
    def build_system_prompt(profile: "CharacterProfile", extra: str = "") -> str:
        """为 agent 构建 system prompt"""
        base = f"""你正在扮演一位魔法少女，参与一场互动叙事游戏。你来自普通现代世界的背景（类似现代日本），拥有名为"魔法"的个人超常能力。你的思维方式、生活习惯、社会常识均是当代普通人的。你不是奇幻世界中的法师，而是拥有特殊能力的现代少女。你必须始终以角色的视角思考和行动。

【你的身份】
ID: {profile.agent_id}
姓名: {profile.name}（{profile.name_jp}）
年龄: {profile.age}

【外貌】
{profile.appearance}

【性格】
{profile.personality}

【魔法能力】
{profile.magic}

【日常习惯】
{profile.daily_habits}

【扮演核心】
{profile.play_core}

【秘密】—— 绝不主动透露给任何角色（仅在极端情况下可能泄露）
{profile.secret}

【魔女动机】—— 当心理防线被击溃时，可能走向的黑暗道路
{profile.witch_motive}

【行为准则】
1. 你只知道自己亲眼所见、亲耳所闻的事情。好感度影响你的态度（高→友善，低→多疑），威胁感影响你的行为（高→防御/攻击性）。
2. 你守着自己的秘密，在符合你日常习惯的范围内自由行动。偶尔可以做一点不那么符合预期的事——人心本就难以预测。
3. 初次见面：你对其他角色的了解为零。不知道她们的名字、能力或过往，除非通过对话或观察了解。别人也不了解你。不要自称另一个身份，不要提及场景外的人物。"""
        if extra:
            base += "\n\n" + extra
        return base


CHARACTERS: dict[str, CharacterProfile] = {}


def register_character(
    agent_id: str, name: str, name_jp: str, age: int,
    appearance: str, personality: str, magic: str,
    daily_habits: str, play_core: str, secret: str, witch_motive: str
) -> CharacterProfile:
    if agent_id in CHARACTERS:
        logging.getLogger("astral").debug(f"覆盖已存在的角色: {agent_id}")
    profile = CharacterProfile(
        agent_id=agent_id, name=name, name_jp=name_jp, age=age,
        appearance=appearance.strip(), personality=personality.strip(),
        magic=magic.strip(), daily_habits=daily_habits.strip(),
        play_core=play_core.strip(), secret=secret.strip(),
        witch_motive=witch_motive.strip(),
        system_prompt=""
    )
    profile.system_prompt = CharacterProfile.build_system_prompt(profile)
    CHARACTERS[agent_id] = profile
    return profile


def from_rich_card(card: dict, agent_id: str = "", name_jp: str = "") -> CharacterProfile:
    """将 parse_card() 的富格式结果映射为 CharacterProfile。
    card 必须包含 name/age/appearance/magic/personality 等基础字段，
    可选包含 background/dialogue_corpus/relationships/boundaries/other_sections。
    """
    name = card.get("name", "").strip()
    age_str = card.get("age", "16")
    try:
        age = int(re.findall(r'\d+', str(age_str))[0]) if re.findall(r'\d+', str(age_str)) else 16
    except (ValueError, IndexError):
        age = 16

    # 提取核心提示词作为 play_core
    play_core = ""
    personality_full = card.get("personality", "").strip()
    pm = re.search(r'【核心提示词[：:](.+?)】', personality_full)
    if pm:
        play_core = pm.group(1).strip()
    elif personality_full:
        lines = personality_full.split('\n')
        if len(lines) > 2:
            play_core = lines[0] if len(lines[0]) < 200 else lines[0][:200]

    # 提取秘密（背景经历的前几段作为秘密）
    secret = card.get("background", "")[:500] if card.get("background") else ""

    # 构建富 system_prompt
    extra_parts: list[str] = []

    if card.get("background"):
        extra_parts.append(f"【背景经历】\n{card['background']}")

    if card.get("personality"):
        extra_parts.append(f"【性格详述】\n{card['personality']}")

    if card.get("dialogue_corpus"):
        extra_parts.append(f"【说话方式与语料库】\n{card['dialogue_corpus']}")

    if card.get("relationships"):
        extra_parts.append(f"【重要关系】\n{card['relationships']}")

    if card.get("boundaries"):
        extra_parts.append(f"【行为边界】\n{card['boundaries']}")

    other = card.get("other_sections", {})
    if other:
        parts = []
        for k, v in other.items():
            parts.append(f"【{k}】\n{v}")
        extra_parts.extend(parts)

    extra = "\n\n".join(extra_parts) if extra_parts else ""

    profile = CharacterProfile(
        agent_id=agent_id or f"card_{re.sub(r'\s+', '_', name)}_{age}",
        name=name,
        name_jp=name_jp or name,
        age=age,
        appearance=card.get("appearance", "").strip(),
        personality=card.get("personality", "").strip()[:300] if card.get("personality") else "",
        magic=card.get("magic", "").strip(),
        daily_habits="",
        play_core=play_core,
        secret=secret,
        witch_motive="",
        system_prompt="",
    )
    profile.system_prompt = CharacterProfile.build_system_prompt(profile, extra)
    CHARACTERS[profile.agent_id] = profile
    return profile
