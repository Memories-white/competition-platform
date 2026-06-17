from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from models import db
from models.models import Competition, Challenge, Environment, Score, User, ExamQuestion
from services.environment_service import get_user_environments
from services.judge_service import submit_for_judge, get_user_scores, get_scoreboard, judge_exam

contestant_bp = Blueprint("contestant", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("请先登录", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def contestant_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if session.get("role") != "contestant":
            flash("需要选手账号", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@contestant_bp.route("/")
@contestant_required
def dashboard():
    user_id = session["user_id"]
    active_comps = Competition.query.filter_by(status="active").order_by(Competition.start_time).all()

    comps_data = []
    for comp in active_comps:
        envs = get_user_environments(user_id, comp.id)
        scores = get_user_scores(user_id, comp.id)
        total_score = sum(s["score"] for s in scores)
        total_possible = sum(c.points for c in comp.challenges)
        exam_challenges = [c for c in comp.challenges if c.challenge_type == "exam"]
        exam_scores = {s["challenge_id"]: s for s in scores if s.get("challenge_id")}
        comps_data.append({
            "competition": comp,
            "environments": envs,
            "exam_challenges": exam_challenges,
            "exam_scores": exam_scores,
            "total_score": total_score,
            "total_possible": total_possible,
            "passed_count": sum(1 for s in scores if s["passed"]),
            "total_challenges": len(comp.challenges),
        })

    return render_template("contestant/dashboard.html", comps=comps_data)


@contestant_bp.route("/environment/<int:env_id>")
@contestant_required
def environment_detail(env_id):
    env = db.session.get(Environment, env_id)
    if not env:
        flash("环境不存在", "error")
        return redirect(url_for("contestant.dashboard"))

    if env.user_id != session["user_id"]:
        flash("无权访问此环境", "error")
        return redirect(url_for("contestant.dashboard"))

    from docker_engine.manager import get_container_status

    status = get_container_status(env.container_id) if env.container_id else None
    challenge = env.challenge
    score_record = Score.query.filter_by(
        competition_id=env.competition_id,
        user_id=env.user_id,
        challenge_id=env.challenge_id,
    ).first()

    return render_template("contestant/environment.html",
                           env=env, status=status, challenge=challenge,
                           score=score_record)


@contestant_bp.route("/environment/<int:env_id>/submit", methods=["POST"])
@contestant_required
def submit_judge(env_id):
    env = db.session.get(Environment, env_id)
    if not env or env.user_id != session["user_id"]:
        return jsonify({"success": False, "error": "无权操作"}), 403

    result = submit_for_judge(env_id)
    return jsonify(result)


@contestant_bp.route("/scoreboard")
@contestant_required
def scoreboard():
    comp_id = request.args.get("competition_id")
    competitions = Competition.query.filter(
        Competition.status.in_(["active", "finished"])
    ).order_by(Competition.start_time.desc()).all()

    rankings = []
    current_comp = None
    if comp_id:
        current_comp = db.session.get(Competition, int(comp_id))
    elif competitions:
        current_comp = competitions[0]

    if current_comp:
        rankings = get_scoreboard(current_comp.id)

    return render_template("contestant/scoreboard.html",
                           competitions=competitions,
                           current_comp=current_comp,
                           rankings=rankings)


# ── Exam ──

@contestant_bp.route("/exam/<int:challenge_id>")
@contestant_required
def exam_page(challenge_id):
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge or challenge.challenge_type != "exam":
        flash("无效的试卷题目", "error")
        return redirect(url_for("contestant.dashboard"))

    questions = ExamQuestion.query.filter_by(challenge_id=challenge_id).order_by(ExamQuestion.order).all()

    import json
    for q in questions:
        try:
            q.options_list = json.loads(q.options) if q.options else []
        except (json.JSONDecodeError, TypeError):
            q.options_list = []

    existing_score = Score.query.filter_by(
        competition_id=challenge.competition_id,
        user_id=session["user_id"],
        challenge_id=challenge_id,
    ).first()

    return render_template("contestant/exam.html",
                           challenge=challenge,
                           questions=questions,
                           existing_score=existing_score)


@contestant_bp.route("/exam/<int:challenge_id>/submit", methods=["POST"])
@contestant_required
def exam_submit(challenge_id):
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge or challenge.challenge_type != "exam":
        return jsonify({"success": False, "error": "无效的试卷题目"}), 400

    answers = {}
    for key, value in request.form.items():
        if key.startswith("q_"):
            q_id = key[2:]
            answers[q_id] = value.strip()

    result = judge_exam(challenge_id, session["user_id"], answers)
    return jsonify(result)
