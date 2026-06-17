import os
import logging
from collections import deque
from datetime import datetime, timezone
from flask import Flask, redirect, url_for, session, request, jsonify, render_template, flash
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from models import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

socketio = SocketIO()
scheduler = BackgroundScheduler()

# 内存日志存储：双端队列 (时间戳, 级别, 模块, 消息)
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

# 同时捕获 werkzeug 访问日志（禁止传播避免重复）
logging.getLogger("werkzeug").addHandler(_mem_handler)
logging.getLogger("werkzeug").propagate = False
logging.getLogger("apscheduler").addHandler(_mem_handler)
logging.getLogger("apscheduler").propagate = False


def get_logs(limit=200, level=None):
    """返回最近的日志条目，可按级别过滤。"""
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

    @app.route("/presets")
    def presets():
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            flash("需要管理员权限", "error")
            return redirect(url_for("contestant.dashboard"))
        from data.presets import PRESETS
        from docker_engine.builder import get_available_templates
        return render_template("presets.html", presets=PRESETS, templates=get_available_templates())

    @app.route("/presets/create", methods=["POST"])
    def create_preset():
        if "user_id" not in session or session.get("role") != "admin":
            flash("需要管理员权限", "error")
            return redirect(url_for("auth.login"))
        from data.presets import PRESETS

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        login_info = request.form.get("login_info", "").strip()
        judge_type = request.form.get("judge_type", "port")
        judge_config = request.form.get("judge_config", "{}").strip()
        dockerfile_content = request.form.get("dockerfile_content", "").strip()
        category = request.form.get("category", "自定义").strip()
        difficulty = request.form.get("difficulty", "基础").strip()

        if not title:
            flash("题目标题不能为空", "error")
            return redirect(url_for("presets"))

        new_id = max((p["id"] for p in PRESETS), default=-1) + 1
        PRESETS.append({
            "id": new_id,
            "title": title,
            "description": description,
            "category": category,
            "difficulty": difficulty,
            "login_info": login_info,
            "judge_type": judge_type,
            "judge_config": judge_config,
            "dockerfile_content": dockerfile_content,
        })
        flash(f"题库题目「{title}」创建成功", "success")
        return redirect(url_for("presets"))

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
        _sync_orphan_containers(app)
        _start_scheduler(app)

    return app


def _migrate_database(app):
    """为已有数据库添加缺失的列/表（SQLite 安全迁移）。"""
    from sqlalchemy import text, inspect

    with app.app_context():
        conn = db.engine.connect()
        inspector = inspect(db.engine)

        # 题目类型字段
        cols = [c["name"] for c in inspector.get_columns("challenges")]
        if "challenge_type" not in cols:
            conn.execute(text("ALTER TABLE challenges ADD COLUMN challenge_type VARCHAR(20) DEFAULT 'docker'"))
            conn.commit()
            logger.info("Migration: added challenges.challenge_type")

        # 答卷答案字段
        score_cols = [c["name"] for c in inspector.get_columns("scores")]
        if "answers" not in score_cols:
            conn.execute(text("ALTER TABLE scores ADD COLUMN answers TEXT DEFAULT ''"))
            conn.commit()
            logger.info("Migration: added scores.answers")

        # 题目登录信息字段
        chal_cols = [c["name"] for c in inspector.get_columns("challenges")]
        if "login_info" not in chal_cols:
            conn.execute(text("ALTER TABLE challenges ADD COLUMN login_info VARCHAR(200) DEFAULT ''"))
            conn.commit()
            logger.info("Migration: added challenges.login_info")

        # 自动部署标记和部署时间字段
        comp_cols = [c["name"] for c in inspector.get_columns("competitions")]
        if "auto_deployed" not in comp_cols:
            conn.execute(text("ALTER TABLE competitions ADD COLUMN auto_deployed BOOLEAN DEFAULT 0"))
            conn.commit()
            logger.info("Migration: added competitions.auto_deployed")
        if "deployed_at" not in comp_cols:
            conn.execute(text("ALTER TABLE competitions ADD COLUMN deployed_at DATETIME"))
            conn.commit()
            logger.info("Migration: added competitions.deployed_at")

        # 环境 Web 端口字段
        env_cols = [c["name"] for c in inspector.get_columns("environments")]
        if "web_port" not in env_cols:
            conn.execute(text("ALTER TABLE environments ADD COLUMN web_port INTEGER DEFAULT 0"))
            conn.commit()
            logger.info("Migration: added environments.web_port")

        # 试卷题目表
        if "exam_questions" not in inspector.get_table_names():
            from models.models import ExamQuestion
            ExamQuestion.__table__.create(db.engine, checkfirst=True)
            conn.commit()
            logger.info("Migration: created exam_questions table")

        conn.close()


