"""
Astral — 多 Agent 互动小说 Web 引擎 v0.6
Flask 入口：路由已拆分为 blueprints/
"""
from flask import Flask
from flask_socketio import SocketIO
from debug import install_all

app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                    ping_timeout=30, ping_interval=10, max_http_buffer_size=5_000_000)

from blueprints.prologue import prologue_bp
from blueprints.game import game_bp
from blueprints.trial import trial_bp
from blueprints.save import save_bp
from blueprints.settings import settings_bp
from blueprints.meta import meta_bp

app.register_blueprint(prologue_bp)
app.register_blueprint(game_bp)
app.register_blueprint(trial_bp)
app.register_blueprint(save_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(meta_bp)

# 联机 Socket.IO 事件处理（延迟导入避免循环依赖）
def _register_multiplayer():
    from blueprints.multiplayer import register_events
    register_events(socketio)

def main():
    print("=" * 50)
    print("  Astral v1.1.0-alpha — 多 Agent 互动小说引擎")
    print("  3 场景 · 12 NPC · 47 API · 6 Blueprints")
    print("  http://127.0.0.1:8640")
    print("=" * 50)
    install_all(app)
    _register_multiplayer()
    socketio.run(app, host="0.0.0.0", port=8640, debug=False, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    main()
