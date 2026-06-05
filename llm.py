"""
LLM 客户端封装 — 支持 OpenAI 兼容 API（线程安全）
"""
from __future__ import annotations
import json
import os
import threading
from typing import Optional


class LLMClient:
    def __init__(self, config_path: str = ""):
        self._config_path = config_path
        self.default_temperature: float = 1.0
        self.default_top_p: float = 0.95
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.base_url: str = cfg.get("api_base_url", "").rstrip("/")
            self.api_key: str = cfg.get("api_key", "")
            self.model: str = cfg.get("model_name", "")
        else:
            self.base_url = ""
            self.api_key = ""
            self.model = ""
        self._local = threading.local()
        self.thinking_enabled: bool = False
        self.thinking_budget: int = 0

    def _get_client(self):
        """获取当前线程的 httpx.Client（线程局部，延迟创建）"""
        import httpx
        if not hasattr(self._local, "client") or self._local.client is None:
            self._local.client = httpx.Client(timeout=120.0)
        return self._local.client

    def chat(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 2048,
        top_p: Optional[float] = None,
    ) -> str:
        if not self.api_key or not self.api_key.strip():
            raise ValueError("API Key 未配置。请在设置中添加并选择一个 API 配置。")
        if not self.base_url or not self.base_url.strip():
            raise ValueError("API 地址未配置。请在设置中添加并选择一个 API 配置。")
        if not self.model or not self.model.strip():
            raise ValueError("模型名未配置。请在设置中添加并选择一个 API 配置。")

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens,
            "top_p": top_p if top_p is not None else self.default_top_p,
        }
        if self.thinking_enabled:
            payload["thinking"] = {"type": "enabled"}
            if self.thinking_budget > 0:
                payload["thinking"]["budget_tokens"] = self.thinking_budget
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            if not resp.text or not resp.text.strip():
                raise ValueError("API 返回了空响应")
            data = resp.json()
        except Exception as e:
            msg = f"API 调用失败。URL: {self.base_url}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f"，HTTP {e.response.status_code}: {e.response.text[:200]}"
            elif str(e).strip():
                msg += f"，错误: {str(e)[:200]}"
            raise ValueError(msg) from e
        return data["choices"][0]["message"]["content"].strip()

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 2048,
    ):
        """流式聊天 — 逐 token 生成文本块（生成器）"""
        if not self.api_key or not self.api_key.strip():
            raise ValueError("API Key 未配置。请在设置中添加并选择一个 API 配置。")
        if not self.base_url or not self.base_url.strip():
            raise ValueError("API 地址未配置。请在设置中添加并选择一个 API 配置。")
        if not self.model or not self.model.strip():
            raise ValueError("模型名未配置。请在设置中添加并选择一个 API 配置。")

        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if self.thinking_enabled:
            payload["thinking"] = {"type": "enabled"}
            if self.thinking_budget > 0:
                payload["thinking"]["budget_tokens"] = self.thinking_budget
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                        continue
        except Exception as e:
            msg = f"流式 API 调用失败。URL: {self.base_url}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f"，HTTP {e.response.status_code}: {e.response.text[:200]}"
            elif str(e).strip():
                msg += f"，错误: {str(e)[:200]}"
            raise ValueError(msg) from e

    def chat_json(
        self,
        messages: list[dict[str, str]],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 2048,
    ) -> dict:
        """请求结构化的 JSON 输出"""
        json_instruction = "\n\n重要：你必须只输出一个有效的 JSON 对象，不要带任何 markdown 标记、解释、额外文字、或前后缀。直接输出 JSON。"
        effective_system = (system or "") + json_instruction
        text = self.chat(
            messages, system=effective_system,
            temperature=temperature, max_tokens=max_tokens
        )
        return self._extract_json(text.strip())

    @staticmethod
    def _extract_json(raw: str) -> dict:
        """从可能包含 markdown 或额外文本的响应中提取 JSON"""
        import re

        # 移除 markdown 代码块标记
        text = raw
        code_block = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if code_block:
            text = code_block.group(1).strip()

        # 尝试找到第一个 { 和最后一个 }
        first = text.find('{')
        last = text.rfind('}')
        if first != -1 and last > first:
            text = text[first:last + 1]

        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试用 ast.literal_eval (处理单引号)
        try:
            import ast
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            pass

        # 修复单引号
        try:
            fixed = text.replace("'", '"')
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 截断修复：补全缺失的括号和引号（在原始文本上操作）
        try:
            full = raw
            code_block2 = re.search(r'```(?:json)?\s*\n?(.*?)```', full, re.DOTALL)
            if code_block2:
                full = code_block2.group(1).strip()
            first2 = full.find('{')
            if first2 != -1:
                full = full[first2:]
            brace_diff = full.count('{') - full.count('}')
            bracket_diff = full.count('[') - full.count(']')
            in_string = False
            escaped = False
            for ch in full:
                if escaped: escaped = False; continue
                if ch == '\\': escaped = True; continue
                if ch == '"': in_string = not in_string
            fixed = full
            if in_string:
                fixed += '"'
            # 关闭顺序：N-1 个内部对象 → 全部数组 → 最外层对象
            if brace_diff > 0:
                inner = max(0, brace_diff - 1)
                fixed += '}' * inner
            fixed += ']' * bracket_diff
            if brace_diff > 0:
                fixed += '}'
            return json.loads(fixed)
        except (json.JSONDecodeError, Exception):
            pass

        raise ValueError(f"LLM 返回了空响应或非 JSON 内容，无法提取: {raw[:200]}")

    def close(self):
        if hasattr(self._local, "client") and self._local.client is not None:
            self._local.client.close()
            self._local.client = None

    def set_model(self, model_name: str):
        """运行时切换模型名（线程安全：model 是实例属性，所有线程读取同一值）"""
        self.model = model_name.strip()

    def reload_config(self, config_path: str = ""):
        """重新加载配置（API key等）"""
        path = config_path or self._config_path or "config.json"
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.base_url = cfg["api_base_url"].rstrip("/")
        self.api_key = cfg["api_key"]
        self.model = cfg["model_name"]
        self._config_path = path
        # 清理旧连接
        self.close()
