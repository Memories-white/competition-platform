import json
import time
import logging
from datetime import datetime, timezone
from models import db
from models.models import Environment, Challenge, Competition
from docker_engine.manager import create_container, remove_container, get_container_status
from docker_engine.builder import get_expose_ports_from_dockerfile

logger = logging.getLogger(__name__)


def deploy_competition_environments(competition_id: int, socketio=None) -> dict:
    """为竞赛的所有选手部署容器环境，通过 SocketIO 实时推送进度。"""
    start_time = time.time()

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
    # 过滤掉试卷类题目（无需 Docker 部署）
    docker_challenges = [c for c in challenges if c.challenge_type != "exam"]

    if not contestants:
        emit("[错误] 没有选手可分配，请先注册选手账号")
        emit_done(0, 0)
        return {"success": False, "error": "没有选手可分配"}
    if not docker_challenges:
        emit("[提示] 没有 Docker 实操题目可部署（试卷题目无需部署）")
        emit_done(0, 0)
        return {"success": False, "error": "没有 Docker 题目可部署"}

    total = len(contestants) * len(docker_challenges)
    current = 0
    results = {"success": 0, "failed": 0, "details": []}

    for user in contestants:
        for challenge in docker_challenges:
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
            expose_ports = get_expose_ports_from_dockerfile(challenge.dockerfile_content or "")
            if not expose_ports:
                expose_ports = [80]

            if not challenge.image_tag:
                logger.warning(f"Deploy skip: challenge '{challenge.title}' has no image_tag (image not built)")
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
                expose_ports=expose_ports,
            )

            if result["success"]:
                if existing:
                    existing.container_id = result["container_id"]
                    existing.container_name = container_name
                    existing.host_port = result["host_port"]
                    existing.web_port = result.get("web_port", 0)
                    existing.status = "running"
                else:
                    env = Environment(
                        competition_id=competition_id,
                        user_id=user.id,
                        challenge_id=challenge.id,
                        container_id=result["container_id"],
                        container_name=container_name,
                        host_port=result["host_port"],
                        web_port=result.get("web_port", 0),
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

    elapsed = round(time.time() - start_time, 2)
    results["elapsed_seconds"] = elapsed
    results["total_envs"] = total

    logger.info(
        f"Deploy metrics [{competition.name}]: "
        f"total={total} success={results['success']} failed={results['failed']} "
        f"elapsed={elapsed}s "
        f"avg_per_container={round(elapsed / total, 2) if total > 0 else 0}s"
    )

    if socketio:
        socketio.emit("deploy_complete", {
            "success": results["success"],
            "failed": results["failed"],
            "total": total,
            "elapsed": elapsed,
        })

    return results


def stop_all_environments(competition_id: int) -> dict:
    """停止竞赛的所有容器。"""
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
    """删除竞赛的所有容器并清理环境记录。"""
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
    """获取用户的所有环境，可按竞赛过滤。"""
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
    """获取竞赛的所有环境（管理员视图）。"""
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
