import json
import logging
import threading
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from models import db
from models.models import Competition, Challenge, Environment, Score, User, ExamQuestion
from docker_engine.builder import build_image, build_image_from_template, get_image_info, get_available_templates
from docker_engine.manager import get_container_status, start_container, stop_container, remove_container
from data.presets import PRESETS

logger = logging.getLogger(__name__)

OS_IMAGES = {
    "Ubuntu 22.04": "ubuntu:22.04",
    "Ubuntu 20.04": "ubuntu:20.04",
    "Debian 12": "debian:12",
}

DOCKER_INSTALL_CMDS = {
    "Ubuntu 22.04": "RUN apt-get update && apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable\" > /etc/apt/sources.list.d/docker.list && apt-get update && apt-get install -y docker-ce-cli",
    "Ubuntu 20.04": "RUN apt-get update && apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable\" > /etc/apt/sources.list.d/docker.list && apt-get update && apt-get install -y docker-ce-cli",
    "Debian 12": "RUN apt-get update && apt-get install -y ca-certificates curl && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable\" > /etc/apt/sources.list.d/docker.list && apt-get update && apt-get install -y docker-ce-cli",
}

def _inject_docker_install(dockerfile, os_choice):
    """在第一个 apt-get install 行之前注入 Docker CLI 安装命令。"""
    cmd = DOCKER_INSTALL_CMDS.get(os_choice)
    if not cmd:
        return dockerfile
    lines = dockerfile.split("\n")
    result = []
    injected = False
    for line in lines:
        if not injected and "apt-get install" in line:
            result.append(f"# 自动安装 Docker CLI\n{cmd}")
            injected = True
        result.append(line)
    return "\n".join(result)
