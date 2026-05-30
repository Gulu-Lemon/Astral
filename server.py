"""
Astral — 多 Agent 互动小说 Web 引擎 v0.6
Flask 入口：路由已拆分为 blueprints/
"""
from flask import Flask
from debug import install_all

app = Flask(__name__, static_folder="static", static_url_path="")

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

def main():
    print("=" * 50)
    print("  Astral v0.6 — 多 Agent 互动小说引擎")
    print("  3 场景 · 12 NPC · 37 API · 6 Blueprints")
    print("  http://127.0.0.1:8640")
    print("=" * 50)
    install_all(app)
    app.run(host="0.0.0.0", port=8640, debug=False, threaded=True)

if __name__ == "__main__":
    main()
