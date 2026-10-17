from flask import render_template, request, redirect, url_for, flash, jsonify, Blueprint
from flask_login import current_user, login_required, logout_user, login_user
from models import db, User, GroupMember


def get_or_create_welcome_group():
    from models import Group

    group = Group.query.filter_by(name="Welcome", is_default=True).first()
    if group is None:
        group = Group(name="Welcome", is_default=True)
        db.session.add(group)
        db.session.flush()
    return group


def create_blueprint():
    bp = Blueprint("auth", __name__, template_folder="../../templates")

    @bp.route("/", methods=["GET"])
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("chat.chat"))
        return render_template("index.html")

    @bp.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for("chat"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash("Username and password are required.")
            elif User.query.filter_by(username=username).first():
                flash("That username is already taken.")
            else:
                user = User(username=username)
                user.set_password(password)
                db.session.add(user)

                welcome_group = get_or_create_welcome_group()
                db.session.add(GroupMember(user=user, group=welcome_group))
                db.session.commit()

                login_user(user)
                flash("Welcome! You have been added to the Welcome group.")
                return redirect(url_for("chat"))

        return render_template("signup.html")

    @bp.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("chat"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = User.query.filter_by(username=username).first()
            if user is not None and user.check_password(password):
                login_user(user)
                return redirect(request.args.get("next") or url_for("chat"))

            flash("Invalid username or password.")

        return render_template("login.html")

    @bp.route("/logout", methods=["GET"])
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    return bp


auth_bp = create_blueprint()