from services.environment_service import (
    deploy_competition_environments,
    stop_all_environments,
    remove_all_environments,
    get_competition_environments,
)

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            flash("需要管理员权限", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/")
@admin_required
def dashboard():
    comp_count = Competition.query.count()
    active_count = Competition.query.filter_by(status="active").count()
    user_count = User.query.filter_by(role="contestant").count()
    env_count = Environment.query.count()
    running_count = Environment.query.filter_by(status="running").count()

    return render_template("admin/dashboard.html",
                           comp_count=comp_count, active_count=active_count,
                           user_count=user_count, env_count=env_count,
                           running_count=running_count)


@admin_bp.route("/competitions")
@admin_required
def competitions():
    comps = Competition.query.order_by(Competition.created_at.desc()).all()
    return render_template("admin/competitions.html", competitions=comps, presets=PRESETS)


@admin_bp.route("/competitions/create", methods=["POST"])
@admin_required
def create_competition():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")
    cpu_limit = request.form.get("cpu_limit", 0.5)
    mem_limit = request.form.get("mem_limit", "512m")

    if not name:
        flash("竞赛名称不能为空", "error")
        return redirect(url_for("admin.competitions"))

    try:
        comp = Competition(
            name=name,
            description=description,
            start_time=datetime.fromisoformat(start_time) if start_time else datetime.now(),
            end_time=datetime.fromisoformat(end_time) if end_time else datetime.now(),
            cpu_limit=float(cpu_limit),
            mem_limit=mem_limit,
        )
        db.session.add(comp)
        db.session.commit()

        # 从选中的题库预设创建题目
        preset_ids = request.form.getlist("preset_ids")
        logger.info(f"Create competition '{name}': preset_ids={preset_ids}, os={request.form.get('os_choice')}, docker={request.form.get('install_docker')}")
        if preset_ids:
            created = 0
            for pid in preset_ids:
                pid = int(pid)
                preset = next((p for p in PRESETS if p["id"] == pid), None)
                if not preset:
                    continue
                dockerfile = preset["dockerfile_content"]
                # 应用操作系统选择
                os_choice = request.form.get("os_choice", "Ubuntu 22.04")
                os_image = OS_IMAGES.get(os_choice, "ubuntu:22.04")
                dockerfile = dockerfile.replace("FROM ubuntu:22.04", f"FROM {os_image}")
                # 如果勾选了安装 Docker 则注入安装命令
                if request.form.get("install_docker") == "on":
                    dockerfile = _inject_docker_install(dockerfile, os_choice)
                chal = Challenge(
                    competition_id=comp.id,
                    title=preset["title"],
                    description=preset["description"],
                    challenge_type="docker",
                    login_info=preset.get("login_info", ""),
                    judge_type=preset.get("judge_type", "port"),
                    judge_config=preset.get("judge_config", "{}"),
                    dockerfile_content=dockerfile,
                    points=100,
                    order=created + 1,
                )
                db.session.add(chal)
                db.session.flush()  # get chal.id for image tag
                try:
                    success, msg = build_image(chal.id, dockerfile)
                    if success:
                        chal.image_tag = msg
                    else:
                        logger.error(f"Build failed for challenge {chal.id}: {msg}")
                except Exception as e:
                    logger.error(f"Build exception for challenge {chal.id}: {e}")
                created += 1
            db.session.commit()
            flash(f"竞赛创建成功，已从题库添加 {created} 道题目", "success")
        else:
            flash("竞赛创建成功，请进入管理页添加题目", "success")
    except Exception as e:
        flash(f"创建失败: {e}", "error")

    return redirect(url_for("admin.competitions"))


@admin_bp.route("/competitions/<int:comp_id>/edit", methods=["POST"])
@admin_required
def edit_competition(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    comp.name = request.form.get("name", comp.name).strip()
    comp.description = request.form.get("description", comp.description).strip()
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")
    if start_time:
        comp.start_time = datetime.fromisoformat(start_time)
    if end_time:
        comp.end_time = datetime.fromisoformat(end_time)
    comp.cpu_limit = float(request.form.get("cpu_limit", comp.cpu_limit))
    comp.mem_limit = request.form.get("mem_limit", comp.mem_limit)

    db.session.commit()
    flash("竞赛更新成功", "success")
    return redirect(url_for("admin.competitions"))


@admin_bp.route("/competitions/<int:comp_id>/status", methods=["POST"])
@admin_required
def update_competition_status(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    new_status = request.form.get("status", "")
    if new_status in ("draft", "active", "finished"):
        comp.status = new_status
        if new_status == "active":
            comp.auto_deployed = False  # 重置以让调度器重新触发部署
        db.session.commit()

        if new_status == "active":
            flash("竞赛已开始，系统将在 15 秒内自动部署环境", "success")
        else:
            flash(f"竞赛状态已更新为: {new_status}", "success")

    return redirect(url_for("admin.competitions"))


@admin_bp.route("/competitions/<int:comp_id>/delete", methods=["POST"])
@admin_required
def delete_competition(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    remove_all_environments(comp_id)
    # 先删除成绩和题目，避免外键约束冲突
    Score.query.filter_by(competition_id=comp_id).delete()
    Challenge.query.filter_by(competition_id=comp_id).delete()
    db.session.delete(comp)
    db.session.commit()
    flash("竞赛已删除", "success")
    return redirect(url_for("admin.competitions"))


@admin_bp.route("/competitions/<int:comp_id>")
@admin_required
def competition_detail(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    challenges_list = Challenge.query.filter_by(competition_id=comp_id).order_by(Challenge.order).all()
    exam_questions_map = {}
    for chal in challenges_list:
        if chal.challenge_type == "exam":
            exam_questions_map[chal.id] = ExamQuestion.query.filter_by(challenge_id=chal.id).order_by(ExamQuestion.order).all()
    templates = get_available_templates()
    envs = get_competition_environments(comp_id)

    from sqlalchemy import func
    rankings = db.session.query(
        User.id, User.username, User.team_name,
        func.coalesce(func.sum(Score.score), 0).label("total_score"),
        func.count(Score.id).label("solved_count"),
    ).outerjoin(Score, (Score.user_id == User.id) & (Score.competition_id == comp_id) & (Score.passed == True)) \
     .filter(User.role == "contestant") \
     .group_by(User.id).order_by(func.sum(Score.score).desc()).all()

    score_lookup = {}
    for s in Score.query.filter_by(competition_id=comp_id).all():
        score_lookup[(s.user_id, s.challenge_id)] = s

    return render_template("admin/competition_detail.html",
                           competition=comp, challenges=challenges_list,
                           templates=templates, environments=envs,
                           rankings=rankings, score_lookup=score_lookup,
                           exam_questions_map=exam_questions_map,
                           presets=PRESETS)


@admin_bp.route("/competitions/<int:comp_id>/challenges")
@admin_required
def challenges(comp_id):
    return redirect(url_for("admin.competition_detail", comp_id=comp_id))


@admin_bp.route("/competitions/<int:comp_id>/challenges/create", methods=["POST"])
@admin_required
def create_challenge(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    challenge_type = request.form.get("challenge_type", "docker").strip()
    login_info = request.form.get("login_info", "").strip()
    dockerfile_content = request.form.get("dockerfile_content", "").strip()
    template_name = request.form.get("template_name", "").strip()
    judge_type = request.form.get("judge_type", "port")
    judge_config = request.form.get("judge_config", "{}").strip()
    points = int(request.form.get("points", 100))
    order = int(request.form.get("order", 0))

    if not title:
        flash("题目标题不能为空", "error")
        return redirect(url_for("admin.competition_detail", comp_id=comp_id))

    challenge = Challenge(
        competition_id=comp_id,
        title=title,
        description=description,
        challenge_type=challenge_type,
        login_info=login_info,
        dockerfile_content=dockerfile_content,
        judge_type=judge_type,
        judge_config=judge_config,
        points=points,
        order=order,
    )
    db.session.add(challenge)
    db.session.flush()

    if challenge_type == "docker":
        if template_name and not dockerfile_content:
            success, msg = build_image_from_template(template_name, challenge.id)
            if success:
                challenge.image_tag = msg
                import os
                from config import Config
                tpl_path = os.path.join(Config.DOCKER_TEMPLATES_DIR, template_name, "Dockerfile")
                with open(tpl_path) as f:
                    challenge.dockerfile_content = f.read()
            else:
                flash(f"镜像构建失败: {msg}", "error")
        elif dockerfile_content:
            success, msg = build_image(challenge.id, dockerfile_content)
            if success:
                challenge.image_tag = msg
            else:
                flash(f"镜像构建失败: {msg}", "error")

    db.session.commit()
    flash(f"题目「{title}」创建成功", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp_id))


@admin_bp.route("/challenges/<int:challenge_id>/edit", methods=["POST"])
@admin_required
def edit_challenge(challenge_id):
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge:
        flash("题目不存在", "error")
        return redirect(url_for("admin.competitions"))

    challenge.title = request.form.get("title", challenge.title).strip()
    challenge.description = request.form.get("description", challenge.description).strip()
    challenge.challenge_type = request.form.get("challenge_type", challenge.challenge_type)
    challenge.login_info = request.form.get("login_info", challenge.login_info or "").strip()
    challenge.judge_type = request.form.get("judge_type", challenge.judge_type)
    challenge.judge_config = request.form.get("judge_config", challenge.judge_config)
    challenge.points = int(request.form.get("points", challenge.points))
    challenge.order = int(request.form.get("order", challenge.order))

    if challenge.challenge_type == "docker":
        new_dockerfile = request.form.get("dockerfile_content", "").strip()
        if new_dockerfile and new_dockerfile != challenge.dockerfile_content:
            challenge.dockerfile_content = new_dockerfile
            success, msg = build_image(challenge.id, new_dockerfile)
            if success:
                challenge.image_tag = msg
            else:
                flash(f"镜像构建失败: {msg}", "error")

    db.session.commit()
    flash("题目更新成功", "success")
    return redirect(url_for("admin.competition_detail", comp_id=challenge.competition_id))


@admin_bp.route("/challenges/<int:challenge_id>/delete", methods=["POST"])
@admin_required
def delete_challenge(challenge_id):
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge:
        flash("题目不存在", "error")
        return redirect(url_for("admin.competitions"))

    comp_id = challenge.competition_id
    db.session.delete(challenge)
    db.session.commit()
    flash("题目已删除", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp_id))


@admin_bp.route("/competitions/<int:comp_id>/deploy", methods=["POST"])
@admin_required
def deploy_environments(comp_id):
    from app import socketio, logger
    from flask import current_app

    app = current_app._get_current_object()

    # 快速预检：Docker 是否可用？
    docker_ok = True
    try:
        from docker_engine.manager import get_client
        get_client()
    except Exception as e:
        docker_ok = False
        logger.warning(f"Deploy pre-check: Docker not available ({e})")

    def _deploy():
        try:
            with app.app_context():
                deploy_competition_environments(comp_id, socketio=socketio)
        except Exception as e:
            logger.error(f"Deploy error: {e}")
            try:
                socketio.emit("deploy_progress", {
                    "progress": 0, "total": 0, "current": 0,
                    "message": f"[系统错误] {e}"
                })
                socketio.emit("deploy_complete", {"success": 0, "failed": 0, "total": 0})
            except Exception:
                pass

    thread = threading.Thread(target=_deploy)
    thread.start()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "message": "部署任务已启动", "docker_ok": docker_ok})
    flash("部署任务已启动，请观察下方日志了解进度", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp_id))


@admin_bp.route("/competitions/<int:comp_id>/environments")
@admin_required
def environments(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    envs = get_competition_environments(comp_id)
    return render_template("admin/environments.html", competition=comp, environments=envs)


@admin_bp.route("/environments/<int:env_id>/action/<action>", methods=["POST"])
@admin_required
def environment_action(env_id, action):
    env = db.session.get(Environment, env_id)
    if not env:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "error": "环境不存在"})
        flash("环境不存在", "error")
        return redirect(url_for("admin.competitions"))

    if action == "start":
        start_container(env.container_id)
        env.status = "running"
    elif action == "stop":
        stop_container(env.container_id)
        env.status = "stopped"
    elif action == "remove":
        remove_container(env.container_id)
        env.status = "removed"
        env.container_id = ""

    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "action": action, "status": env.status})
    return redirect(url_for("admin.competition_detail", comp_id=env.competition_id))


