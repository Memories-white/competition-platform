import os
import socket

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _detect_host_ip():
    """自动检测服务器局域网 IP，可通过环境变量 HOST_IP 覆盖。"""
    env_ip = os.environ.get("HOST_IP", "")
    if env_ip:
        return env_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "localhost"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "competition-platform-secret-key-2024")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "database.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEFAULT_CPU_LIMIT = 0.5
    DEFAULT_MEM_LIMIT = "512m"
    CONTAINER_NETWORK = "comp_network"

    AUTO_BUILD_INTERVAL_SECONDS = 15
    JUDGE_INTERVAL_SECONDS = 30
    CLEANUP_INTERVAL_SECONDS = 120

    DOCKER_TEMPLATES_DIR = os.path.join(BASE_DIR, "docker_templates")

    HOST_IP = _detect_host_ip()
    DOCKER_HOST = os.environ.get("DOCKER_HOST", "")

    # Docker 镜像加速器（国内环境使用）
    # 示例: "https://docker.m.daocloud.io" 或 "https://registry.cn-hangzhou.aliyuncs.com"
    # 留空则不启用；也可通过环境变量 DOCKER_REGISTRY_MIRROR 设置
    DOCKER_REGISTRY_MIRROR = os.environ.get("DOCKER_REGISTRY_MIRROR", "")

    # 后台镜像构建间隔（秒），未构建的题目镜像会在此间隔被逐个构建
    IMAGE_BUILD_INTERVAL_SECONDS = int(os.environ.get("IMAGE_BUILD_INTERVAL_SECONDS", "30"))
