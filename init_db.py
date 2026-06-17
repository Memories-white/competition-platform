from app import create_app
from models import db, User
import bcrypt

app = create_app()

with app.app_context():
    db.create_all()
    print("Database tables created.")

    pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", password_hash=pw, role="admin", team_name="管理员")
        db.session.add(admin)

    contestant = User.query.filter_by(username="player1").first()
    if not contestant:
        pw2 = bcrypt.hashpw("player123".encode(), bcrypt.gensalt()).decode()
        contestant = User(username="player1", password_hash=pw2, role="contestant", team_name="测试队伍")
        db.session.add(contestant)

    db.session.commit()
    print("Seed data created: admin/admin123, player1/player123")
