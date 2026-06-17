from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="contestant")  # admin | contestant
    team_name = db.Column(db.String(120), default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    environments = db.relationship("Environment", backref="user", lazy=True)
    scores = db.relationship("Score", backref="user", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "team_name": self.team_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Competition(db.Model):
    __tablename__ = "competitions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="draft")  # draft | active | finished
    cpu_limit = db.Column(db.Float, default=0.5)
    mem_limit = db.Column(db.String(20), default="512m")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    challenges = db.relationship("Challenge", backref="competition", lazy=True, cascade="all, delete-orphan")
    environments = db.relationship("Environment", backref="competition", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "cpu_limit": self.cpu_limit,
            "mem_limit": self.mem_limit,
        }


class Challenge(db.Model):
    __tablename__ = "challenges"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competitions.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    dockerfile_content = db.Column(db.Text, default="")
    judge_type = db.Column(db.String(20), default="port")  # port | command | file
    judge_config = db.Column(db.Text, default="{}")  # JSON: {port:80} | {cmd:"curl localhost"} | {path:"/etc/nginx/nginx.conf"}
    points = db.Column(db.Integer, default=100)
    order = db.Column(db.Integer, default=0)
    image_tag = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    environments = db.relationship("Environment", backref="challenge", lazy=True)
    scores = db.relationship("Score", backref="challenge", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "title": self.title,
            "description": self.description,
            "judge_type": self.judge_type,
            "judge_config": self.judge_config,
            "points": self.points,
            "order": self.order,
            "image_tag": self.image_tag,
        }


class Environment(db.Model):
    __tablename__ = "environments"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competitions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id"), nullable=False)
    container_id = db.Column(db.String(200), default="")
    container_name = db.Column(db.String(200), default="")
    host_port = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="pending")  # pending | running | stopped | error
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "user_id": self.user_id,
            "challenge_id": self.challenge_id,
            "container_id": self.container_id[:12] if self.container_id else "",
            "container_name": self.container_name,
            "host_port": self.host_port,
            "status": self.status,
        }


class Score(db.Model):
    __tablename__ = "scores"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competitions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenges.id"), nullable=False)
    score = db.Column(db.Integer, default=0)
    passed = db.Column(db.Boolean, default=False)
    judged_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "competition_id": self.competition_id,
            "user_id": self.user_id,
            "challenge_id": self.challenge_id,
            "score": self.score,
            "passed": self.passed,
            "judged_at": self.judged_at.isoformat() if self.judged_at else None,
        }
