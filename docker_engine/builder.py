import os
import io
import re
import time
import logging
import docker
from config import Config

logger = logging.getLogger(__name__)

BUILD_MAX_RETRIES = 2
BUILD_RETRY_DELAY = 3  # seconds
BUILD_TIMEOUT = 300     # 单次构建超时（秒），5分钟足够拉取和安装

_client = None


_HINT_MSG = (
    "【提示】如果你遇到类似报错，说明 Docker 没有配置镜像加速，"
    "需要梯子或者其他工具来访问 Docker Hub。如果看不懂如何解决，"
    "请把这段错误信息发给 AI 询问。"
)


def _format_error(msg: str) -> str:
    msg_lower = msg.lower()
    for kw in [
        "dial tcp", "connection refused", "failed to resolve",
        "dialing", "connectex", "registry", "no such host",
        "timeout", "TLS handshake timeout", "no HTTPS proxy",
    ]:
        if kw in msg_lower:
            return msg + " | " + _HINT_MSG
    return msg


def _rewrite_dockerfile_for_mirror(dockerfile_content: str, mirror: str) -> str:
    """将 Dockerfile 中的 FROM 行重写为使用镜像加速器拉取基础镜像。
    只重写官方镜像（不含私有 registry 路径），避免破坏自定义镜像引用。"""
    if not mirror:
        return dockerfile_content
    mirror = mirror.rstrip("/")
    lines = dockerfile_content.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split(None, 1)
            if len(parts) >= 2:
                image = parts[1]
                # 跳过 scratch 和已使用私有 registry 的镜像
                if image.lower() == "scratch":
                    result.append(line)
                    continue
                # 如果镜像不含 "/" 或使用 docker.io/library，认为是官方镜像，加上镜像前缀
                if "/" not in image:
                    # 官方库镜像，如 "ubuntu:22.04"
                    parts[1] = f"{mirror}/library/{image}"
                else:
                    # 含 "/" 的镜像，判断是否已经是镜像地址
                    # 常见模式：docker.io/library/xxx 不重写，保持原样放行
                    # 私有 registry 也不重写
                    host_part = image.split("/")[0]
                    if "." not in host_part and ":" not in host_part:
                        # 无域名/端口 => 官方镜像如 library/ubuntu
                        parts[1] = f"{mirror}/{image}"
                    # 否则认为已是完整 registry 路径，不修改
            result.append(" ".join(parts))
        else:
            result.append(line)
    return "\n".join(result)


def get_client():
    global _client
    if _client is None:
        try:
            _client = docker.from_env(timeout=5)
            _client.ping()
        except Exception as e:
            _client = None
            logger.error(f"Failed to connect to Docker: {e}")
            raise ConnectionError(f"Docker 服务未启动或无法连接: {e}")
    return _client


def build_image(challenge_id: int, dockerfile_content: str, max_retries: int = None, mirror: str = None) -> tuple:
    """构建 Docker 镜像。若配置了 mirror 且首次构建全部失败，则用镜像地址重试。
    返回 (success: bool, image_tag_or_error: str)"""
    image_tag = f"comp-chal-{challenge_id}:latest"
    retries = max_retries if max_retries is not None else BUILD_MAX_RETRIES

    def _do_build(dockerfile):
        """内部构建循环，返回 (bool, error_msg)"""
        last_error = ""
        for attempt in range(retries + 1):
            try:
                client = get_client()
                client.images.build(
                    fileobj=io.BytesIO(dockerfile.encode()),
                    tag=image_tag,
                    rm=True,
                    forcerm=True,
                    timeout=BUILD_TIMEOUT,
                )
                if attempt > 0:
                    logger.info(f"Build succeeded on retry {attempt} for challenge {challenge_id}")
                return True, ""
            except docker.errors.BuildError as e:
                error_msg = ""
                for line in e.build_log:
                    if "stream" in line:
                        error_msg += line["stream"]
                    elif "error" in line:
                        error_msg += line["error"]
                last_error = _format_error(error_msg or str(e))
            except Exception as e:
                last_error = _format_error(str(e))

            if attempt < retries:
                logger.warning(f"Build attempt {attempt + 1} failed for challenge {challenge_id}, retrying in {BUILD_RETRY_DELAY}s: {last_error}")
                time.sleep(BUILD_RETRY_DELAY)
        return False, last_error

    # ── 第一次：使用原始 Dockerfile 构建 ──
    ok, err = _do_build(dockerfile_content)
    if ok:
        return True, image_tag

    # ── 第二次：使用镜像加速器重试 ──
    mirror = mirror or Config.DOCKER_REGISTRY_MIRROR
    if mirror:
        mirrored = _rewrite_dockerfile_for_mirror(dockerfile_content, mirror)
        if mirrored != dockerfile_content:
            logger.info(f"Retrying build for challenge {challenge_id} with mirror: {mirror}")
            ok2, err2 = _do_build(mirrored)
            if ok2:
                return True, image_tag
            err = err2  # 返回镜像重试的错误信息

    return False, err


