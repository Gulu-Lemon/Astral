"""
API 配置管理 — config_profiles.json 多配置支持
"""
import json
import os
import sys
from typing import Optional

_BASE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)

PROFILES_PATH = os.path.join(_BASE, "config_profiles.json")


def _ensure():
    if not os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump({"profiles": [], "active": ""}, f, indent=2)


def get_active() -> dict:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_name = data.get("active", "")
    for p in data.get("profiles", []):
        if p.get("name") == active_name:
            return {
                "name": p["name"].strip(),
                "base_url": p.get("base_url", "").strip(),
                "api_key": p.get("api_key", "").strip(),
                "model": p.get("model", "").strip(),
                "temperature": p.get("temperature", 1.0),
                "top_p": p.get("top_p", 0.95),
                "agent_model": p.get("agent_model", "").strip(),
                "arbiter_model": p.get("arbiter_model", "").strip(),
                "gm_model": p.get("gm_model", "").strip(),
                "thinking_mode": p.get("thinking_mode", False),
                "thinking_budget": p.get("thinking_budget", 0),
                "agent_thinking": p.get("agent_thinking", p.get("thinking_mode", False)),
                "arbiter_thinking": p.get("arbiter_thinking", p.get("thinking_mode", False)),
                "gm_thinking": p.get("gm_thinking", False),
            }
    return {}


def list_profiles() -> list[dict]:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_name = data.get("active", "")
    profiles = []
    for p in data.get("profiles", []):
        entry = {
            "name": p.get("name", "").strip(),
            "base_url": p.get("base_url", "").strip(),
            "model": p.get("model", "").strip(),
            "temperature": p.get("temperature", 1.0),
            "top_p": p.get("top_p", 0.95),
            "agent_model": p.get("agent_model", "").strip(),
            "arbiter_model": p.get("arbiter_model", "").strip(),
            "gm_model": p.get("gm_model", "").strip(),
            "thinking_mode": p.get("thinking_mode", False),
            "thinking_budget": p.get("thinking_budget", 0),
            "agent_thinking": p.get("agent_thinking", p.get("thinking_mode", False)),
            "arbiter_thinking": p.get("arbiter_thinking", p.get("thinking_mode", False)),
            "gm_thinking": p.get("gm_thinking", False),
        }
        entry["has_key"] = bool(p.get("api_key", "").strip())
        entry["active"] = p.get("name") == active_name
        profiles.append(entry)
    return profiles


def save_profile(name: str, base_url: str, api_key: str, model: str,
                 temperature: float = 1.0, top_p: float = 0.95,
                 agent_model: str = "", arbiter_model: str = "", gm_model: str = "",
                 thinking_mode: bool = False, thinking_budget: int = 0,
                 agent_thinking: bool = False, arbiter_thinking: bool = False,
                 gm_thinking: bool = False) -> bool:
    name = name.strip()
    base_url = base_url.strip()
    api_key = api_key.strip()
    model = model.strip() or "gpt-3.5-turbo"
    agent_model = agent_model.strip()
    arbiter_model = arbiter_model.strip()
    gm_model = gm_model.strip()
    try: temperature = float(temperature)
    except (ValueError, TypeError): temperature = 1.0
    try: top_p = float(top_p)
    except (ValueError, TypeError): top_p = 0.95
    try: thinking_budget = int(thinking_budget)
    except (ValueError, TypeError): thinking_budget = 0
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    profiles = data.get("profiles", [])
    for i, p in enumerate(profiles):
        if p.get("name") == name:
            old_key = p.get("api_key", "")
            profiles[i] = {
                "name": name, "base_url": base_url,
                "api_key": api_key if api_key else old_key,
                "model": model,
                "temperature": temperature,
                "top_p": top_p,
                "agent_model": agent_model,
                "arbiter_model": arbiter_model,
                "gm_model": gm_model,
                "thinking_mode": thinking_mode,
                "thinking_budget": thinking_budget,
                "agent_thinking": agent_thinking,
                "arbiter_thinking": arbiter_thinking,
                "gm_thinking": gm_thinking,
            }
            break
    else:
        profiles.append({"name": name, "base_url": base_url, "api_key": api_key, "model": model,
            "temperature": temperature, "top_p": top_p,
            "agent_model": agent_model, "arbiter_model": arbiter_model, "gm_model": gm_model,
            "thinking_mode": thinking_mode, "thinking_budget": thinking_budget,
            "agent_thinking": agent_thinking, "arbiter_thinking": arbiter_thinking,
            "gm_thinking": gm_thinking})
    # 如果没有 active，自动设为这个
    if not data.get("active"):
        data["active"] = name
    data["profiles"] = profiles
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def activate(name: str) -> bool:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for p in data.get("profiles", []):
        if p.get("name") == name:
            data["active"] = name
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
    return False


def delete_profile(name: str) -> bool:
    _ensure()
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["profiles"] = [p for p in data.get("profiles", []) if p.get("name") != name]
    if data.get("active") == name:
        data["active"] = data["profiles"][0]["name"] if data["profiles"] else ""
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def apply_to_llm(llm) -> bool:
    """将当前 active 配置应用到单个 LLMClient"""
    cfg = get_active()
    if not cfg:
        return False
    llm.base_url = cfg["base_url"].strip().rstrip("/")
    llm.api_key = cfg["api_key"].strip()
    llm.model = cfg["model"].strip()
    llm.default_temperature = cfg.get("temperature", 1.0)
    llm.default_top_p = cfg.get("top_p", 0.95)
    llm.thinking_enabled = cfg.get("thinking_mode", False)
    llm.thinking_budget = cfg.get("thinking_budget", 0)
    llm.close()
    return True


def apply_to_all_llms(base_llm, agent_llm, gm_llm) -> bool:
    """将 active 配置应用到所有 LLM 实例，并按角色覆盖模型"""
    cfg = get_active()
    if not cfg:
        return False
    base_url = cfg["base_url"].strip().rstrip("/")
    api_key = cfg["api_key"].strip()
    default_model = cfg["model"].strip()
    temperature = cfg.get("temperature", 1.0)
    top_p = cfg.get("top_p", 0.95)
    agent_model = cfg.get("agent_model", "").strip()
    arbiter_model = cfg.get("arbiter_model", "").strip()
    gm_model = cfg.get("gm_model", "").strip()
    # 通用设置应用到所有实例
    for llm in (base_llm, agent_llm, gm_llm):
        llm.base_url = base_url
        llm.api_key = api_key
        llm.default_temperature = temperature
        llm.default_top_p = top_p
    # 模型按角色覆盖
    base_llm.model = default_model
    agent_llm.model = agent_model or default_model
    gm_llm.model = gm_model or default_model
    # 思考模式按角色设置
    base_llm.thinking_enabled = cfg.get("thinking_mode", False)
    base_llm.thinking_budget = cfg.get("thinking_budget", 0)
    agent_llm.thinking_enabled = cfg.get("agent_thinking", cfg.get("thinking_mode", False))
    agent_llm.thinking_budget = cfg.get("thinking_budget", 0)
    gm_llm.thinking_enabled = cfg.get("gm_thinking", False)
    gm_llm.thinking_budget = cfg.get("thinking_budget", 0)
    for llm in (base_llm, agent_llm, gm_llm):
        llm.close()
    return True
