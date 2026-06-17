import json
from datetime import datetime, timezone
from models import db
from models.models import Challenge, Environment, Score, Competition, ExamQuestion
from docker_engine.manager import (
    check_port_in_container,
    check_file_in_container,
    exec_in_container,
)


def judge_environment(env: Environment) -> dict:
    """Judge a single environment. Returns result dict."""
    challenge = env.challenge
    if not challenge or not env.container_id:
        return {"passed": False, "score": 0, "error": "无效的环境或题目"}

    try:
        config = json.loads(challenge.judge_config)
    except json.JSONDecodeError:
        config = {}

    passed = False

    if challenge.judge_type == "port":
        port = config.get("port", 80)
        passed = check_port_in_container(env.container_id, port)

    elif challenge.judge_type == "command":
        cmd = config.get("cmd", "")
        expected = config.get("expected", None)
        if cmd:
            exit_code, output = exec_in_container(env.container_id, cmd)
            if exit_code == 0:
                if expected is not None:
                    passed = expected in output
                else:
                    passed = True

    elif challenge.judge_type == "file":
        path = config.get("path", "")
        if path:
            passed = check_file_in_container(env.container_id, path)

    score_value = challenge.points if passed else 0

    existing = Score.query.filter_by(
        competition_id=env.competition_id,
        user_id=env.user_id,
        challenge_id=env.challenge_id,
    ).first()

    if existing:
        existing.passed = passed
        existing.score = score_value
        existing.judged_at = datetime.now(timezone.utc)
    else:
        score = Score(
            competition_id=env.competition_id,
            user_id=env.user_id,
            challenge_id=env.challenge_id,
            passed=passed,
            score=score_value,
            judged_at=datetime.now(timezone.utc),
        )
        db.session.add(score)

    db.session.commit()
    return {"passed": passed, "score": score_value, "challenge_title": challenge.title}


def judge_all_for_competition(competition_id: int) -> dict:
    """Judge all environments for a competition. Called by scheduler.
    Only judges Docker-type challenges; exam challenges are scored on submission."""
    envs = Environment.query.filter_by(competition_id=competition_id).all()
    results = {"judged": 0, "passed": 0, "details": []}

    for env in envs:
        if not env.container_id:
            continue
        # Skip exam challenges (no container to judge)
        if env.challenge and env.challenge.challenge_type == "exam":
            continue
        result = judge_environment(env)
        results["judged"] += 1
        if result["passed"]:
            results["passed"] += 1
        results["details"].append({
            "user_id": env.user_id,
            "challenge_id": env.challenge_id,
            "passed": result["passed"],
        })

    return results


def submit_for_judge(env_id: int) -> dict:
    """Manual submission for judging by a contestant."""
    env = db.session.get(Environment, env_id)
    if not env:
        return {"success": False, "error": "环境不存在"}
    if not env.container_id:
        return {"success": False, "error": "容器未创建"}

    result = judge_environment(env)
    return {
        "success": True,
        "passed": result["passed"],
        "score": result["score"],
        "challenge_title": result["challenge_title"],
    }


def get_user_scores(user_id: int, competition_id: int = None) -> list:
    """Get scores for a user."""
    q = Score.query.filter_by(user_id=user_id)
    if competition_id:
        q = q.filter_by(competition_id=competition_id)

    scores = []
    for s in q.all():
        data = s.to_dict()
        data["challenge_title"] = s.challenge.title if s.challenge else ""
        data["competition_name"] = Competition.query.get(s.competition_id).name if s.competition_id else ""
        scores.append(data)
    return scores


def judge_exam(challenge_id: int, user_id: int, answers: dict) -> dict:
    """Judge exam answers and save score."""
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge or challenge.challenge_type != "exam":
        return {"success": False, "error": "无效的试卷题目"}

    questions = ExamQuestion.query.filter_by(challenge_id=challenge_id).order_by(ExamQuestion.order).all()
    if not questions:
        return {"success": False, "error": "试卷没有试题"}

    total_points = 0
    earned_points = 0
    details = []

    for q in questions:
        user_answer = answers.get(str(q.id), "").strip()
        correct_answer = q.answer.strip()
        is_correct = user_answer.lower() == correct_answer.lower() if q.question_type == "fill_blank" else user_answer == correct_answer
        total_points += q.points
        if is_correct:
            earned_points += q.points
        details.append({
            "question_id": q.id,
            "question_text": q.question_text,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "points": q.points if is_correct else 0,
            "max_points": q.points,
        })

    passed = earned_points >= total_points * 0.6 if total_points > 0 else False

    existing = Score.query.filter_by(
        competition_id=challenge.competition_id,
        user_id=user_id,
        challenge_id=challenge_id,
    ).first()

    if existing:
        existing.score = earned_points
        existing.passed = passed
        existing.judged_at = datetime.now(timezone.utc)
        existing.answers = json.dumps(answers, ensure_ascii=False)
    else:
        score = Score(
            competition_id=challenge.competition_id,
            user_id=user_id,
            challenge_id=challenge_id,
            score=earned_points,
            passed=passed,
            judged_at=datetime.now(timezone.utc),
            answers=json.dumps(answers, ensure_ascii=False),
        )
        db.session.add(score)

    db.session.commit()
    return {
        "success": True,
        "passed": passed,
        "score": earned_points,
        "total_points": total_points,
        "details": details,
    }


def get_scoreboard(competition_id: int) -> list:
    """Get the scoreboard for a competition."""
    from models.models import User
    from sqlalchemy import func

    rankings = db.session.query(
        User.id,
        User.username,
        User.team_name,
        func.coalesce(func.sum(Score.score), 0).label("total_score"),
        func.count(Score.id).label("solved_count"),
    ).outerjoin(
        Score,
        (Score.user_id == User.id) & (Score.competition_id == competition_id) & (Score.passed == True)
    ).filter(
        User.role == "contestant"
    ).group_by(User.id).order_by(func.sum(Score.score).desc()).all()

    result = []
    for i, row in enumerate(rankings):
        result.append({
            "rank": i + 1,
            "username": row.username,
            "team_name": row.team_name or "",
            "total_score": int(row.total_score),
            "solved_count": row.solved_count,
        })
    return result
