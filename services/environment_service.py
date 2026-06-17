import json
from datetime import datetime, timezone
from models import db
from models.models import Environment, Challenge, Competition
from docker_engine.manager import create_container, remove_container, get_container_status
from docker_engine.builder import get_expose_port_from_dockerfile


def deploy_competition_environments(competition_id: int, socketio=None) -> dict:
    """Deploy containers for all contestants for a competition. Emits progress via socketio."""
    def emit(msg):
        if socketio:
            socketio.emit("deploy_progress", {"progress": 0, "total": 0, "current": 0, "message": msg})

    def emit_done(success, failed):
        if socketio:
            socketio.emit("deploy_complete", {"success": success, "failed": failed, "total": success + failed})

    competition = db.session.get(Competition, competition_id)
    if not competition:
        emit("[错误] 竞赛不存在")
        emit_done(0, 0)
        return {"success": False, "error": "竞赛不存在"}

    from models.models import User
    contestants = User.query.filter_by(role="contestant").all()
    challenges = Challenge.query.filter_by(competition_id=competition_id).all()

    if not contestants:
        emit("[错误] 没有选手可分配，请先注册选手账号")
        emit_done(0, 0)
        return {"success": False, "error": "没有选手可分配"}
    if not challenges:
        emit("[错误] 没有题目可部署，请先添加题目并构建镜像")
        emit_done(0, 0)
        return {"success": False, "error": "没有题目可部署"}

    total = len(contestants) * len(challenges)
    current = 0
    results = {"success": 0, "failed": 0, "details": []}

    for user in contestants:
        for challenge in challenges:
            current += 1
            progress_pct = int(current / total * 100)

            existing = Environment.query.filter_by(
                competition_id=competition_id,
                user_id=user.id,
                challenge_id=challenge.id,
            ).first()

            if existing and existing.container_id:
                status = get_container_status(existing.container_id)
                if status and status["status"] == "running":
                    results["details"].append({
                        "user": user.username,
                        "challenge": challenge.title,
                        "status": "already_running",
                        "container_name": existing.container_name,
                    })
                    if socketio:
                        socketio.emit("deploy_progress", {
                            "progress": progress_pct,
                            "total": total,
                            "current": current,
                            "message": f"[跳过] {user.username} - {challenge.title} (已运行)"
                        })
                    continue
                elif existing.container_id:
                    remove_container(existing.container_id)

            container_name = f"comp-{competition_id}-u{user.id}-c{challenge.id}"
            expose_port = get_expose_port_from_dockerfile(challenge.dockerfile_content or "")

            if not challenge.image_tag:
                results["details"].append({
                    "user": user.username,
                    "challenge": challenge.title,
                    "status": "no_image",
                })
                if socketio:
                    socketio.emit("deploy_progress", {
                        "progress": progress_pct,
                        "total": total,
                        "current": current,
                        "message": f"[错误] {user.username} - {challenge.title} (镜像未构建)"
                    })
                results["failed"] += 1
                continue

            result = create_container(
                image_tag=challenge.image_tag,
                container_name=container_name,
                cpu_limit=competition.cpu_limit,
                mem_limit=competition.mem_limit,
                expose_port=expose_port,
            )

            if result["success"]:
                if existing:
                    existing.container_id = result["container_id"]
                    existing.container_name = container_name
                    existing.host_port = result["host_port"]
                    existing.status = "running"
                else:
                    env = Environment(
                        competition_id=competition_id,
                        user_id=user.id,
                        challenge_id=challenge.id,
                        container_id=result["container_id"],
                        container_name=container_name,
                        host_port=result["host_port"],
                        status="running",
                    )
                    db.session.add(env)
                results["success"] += 1
                msg = f"[成功] {user.username} - {challenge.title} (端口: {result['host_port']})"
            else:
                results["failed"] += 1
                msg = f"[失败] {user.username} - {challenge.title} ({result.get('error', '未知错误')})"

            results["details"].append({
                "user": user.username,
                "challenge": challenge.title,
                "status": "success" if result["success"] else "failed",
                "container_name": container_name,
                "host_port": result.get("host_port"),
                "error": result.get("error"),
            })

            if socketio:
                socketio.emit("deploy_progress", {
                    "progress": progress_pct,
                    "total": total,
                    "current": current,
                    "message": msg,
                })

    db.session.commit()

    if socketio:
        socketio.emit("deploy_complete", {
            "success": results["success"],
            "failed": results["failed"],
            "total": total,
        })

    return results


def stop_all_environments(competition_id: int) -> dict:
    """Stop all containers for a competition."""
    environments = Environment.query.filter_by(competition_id=competition_id).all()
    stopped = 0
    errors = 0

    for env in environments:
        if env.container_id:
            from docker_engine.manager import stop_container

            if stop_container(env.container_id):
                env.status = "stopped"
                stopped += 1
            else:
                errors += 1

    db.session.commit()
    return {"stopped": stopped, "errors": errors}


def remove_all_environments(competition_id: int) -> dict:
    """Remove all containers for a competition."""
    environments = Environment.query.filter_by(competition_id=competition_id).all()
    removed = 0
    errors = 0

    for env in environments:
        if env.container_id:
            from docker_engine.manager import remove_container

            if remove_container(env.container_id):
                removed += 1
            else:
                errors += 1
        db.session.delete(env)

    db.session.commit()
    return {"removed": removed, "errors": errors}


def get_user_environments(user_id: int, competition_id: int = None) -> list:
    """Get all environments for a user, optionally filtered by competition."""
    q = Environment.query.filter_by(user_id=user_id)
    if competition_id:
        q = q.filter_by(competition_id=competition_id)
    envs = q.order_by(Environment.created_at.desc()).all()

    result = []
    for env in envs:
        data = env.to_dict()
        data["challenge_title"] = env.challenge.title if env.challenge else ""
        data["competition_name"] = env.competition.name if env.competition else ""
        data["points"] = env.challenge.points if env.challenge else 0

        if env.container_id:
            status = get_container_status(env.container_id)
            if status:
                data["docker_status"] = status["status"]
                if data["status"] != status["status"]:
                    env.status = status["status"]

        result.append(data)

    db.session.commit()
    return result


def get_competition_environments(competition_id: int) -> list:
    """Get all environments for a competition (admin view)."""
    envs = Environment.query.filter_by(competition_id=competition_id).order_by(
        Environment.user_id, Environment.challenge_id
    ).all()

    result = []
    for env in envs:
        data = env.to_dict()
        data["username"] = env.user.username if env.user else ""
        data["team_name"] = env.user.team_name if env.user else ""
        data["challenge_title"] = env.challenge.title if env.challenge else ""

        if env.container_id:
            status = get_container_status(env.container_id)
            if status:
                data["docker_status"] = status["status"]
                if data["status"] != status["status"]:
                    env.status = status["status"]

        result.append(data)

    db.session.commit()
    return result