def build_image_from_template(template_name: str, challenge_id: int, max_retries: int = None) -> tuple:
    template_path = os.path.join(Config.DOCKER_TEMPLATES_DIR, template_name)
    if not os.path.isdir(template_path):
        return False, f"Template {template_name} not found"

    image_tag = f"comp-chal-{challenge_id}:latest"
    retries = max_retries if max_retries is not None else BUILD_MAX_RETRIES

    last_error = ""
    for attempt in range(retries + 1):
        try:
            client = get_client()
            client.images.build(
                path=template_path,
                tag=image_tag,
                rm=True,
                forcerm=True,
                timeout=BUILD_TIMEOUT,
            )
            if attempt > 0:
                logger.info(f"Template build succeeded on retry {attempt} for challenge {challenge_id}")
            return True, image_tag
        except docker.errors.BuildError as e:
            error_msg = ""
            for line in e.build_log:
                if "stream" in line:
                    error_msg += line["stream"]
                elif "error" in line:
                    error_msg += line["error"]
            last_error = _format_error(error_msg or str(e))
        except Exception as e:
            last_error = _format_error(str(e))

        if attempt < retries:
            logger.warning(f"Template build attempt {attempt + 1} failed for {template_name}, retrying in {BUILD_RETRY_DELAY}s: {last_error}")
            time.sleep(BUILD_RETRY_DELAY)

    return False, last_error


def get_image_info(tag: str) -> dict | None:
    try:
        client = get_client()
        img = client.images.get(tag)
        return {
            "id": img.id,
            "tags": img.tags,
            "size": round(img.attrs.get("Size", 0) / (1024 * 1024), 2),
            "created": img.attrs.get("Created", ""),
        }
    except Exception:
        return None


def remove_image(tag: str) -> bool:
    try:
        client = get_client()
        client.images.remove(tag, force=True)
        return True
    except Exception:
        return False


def list_built_images() -> list:
    try:
        client = get_client()
        images = []
        for img in client.images.list():
            for tag in img.tags:
                if "comp-chal-" in tag:
                    images.append({"id": img.id, "tag": tag, "size": img.attrs.get("Size", 0)})
        return images
    except Exception:
        return []


def get_available_templates() -> list[dict]:
    templates = []
    templates_dir = Config.DOCKER_TEMPLATES_DIR
    if os.path.isdir(templates_dir):
        for name in sorted(os.listdir(templates_dir)):
            p = os.path.join(templates_dir, name)
            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "Dockerfile")):
                dockerfile = open(os.path.join(p, "Dockerfile")).read()
                desc = ""
                for line in dockerfile.split("\n"):
                    if line.strip().startswith("RUN echo"):
                        desc = line.split("echo", 1)[1].strip().strip("'").strip('"').strip(";").strip()
                        break
                templates.append({"name": name, "description": desc or name})
    return templates


def get_expose_ports_from_dockerfile(dockerfile_content: str) -> list[int]:
    """返回 Dockerfile 中所有 EXPOSE 端口（排序后，Web 端口在后）。"""
    ports = []
    for line in dockerfile_content.split("\n"):
        stripped = line.strip().upper()
        if stripped.startswith("EXPOSE"):
            parts = stripped.split()
            for p in parts[1:]:
                try:
                    ports.append(int(p.split("/")[0]))
                except ValueError:
                    pass
    # 排序：SSH (22) 在前，Web 端口 (80, 443, 5000 等) 在后
    ssh_ports = [p for p in ports if p == 22]
    web_ports = [p for p in ports if p != 22]
    return ssh_ports + web_ports


def build_challenge_image(challenge_id: int, dockerfile_content: str) -> dict:
    """供后台调度器调用：构建题目镜像并返回结果 dict。
    返回 {"success": bool, "image_tag": str, "error": str}"""
    mirror = Config.DOCKER_REGISTRY_MIRROR or None
    ok, result = build_image(challenge_id, dockerfile_content, mirror=mirror)
    if ok:
        return {"success": True, "image_tag": result, "error": ""}
    return {"success": False, "image_tag": "", "error": result}


def get_expose_port_from_dockerfile(dockerfile_content: str) -> int:
    """返回主端口 (SSH)，若未暴露 SSH 端口则回退到 22。"""
    ports = get_expose_ports_from_dockerfile(dockerfile_content)
    ssh = [p for p in ports if p == 22]
    if ssh:
        return 22
    return ports[0] if ports else 80
