# -*- encoding: utf-8 -*-
# this holds all the flask-login specific logic (+ url mapping an rendering templates)
# for the user management
# author: harald schilly <harald.schilly@univie.ac.at>

from __future__ import absolute_import
import flask
from functools import wraps
from seminars.app import app
from lmfdb.logger import make_logger
from flask import render_template, request, Blueprint, url_for, make_response
from flask_login import login_required, login_user, current_user, logout_user, LoginManager, __version__ as FLASK_LOGIN_VERSION
from distutils.version import StrictVersion
from lmfdb.utils import flash_error
from markupsafe import Markup

from lmfdb import db
assert db
from seminars.utils import timezones
import pytz


login_page = Blueprint("users", __name__, template_folder='templates')
logger = make_logger(login_page)


login_manager = LoginManager()

# We log a warning if the version of flask-login is less than FLASK_LOGIN_LIMIT
FLASK_LOGIN_LIMIT = '0.3.0'
from .pwdmanager import userdb, SeminarsUser, SeminarsAnonymousUser


@login_manager.user_loader
def load_user(uid):
    return SeminarsUser(uid)

login_manager.login_view = "users.info"

# this anonymous user has the is_admin() method
login_manager.anonymous_user = SeminarsAnonymousUser

def get_username(uid):
    """returns the name of user @uid"""
    return SeminarsUser(uid).name


# globally define user properties and username
@app.context_processor
def ctx_proc_userdata():
    userdata = {}
    userdata['userid'] = 'anon' if current_user.is_anonymous() else current_user._uid
    userdata['username'] = 'Anonymous' if current_user.is_anonymous() else current_user.name

    if StrictVersion(FLASK_LOGIN_VERSION) > StrictVersion(FLASK_LOGIN_LIMIT):
        userdata['user_is_authenticated'] = current_user.is_authenticated
    else:
        userdata['user_is_authenticated'] = current_user.is_authenticated()

    userdata['user_is_admin'] = current_user.is_admin()
    userdata['user_is_editor'] = current_user.is_editor()
    userdata['get_username'] = get_username  # this is a function
    return userdata

# blueprint specific definition of the body_class variable
@login_page.context_processor
def body_class():
    return {'body_class': 'login'}



@login_page.route("/myself")
def info():
    info = {}
    info['login'] = url_for(".login")
    info['logout'] = url_for(".logout")
    info['user'] = current_user
    info['next'] = request.referrer
    return render_template("user-info.html",
                           info=info,
                           title="Userinfo",
                           timezones=timezones)

# ./info again, but for POST!


@login_page.route("/info", methods=['POST'])
@login_required
def set_info():
    for k, v in request.form.items():
        setattr(current_user, k, v)
    if current_user.save():
        flask.flash(Markup("Thank you for updating your details!"))
    return flask.redirect(url_for(".info"))


@login_page.route("/send_confirmation_email")
@login_required
def resend_confirmation_email():
    try:
        current_user.resend_email()
    except Exception as e:
        flash_error("%s",  str(e))
    return flask.redirect(url_for(".info"))



@login_page.route("/login", methods=["POST"])
def login(**kwargs):
    # login and validate the user …
    # remember = True sets a cookie to remember the user
    email = request.form["email"]
    password = request.form["password"]
    next = request.form["next"]
    remember = True if request.form["remember"] == "on" else False
    user = SeminarsUser(email=email)
    if user and user.authenticate(password):
        login_user(user, remember=remember)
        flask.flash(Markup("Hello %s, your login was successful!" % user.name))
        logger.info("login: '%s' - '%s'" % (user.get_id(), user.name))
        return flask.redirect(next or url_for(".info"))
    flash_error("Oops! Wrong username or password.")
    return flask.redirect(url_for(".info"))


def admin_required(fn):
    """
    wrap this around those entry points where you need to be an admin.
    """
    @wraps(fn)
    @login_required
    def decorated_view(*args, **kwargs):
        logger.info("admin access attempt by %s" % current_user.get_id())
        if not current_user.is_admin():
            return flask.abort(403)  # access denied
        return fn(*args, **kwargs)
    return decorated_view

