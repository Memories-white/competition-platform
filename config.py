import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


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