@admin_bp.route("/competitions/<int:comp_id>/stop-all", methods=["POST"])
@admin_required
def stop_all(comp_id):
    result = stop_all_environments(comp_id)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "stopped": result["stopped"], "errors": result["errors"]})
    flash(f"已停止 {result['stopped']} 个容器，{result['errors']} 个失败", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp_id))


@admin_bp.route("/competitions/<int:comp_id>/remove-all", methods=["POST"])
@admin_required
def remove_all(comp_id):
    result = remove_all_environments(comp_id)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "removed": result["removed"], "errors": result["errors"]})
    flash(f"已删除 {result['removed']} 个容器", "success")
    return redirect(url_for("admin.competition_detail", comp_id=comp_id))


@admin_bp.route("/competitions/<int:comp_id>/scores")
@admin_required
def scores(comp_id):
    comp = db.session.get(Competition, comp_id)
    if not comp:
        flash("竞赛不存在", "error")
        return redirect(url_for("admin.competitions"))

    from sqlalchemy import func
    rankings = db.session.query(
        User.id,
        User.username,
        User.team_name,
        func.coalesce(func.sum(Score.score), 0).label("total_score"),
        func.count(Score.id).label("solved_count"),
    ).outerjoin(Score, (Score.user_id == User.id) & (Score.competition_id == comp_id) & (Score.passed == True)) \
     .filter(User.role == "contestant") \
     .group_by(User.id) \
     .order_by(func.sum(Score.score).desc()) \
     .all()

    challenges_list = Challenge.query.filter_by(competition_id=comp_id).order_by(Challenge.order).all()

    # 构建查找表：(user_id, challenge_id) -> Score
    score_lookup = {}
    for s in Score.query.filter_by(competition_id=comp_id).all():
        score_lookup[(s.user_id, s.challenge_id)] = s

    return render_template("admin/scores.html", competition=comp,
                           rankings=rankings, score_lookup=score_lookup,
                           challenges=challenges_list)


