import os
import logging
from collections import deque
from datetime import datetime, timezone
from flask import Flask, redirect, url_for, session, request, jsonify
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from models import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

socketio = SocketIO()
scheduler = BackgroundScheduler()

# In-memory log store: deque of (timestamp, level, module, message)
_log_buffer = deque(maxlen=500)


class MemoryLogHandler(logging.Handler):
    def emit(self, record):
        _log_buffer.append({
            "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": self.format(record),
        })


_mem_handler = MemoryLogHandler()
_mem_handler.setFormatter(logging.Formatter("%(message)s"))
_mem_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_mem_handler)

# Also capture werkzeug access logs (prevent duplicate via propagation)
logging.getLogger("werkzeug").addHandler(_mem_handler)
logging.getLogger("werkzeug").propagate = False
logging.getLogger("apscheduler").addHandler(_mem_handler)
logging.getLogger("apscheduler").propagate = False


def get_logs(limit=200, level=None):
    """Return recent log entries, optionally filtered by level."""
    logs = list(_log_buffer)
    if level:
        logs = [l for l in logs if l["level"].upper() == level.upper()]
    return logs[-limit:]


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(os.path.join(app.instance_path), exist_ok=True)

    db.init_app(app)
    socketio.init_app(app)

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.contestant import contestant_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(contestant_bp, url_prefix="/contestant")

    @app.route("/")
    def index():
        if "user_id" in session:
            if session.get("role") == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("contestant.dashboard"))
        return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_user():
        from models.models import User

        if "user_id" in session:
            user = db.session.get(User, session["user_id"])
            return {"current_user": user}
        return {"current_user": None}

    with app.app_context():
        db.create_all()
        _migrate_database(app)
        _seed_admin(app)
        _start_scheduler(app)

    return app


def _migrate_database(app):
    """Add missing columns/tables for existing databases (SQLite-safe)."""
    from sqlalchemy import text, inspect

    with app.app_context():
        conn = db.engine.connect()
        inspector = inspect(db.engine)

        # challenges.challenge_type
        cols = [c["name"] for c in inspector.get_columns("challenges")]
        if "challenge_type" not in cols:
            conn.execute(text("ALTER TABLE challenges ADD COLUMN challenge_type VARCHAR(20) DEFAULT 'docker'"))
            conn.commit()
            logger.info("Migration: added challenges.challenge_type")

        # scores.answers
        score_cols = [c["name"] for c in inspector.get_columns("scores")]
        if "answers" not in score_cols:
            conn.execute(text("ALTER TABLE scores ADD COLUMN answers TEXT DEFAULT ''"))
            conn.commit()
            logger.info("Migration: added scores.answers")

        # exam_questions table
        if "exam_questions" not in inspector.get_table_names():
            from models.models import ExamQuestion
            ExamQuestion.__table__.create(db.engine, checkfirst=True)
            conn.commit()
            logger.info("Migration: created exam_questions table")

        conn.close()


def _seed_admin(app):
    from models.models import User
    import bcrypt

    admin = db.session.execute(
        db.select(User).where(User.username == "admin")
    ).scalar_one_or_none()

    if not admin:
        pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        admin = User(username="admin", password_hash=pw, role="admin", team_name="管理员")
        db.session.add(admin)
        db.session.commit()


def _start_scheduler(app):
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    if scheduler.running:
        return
    from services.judge_service import judge_all_for_competition
    from services.environment_service import stop_all_environments, remove_all_environments
    from models.models import Competition, Environment

    def auto_judge_job():
        with app.app_context():
            active_comps = Competition.query.filter_by(status="active").all()
            for comp in active_comps:
                try:
                    result = judge_all_for_competition(comp.id)
                    logger.info(f"Auto-judge [{comp.name}]: judged={result['judged']}, passed={result['passed']}")
                except Exception as e:
                    logger.error(f"Auto-judge error [{comp.name}]: {e}")

    def auto_cleanup_job():
        """Auto-judge and clean up environments for finished competitions."""
        with app.app_context():
            finished_comps = Competition.query.filter_by(status="finished").all()
            for comp in finished_comps:
                # Check if there are any non-removed environments
                active_envs = Environment.query.filter_by(competition_id=comp.id).filter(
                    ~Environment.status.in_(["removed"])
                ).count()
                if active_envs == 0:
                    continue

                logger.info(f"Auto-cleanup [{comp.name}]: judging remaining environments...")
                try:
                    judge_result = judge_all_for_competition(comp.id)
                    logger.info(f"Auto-cleanup [{comp.name}]: judged={judge_result['judged']}, passed={judge_result['passed']}")
                except Exception as e:
                    logger.error(f"Auto-cleanup judge error [{comp.name}]: {e}")

                try:
                    stop_result = stop_all_environments(comp.id)
                    logger.info(f"Auto-cleanup [{comp.name}]: stopped {stop_result['stopped']} containers")
                except Exception as e:
                    logger.error(f"Auto-cleanup stop error [{comp.name}]: {e}")

                try:
                    remove_result = remove_all_environments(comp.id)
                    logger.info(f"Auto-cleanup [{comp.name}]: removed {remove_result['removed']} containers")
                except Exception as e:
                    logger.error(f"Auto-cleanup remove error [{comp.name}]: {e}")

    scheduler.add_job(
        auto_judge_job,
        "interval",
        seconds=app.config.get("JUDGE_INTERVAL_SECONDS", 30),
        id="auto_judge",
        replace_existing=True,
    )
    scheduler.add_job(
        auto_cleanup_job,
        "interval",
        seconds=app.config.get("CLEANUP_INTERVAL_SECONDS", 120),
        id="auto_cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Auto-judge scheduler started (interval: {app.config.get('JUDGE_INTERVAL_SECONDS', 30)}s)")
    logger.info(f"Auto-cleanup scheduler started (interval: {app.config.get('CLEANUP_INTERVAL_SECONDS', 120)}s)")


if __name__ == "__main__":
    # Prevent double-import: when "python app.py" runs, __name__ is "__main__".
    # Later, "from app import socketio" inside route modules would trigger a fresh
    # import of app.py as "app", creating a second uninitialized SocketIO instance.
    # Alias __main__ as "app" so both import paths resolve to the same module.
    import sys as _sys
    _sys.modules["app"] = _sys.modules["__main__"]

    app = create_app()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