def _sync_orphan_containers(app):
    """启动时将 Docker 中已有但数据库未记录的 comp-* 容器同步入库。
    容器命名格式：comp-{竞赛ID}-u{用户ID}-c{题目ID}"""
    from models.models import Environment, Challenge, Competition, User
    import re

    try:
        from docker_engine.manager import get_client
        client = get_client()
    except Exception:
        logger.info("Sync containers: Docker unavailable, skipping")
        return

    try:
        containers = client.containers.list(all=True, sparse=True)
    except Exception as e:
        logger.warning(f"Sync containers: failed to list containers: {e}")
        return

    pattern = re.compile(r"^comp-(\d+)-u(\d+)-c(\d+)$")
    synced = 0

    for c in containers:
        name = c.name
        match = pattern.match(name)
        if not match:
            continue

        comp_id = int(match.group(1))
        user_id = int(match.group(2))
        challenge_id = int(match.group(3))

        # 检查数据库是否已有此环境记录
        existing = Environment.query.filter_by(
            competition_id=comp_id,
            user_id=user_id,
            challenge_id=challenge_id,
        ).first()
        if existing:
            continue

        # 验证关联记录存在
        comp = db.session.get(Competition, comp_id)
        user = db.session.get(User, user_id)
        chal = db.session.get(Challenge, challenge_id)
        if not all([comp, user, chal]):
            logger.warning(f"Sync containers: skipping orphan {name} (missing comp/user/chal)")
            continue

        # 获取容器实际状态和端口映射
        host_port = 0
        web_port = 0
        status = "running"
        try:
            cinfo = client.containers.get(c.name)
            status = cinfo.status
            # 解析端口映射：Docker 返回 "30000/tcp" -> [{"HostPort": "30000"}]
            ports = cinfo.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
            for container_port, bindings in ports.items():
                if bindings and isinstance(bindings, list) and len(bindings) > 0:
                    hp = int(bindings[0].get("HostPort", 0))
                    if "22/tcp" in container_port:
                        host_port = hp
                    elif "80/tcp" in container_port or "443/tcp" in container_port or "5000/tcp" in container_port:
                        web_port = hp
                    elif web_port == 0 and hp > 0:
                        web_port = hp  # 兜底：最后一个非 22 的端口
        except Exception:
            pass

        env = Environment(
            competition_id=comp_id,
            user_id=user_id,
            challenge_id=challenge_id,
            container_id=c.name,  # 用容器名作为标识
            container_name=name,
            host_port=host_port,
            web_port=web_port,
            status=status,
        )
        db.session.add(env)
        synced += 1
        logger.info(f"Sync containers: recovered {name} (status={status}, port={host_port})")

    if synced > 0:
        db.session.commit()
        logger.info(f"Sync containers: {synced} orphan containers recovered to database")
    else:
        logger.info("Sync containers: no orphans found")


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
    from services.environment_service import stop_all_environments, remove_all_environments, deploy_competition_environments
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

    def auto_build_job():
        """为已激活但尚未部署的竞赛自动部署环境。"""
        with app.app_context():
            from datetime import datetime, timezone
            active_comps = Competition.query.filter_by(status="active", auto_deployed=False).all()
            for comp in active_comps:
                try:
                    logger.info(f"Auto-build [{comp.name}]: starting automatic deployment...")
                    result = deploy_competition_environments(comp.id, socketio=socketio)
                    comp.auto_deployed = True
                    comp.deployed_at = datetime.now(timezone.utc)
                    db.session.commit()
                    succ = result.get('success', 0)
                    fail = result.get('failed', 0)
                    # 若返回 error 字段说明部署前置条件不满足（无选手/无题目等）
                    if result.get("error"):
                        logger.info(f"Auto-build [{comp.name}]: skipped ({result['error']})")
                        socketio.emit("auto_deploy_done", {
                            "competition": comp.name,
                            "success": 0,
                            "failed": 0,
                            "error": result["error"],
                        })
                    else:
                        logger.info(f"Auto-build [{comp.name}]: success={succ}, failed={fail}")
                        socketio.emit("auto_deploy_done", {
                            "competition": comp.name,
                            "success": succ,
                            "failed": fail,
                        })
                except Exception as e:
                    logger.error(f"Auto-build error [{comp.name}]: {e}")
                    socketio.emit("auto_deploy_done", {
                        "competition": comp.name,
                        "success": 0,
                        "failed": 0,
                        "error": str(e),
                    })

    def auto_image_build_job():
        """为未构建镜像的 Docker 题目后台构建镜像，通过 SocketIO 推送通知。"""
        with app.app_context():
            from models.models import Challenge
            from docker_engine.builder import build_challenge_image
            # 查找所有 docker 类型且尚未构建镜像的题目
            unbuilt = Challenge.query.filter_by(challenge_type="docker").filter(
                Challenge.image_tag == ""
            ).all()
            for challenge in unbuilt:
                try:
                    logger.info(f"Image build: starting for challenge {challenge.id} '{challenge.title}'")
                    result = build_challenge_image(challenge.id, challenge.dockerfile_content)
                    if result["success"]:
                        challenge.image_tag = result["image_tag"]
                        db.session.commit()
                        logger.info(f"Image build: success for challenge {challenge.id}, tag={result['image_tag']}")
                        socketio.emit("image_build_done", {
                            "challenge_id": challenge.id,
                            "title": challenge.title,
                            "success": True,
                            "image_tag": result["image_tag"],
                            "error": "",
                        })
                    else:
                        logger.error(f"Image build: failed for challenge {challenge.id}: {result['error']}")
                        socketio.emit("image_build_done", {
                            "challenge_id": challenge.id,
                            "title": challenge.title,
                            "success": False,
                            "image_tag": "",
                            "error": result["error"],
                        })
                except Exception as e:
                    logger.error(f"Image build: exception for challenge {challenge.id}: {e}")
                    try:
                        socketio.emit("image_build_done", {
                            "challenge_id": challenge.id,
                            "title": challenge.title,
                            "success": False,
                            "image_tag": "",
                            "error": str(e),
                        })
                    except Exception:
                        pass

    def auto_cleanup_job():
        """对已结束的竞赛执行自动判题并清理环境。"""
        with app.app_context():
            finished_comps = Competition.query.filter_by(status="finished").all()
            for comp in finished_comps:
                # 检查是否还有未移除的环境
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
        auto_build_job,
        "interval",
        seconds=app.config.get("AUTO_BUILD_INTERVAL_SECONDS", 15),
        id="auto_build",
        replace_existing=True,
    )
    scheduler.add_job(
        auto_image_build_job,
        "interval",
        seconds=app.config.get("IMAGE_BUILD_INTERVAL_SECONDS", 30),
        id="auto_image_build",
        replace_existing=True,
    )
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
    logger.info(f"Auto-build scheduler started (interval: {app.config.get('AUTO_BUILD_INTERVAL_SECONDS', 15)}s)")
    logger.info(f"Auto-image-build scheduler started (interval: {app.config.get('IMAGE_BUILD_INTERVAL_SECONDS', 30)}s)")
    logger.info(f"Auto-judge scheduler started (interval: {app.config.get('JUDGE_INTERVAL_SECONDS', 30)}s)")
    logger.info(f"Auto-cleanup scheduler started (interval: {app.config.get('CLEANUP_INTERVAL_SECONDS', 120)}s)")


if __name__ == "__main__":
    # 防止重复导入：当 "python app.py" 运行时，__name__ 为 "__main__"。
    # 后续路由模块中 "from app import socketio" 会以 "app" 名称再次导入
    # app.py，创建第二个未初始化的 SocketIO 实例。
    # 将 __main__ 别名为 "app"，使两个导入路径指向同一模块。
    import sys as _sys
    _sys.modules["app"] = _sys.modules["__main__"]

    app = create_app()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
