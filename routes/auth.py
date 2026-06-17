import bcrypt
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("用户名和密码不能为空", "error")
            return render_template("auth/login.html")

        user = User.query.filter_by(username=username).first()
        if not user or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            flash("用户名或密码错误", "error")
            return render_template("auth/login.html")

        session["user_id"] = user.id
        session["username"] = user.username
        session["role"] = user.role

        if user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("contestant.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        team_name = request.form.get("team_name", "").strip()

        if not username or not password:
            flash("用户名和密码不能为空", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(username=username).first():
            flash("用户名已存在", "error")
            return render_template("auth/register.html")

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, password_hash=pw_hash, role="contestant", team_name=team_name)
        db.session.add(user)
        db.session.commit()

        flash("注册成功，请登录", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