def editor_required(fn):
    """
    wrap this around those entry points where you need to be an editor.
    """
    @wraps(fn)
    @login_required
    def decorated_view(*args, **kwargs):
        logger.info("admin access attempt by %s" % current_user.get_id())
        if not current_user.is_editor():
            return flask.abort(403)  # access denied
        return fn(*args, **kwargs)
    return decorated_view

# The analogous function creator_required is not defined, since we want to allow normal users to creat things that won't be displayed until they're approved as a creator.

def housekeeping(fn):
    """
    wrap this around maintenance calls, they are only accessible for
    admins and for localhost
    """
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        logger.info("housekeeping access attempt by %s" % request.remote_addr)
        if request.remote_addr in ["127.0.0.1", "localhost"]:
            return fn(*args, **kwargs)
        return admin_required(fn)(*args, **kwargs)
    return decorated_view





@login_page.route("/register/",  methods=['GET', 'POST'])
def register():
    if request.method == "GET":
        return render_template("register.html",
                               title="Register",
                               next=request.referrer or "/",
                               timezones=timezones,
                               )
    elif request.method == 'POST':
        email = request.form['email']
        from email_validator import validate_email, EmailNotValidError
        try:
            validate_email(email)
        except EmailNotValidError as e:
            flash_error("""Oops, email '%s' is not allowed. %s""", email, str(e))
            return flask.redirect(url_for(".register"))

        pw1 = request.form['password1']
        pw2 = request.form['password2']
        if pw1 != pw2:
            flash_error("Oops, passwords do not match!")
            return flask.redirect(url_for(".register"))

        if len(pw1) < 8:
            flash_error("Oops, password too short. Minimum 8 characters please!")
            return flask.redirect(url_for(".register"))

        password = pw1
        name = request.form['name']
        affiliation = request.form['affiliation']
        homepage = request.form['homepage']
        if homepage and not homepage.startswith("http://") and not homepage.startswith("https://"):
            homepage = "http://" + homepage
        timezone = request.form['timezone']
        if timezone not in pytz.all_timezones:
            flash_error("Invalid timezone '%s'.", timezone)
            return flask.redirect(url_for(".register"))

        if userdb.user_exists(email):
            flash_error("Sorry, email '%s' already exists!", email)
            return flask.redirect(url_for(".register"))

        newuser = userdb.new_user(email=email,
                                  password=password,
                                  name=name,
                                  affiliation=affiliation,
                                  homepage=homepage,
                                  timezone=timezone
                                  )
        login_user(newuser, remember=True)
        flask.flash(Markup("Hello %s! Congratulations, you are a new user!" % newuser.name))
        logger.info("new user: '%s' - '%s'" % (newuser.get_id(), newuser.name))
        return flask.redirect(url_for(".info"))


@login_page.route("/change_password", methods=['POST'])
@login_required
def change_password():
    email = current_user.email
    pw_old = request.form['oldpwd']
    if not current_user.authenticate(pw_old):
        flash_error("Ooops, old password is wrong!")
        return flask.redirect(url_for(".info"))

    pw1 = request.form['password1']
    pw2 = request.form['password2']
    if pw1 != pw2:
        flash_error("Oops, new passwords do not match!")
        return flask.redirect(url_for(".info"))

    if len(pw1) < 8:
        flash_error("Oops, password too short. Minimum 8 characters please!")
        return flask.redirect(url_for(".info"))

    userdb.change_password(email, pw1)
    flask.flash(Markup("Your password has been changed."))
    return flask.redirect(url_for(".info"))


@login_page.route("/logout")
@login_required
def logout():
    logout_user()
    flask.flash(Markup("You are logged out now. Have a nice day!"))
    return flask.redirect(request.args.get("next") or request.referrer or url_for('.info'))


@login_page.route("/admin")
@login_required
@admin_required
def admin():
    return "success: only admins can read this!"
