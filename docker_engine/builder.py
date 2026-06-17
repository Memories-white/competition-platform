import os
import io
import logging
import docker
from config import Config

logger = logging.getLogger(__name__)

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


def build_image(challenge_id: int, dockerfile_content: str) -> tuple:
    image_tag = f"comp-chal-{challenge_id}:latest"
    try:
        client = get_client()
        client.images.build(
            fileobj=io.BytesIO(dockerfile_content.encode()),
            tag=image_tag,
            rm=True,
            forcerm=True,
        )
        return True, image_tag
    except docker.errors.BuildError as e:
        error_msg = ""
        for line in e.build_log:
            if "stream" in line:
                error_msg += line["stream"]
            elif "error" in line:
                error_msg += line["error"]
        return False, _format_error(error_msg or str(e))
    except Exception as e:
        return False, _format_error(str(e))


def build_image_from_template(template_name: str, challenge_id: int) -> tuple:
    template_path = os.path.join(Config.DOCKER_TEMPLATES_DIR, template_name)
    if not os.path.isdir(template_path):
        return False, f"Template {template_name} not found"

    image_tag = f"comp-chal-{challenge_id}:latest"
    try:
        client = get_client()
        client.images.build(
            path=template_path,
            tag=image_tag,
            rm=True,
            forcerm=True,
        )
        return True, image_tag
    except docker.errors.BuildError as e:
        error_msg = ""
        for line in e.build_log:
            if "stream" in line:
                error_msg += line["stream"]
            elif "error" in line:
                error_msg += line["error"]
        return False, _format_error(error_msg or str(e))
    except Exception as e:
        return False, _format_error(str(e))


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


def get_expose_port_from_dockerfile(dockerfile_content: str) -> int:
    for line in dockerfile_content.split("\n"):
        stripped = line.strip().upper()
        if stripped.startswith("EXPOSE"):
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1].split("/")[0])
                except ValueError:
                    pass
    return 80