# ── 试卷题目管理 ──

@admin_bp.route("/challenges/<int:challenge_id>/exam-questions", methods=["POST"])
@admin_required
def add_exam_question(challenge_id):
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge or challenge.challenge_type != "exam":
        return jsonify({"success": False, "error": "无效的试卷题目"}), 400

    question_type = request.form.get("question_type", "single_choice")
    question_text = request.form.get("question_text", "").strip()
    options = request.form.get("options", "[]").strip()
    answer = request.form.get("answer", "").strip()
    points = int(request.form.get("points", 0))
    order = int(request.form.get("order", 0))

    if not question_text or not answer:
        return jsonify({"success": False, "error": "题目内容和答案不能为空"}), 400

    q = ExamQuestion(
        challenge_id=challenge_id,
        question_type=question_type,
        question_text=question_text,
        options=options,
        answer=answer,
        points=points,
        order=order,
    )
    db.session.add(q)
    db.session.commit()
    return jsonify({"success": True, "question": q.to_dict()})


@admin_bp.route("/exam-questions/<int:question_id>/edit", methods=["POST"])
@admin_required
def edit_exam_question(question_id):
    q = db.session.get(ExamQuestion, question_id)
    if not q:
        return jsonify({"success": False, "error": "试题不存在"}), 404

    q.question_type = request.form.get("question_type", q.question_type)
    q.question_text = request.form.get("question_text", q.question_text).strip()
    q.options = request.form.get("options", q.options).strip()
    q.answer = request.form.get("answer", q.answer).strip()
    q.points = int(request.form.get("points", q.points))
    q.order = int(request.form.get("order", q.order))
    db.session.commit()
    return jsonify({"success": True, "question": q.to_dict()})


