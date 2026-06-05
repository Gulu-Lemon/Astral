"""
Debug 模块 — 请求日志 · 异常捕获 · Agent 决策日志
"""
from __future__ import annotations
import os
import sys
import time
import json
import threading
import traceback
from datetime import datetime
from functools import wraps

_BASE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)

LOG_DIR = os.path.join(_BASE, "logs")


def _ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


class RingBuffer:
    """固定容量的环形缓冲，避免日志文件无限增长"""
    def __init__(self, path: str, max_lines: int = 5000):
        self.path = path
        self.max_lines = max_lines

    def write(self, line: str):
        _ensure_dir()
        lines = []
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                lines = []
        lines.append(line)
        if len(lines) > self.max_lines:
            lines = lines[-self.max_lines:]
        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)


class RequestLogger:
    """方案一：Flask 请求日志中间件"""

    def __init__(self, app, log_file: str = "requests.log"):
        self.log = RingBuffer(os.path.join(LOG_DIR, log_file))
        app.before_request(self._before)
        app.after_request(self._after)

    def _before(self):
        from flask import request, g
        g._req_start = time.time()
        g._req_id = datetime.now().strftime("%H%M%S") + str(int(time.time() * 1000) % 1000)

    def _after(self, response):
        from flask import request, g
        elapsed = (time.time() - getattr(g, "_req_start", time.time())) * 1000
        rid = getattr(g, "_req_id", "????")
        body = ""
        if request.is_json and request.get_data():
            raw = request.get_data(as_text=True)[:200]
            body = f" body={raw}"
        line = f"[{rid}] {request.method} {request.path} -> {response.status_code} ({elapsed:.0f}ms){body}\n"
        self.log.write(line)
        return response


class ExceptionCatcher:
    """方案二：全局异常捕获，写入日志"""

    def __init__(self, app, log_file: str = "errors.log"):
        self.log = RingBuffer(os.path.join(LOG_DIR, log_file))
        app.register_error_handler(Exception, self._handler)
        # 拦截所有未捕获的线程异常
        self._install_thread_hook()

    def _handler(self, exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc  # 让 Flask 正常处理 404/405 等 HTTP 错误
        tb = traceback.format_exc()
        stamp = datetime.now().isoformat()
        entry = f"\n{'='*60}\n[{stamp}] UNCAUGHT EXCEPTION\n{tb}\n{'='*60}\n"
        self.log.write(entry)
        print(f"\n[ERROR] {exc}\n{tb[:300]}", file=sys.stderr, flush=True)
        return {"ok": False, "error": str(exc), "trace": tb[:500]}, 500

    def _install_thread_hook(self):
        original = threading.Thread._bootstrap_inner

        def patched_bootstrap_inner(self_):
            try:
                original(self_)
            except Exception as exc:
                tb = traceback.format_exc()
                stamp = datetime.now().isoformat()
                entry = f"\n{'='*60}\n[{stamp}] THREAD EXCEPTION (thread={self_.name})\n{tb}\n{'='*60}\n"
                log = RingBuffer(os.path.join(LOG_DIR, "thread_errors.log"))
                log.write(entry)
                print(f"\n[THREAD ERROR] {self_.name}: {exc}\n{tb[:300]}", file=sys.stderr, flush=True)
                raise

        threading.Thread._bootstrap_inner = patched_bootstrap_inner


class AgentLogger:
    """方案三：Agent 决策日志"""

    def __init__(self, log_file: str = "agents.log"):
        self.log = RingBuffer(os.path.join(LOG_DIR, log_file))
        self._lock = threading.Lock()

    def log_decision(self, agent_id: str, name: str, intent: str, target: str,
                     reasoning: str, emotion: str, error: str = ""):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {agent_id} {name} | {intent}"
        if target:
            line += f" -> {target}"
        line += f" | {emotion}"
        if reasoning:
            line += f" | {reasoning[:100]}"
        if error:
            line += f" | ERROR: {error}"
        line += "\n"
        with self._lock:
            self.log.write(line)

    def log_round_start(self, round_num: int):
        line = f"\n{'─'*50}\n[ROUND {round_num}]\n"
        with self._lock:
            self.log.write(line)

    def log_arbiter(self, rulings_summary: list[str]):
        lines = "".join(f"  [ARBITER] {s}\n" for s in rulings_summary[:20])
        with self._lock:
            self.log.write(lines)

    def log_narrative(self, text_preview: str):
        line = f"  [GM] {text_preview[:120].replace(chr(10), ' ')}...\n"
        with self._lock:
            self.log.write(line)


# ====== 便捷初始化 ======

def install_all(app) -> tuple[RequestLogger, ExceptionCatcher, AgentLogger]:
    req_logger = RequestLogger(app)
    exc_catcher = ExceptionCatcher(app)
    agent_logger = AgentLogger()
    print(f"  [Debug] 日志目录: {LOG_DIR}")
    return req_logger, exc_catcher, agent_logger