@admin_bp.route("/exam-questions/<int:question_id>/delete", methods=["POST"])
@admin_required
def delete_exam_question(question_id):
    q = db.session.get(ExamQuestion, question_id)
    if not q:
        return jsonify({"success": False, "error": "试题不存在"}), 404

    challenge_id = q.challenge_id
    db.session.delete(q)
    db.session.commit()
    return jsonify({"success": True, "challenge_id": challenge_id})


# ── 用户管理 ──

@admin_bp.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.id).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "player123").strip()
    team_name = request.form.get("team_name", "").strip()

    if not username:
        flash("用户名不能为空", "error")
        return redirect(url_for("admin.users"))

    if User.query.filter_by(username=username).first():
        flash("用户名已存在", "error")
        return redirect(url_for("admin.users"))

    import bcrypt
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user = User(username=username, password_hash=pw_hash, role="contestant", team_name=team_name)
    db.session.add(user)
    db.session.commit()

    flash(f"选手账号「{username}」创建成功（密码: {password}）", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("用户不存在", "error")
        return redirect(url_for("admin.users"))
    if user.role == "admin":
        flash("不能重置管理员密码", "error")
        return redirect(url_for("admin.users"))

    import bcrypt
    user.password_hash = bcrypt.hashpw("player123".encode(), bcrypt.gensalt()).decode()
    db.session.commit()
    flash(f"用户「{user.username}」密码已重置为 player123", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("用户不存在", "error")
        return redirect(url_for("admin.users"))
    if user.role == "admin":
        flash("不能删除管理员账号", "error")
        return redirect(url_for("admin.users"))

    Environment.query.filter_by(user_id=user_id).delete()
    Score.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f"用户「{user.username}」已删除", "success")
    return redirect(url_for("admin.users"))


# ── 模板 API ──

@admin_bp.route("/templates/<template_name>/dockerfile")
@admin_required
def template_dockerfile(template_name):
    import os
    from config import Config
    tpl_path = os.path.join(Config.DOCKER_TEMPLATES_DIR, template_name, "Dockerfile")
    if not os.path.isfile(tpl_path):
        return jsonify({"error": "模板不存在"}), 404
    with open(tpl_path) as f:
        return jsonify({"dockerfile": f.read()})


# ── 部署指标 ──

@admin_bp.route("/metrics")
@admin_required
def deploy_metrics():
    """返回所有竞赛的部署指标数据（用于论文数据分析）。"""
    comps = Competition.query.order_by(Competition.created_at.desc()).all()
    data = []
    for comp in comps:
        docker_chals = [c for c in comp.challenges if c.challenge_type != "exam"]
        envs = Environment.query.filter_by(competition_id=comp.id).all()
        scores = Score.query.filter_by(competition_id=comp.id, passed=True).all()

        data.append({
            "id": comp.id,
            "name": comp.name,
            "status": comp.status,
            "challenge_count": len(docker_chals),
            "exam_count": len(comp.challenges) - len(docker_chals),
            "env_total": len(envs),
            "env_running": sum(1 for e in envs if e.status == "running"),
            "env_stopped": sum(1 for e in envs if e.status == "stopped"),
            "auto_deployed": comp.auto_deployed,
            "deployed_at": comp.deployed_at.isoformat() if comp.deployed_at else None,
            "pass_rate": round(len(scores) / len(envs) * 100, 1) if envs else 0,
            "total_score": sum(s.score for s in scores),
        })

    return jsonify({"metrics": data})


# ── 系统日志 ──

@admin_bp.route("/logs")
@admin_required
def logs():
    return render_template("admin/logs.html")


@admin_bp.route("/logs/data")
@admin_required
def logs_data():
    from app import get_logs
    level = request.args.get("level", "").strip()
    limit = int(request.args.get("limit", 200))
    logs_list = get_logs(limit=limit, level=level or None)
    return jsonify({"logs": logs_list})
