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
from email_validator import validate_email, EmailNotValidError

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
def load_user(email):
    return SeminarsUser(email)

login_manager.login_view = "users.info"

# this anonymous user has the is_admin() method
login_manager.anonymous_user = SeminarsAnonymousUser


def get_username(email):
    """returns the name of user @uid"""
    return SeminarsUser(email).name

# globally define user properties and username


@app.context_processor
def ctx_proc_userdata():
    userdata = {}
    userdata['user_can_write'] = userdb.can_read_write_userdb()
    if not userdata['user_can_write']:
        userdata['userid'] = 'anon'
        userdata['username'] = 'Anonymous'
        userdata['user_is_admin'] = False
        userdata['user_is_authenticated'] = False
        userdata['user_can_review_knowls'] = False
        userdata['get_username'] = SeminarsAnonymousUser().name # this is a function

    else:
        userdata['userid'] = 'anon' if current_user.is_anonymous() else current_user._uid
        userdata['username'] = 'Anonymous' if current_user.is_anonymous() else current_user.name

        if StrictVersion(FLASK_LOGIN_VERSION) > StrictVersion(FLASK_LOGIN_LIMIT):
            userdata['user_is_authenticated'] = current_user.is_authenticated
        else:
            userdata['user_is_authenticated'] = current_user.is_authenticated()

        userdata['user_is_admin'] = current_user.is_admin()
        userdata['get_username'] = get_username  # this is a function
    return userdata

# blueprint specific definition of the body_class variable


@login_page.context_processor
def body_class():
    return {'body_class': 'login'}

# the following doesn't work as it should, also depends on blinker python lib
# flask signal when a user logs in. we record the last logins in the user's data
# http://flask.pocoo.org/docs/signals/
# def log_login_callback(cur_app, user = None):
#  cur_user = user or current_user
#  logger.info(">> curr_app: %s   user: %s" % (cur_app, cur_user))
#
# from flask.ext.login import user_logged_in, user_login_confirmed
# user_logged_in.connect(log_login_callback)
# user_login_confirmed.connect(log_login_callback)




@login_page.route("/")
@login_required
def list():
    COLS = 5
    users = userdb.get_user_list()
    # attempt to sort by last name
    users = sorted(users, key=lambda x: x[1].strip().split(" ")[-1].lower())
    if len(users)%COLS:
        users += [{} for i in range(COLS-len(users)%COLS)]
    n = len(users)/COLS
    user_rows = tuple(zip(*[users[i*n: (i + 1)*n] for i in range(COLS)]))
    return render_template("user-list.html", title="All Users",
                           user_rows=user_rows)


@login_page.route("/change_colors/<int:scheme>")
@login_required
def change_colors(scheme):
    userid = current_user.get_id()
    userdb.change_colors(userid, scheme)
    flask.flash(Markup("Color scheme successfully changed"))
    response = make_response(flask.redirect(url_for(".info")))
    response.set_cookie('color', str(scheme))
    return response

@login_page.route("/myself")
def info():
    info = {}
    info['login'] = url_for(".login")
    info['logout'] = url_for(".logout")
    info['user'] = current_user
    info['next'] = request.referrer
    from lmfdb.utils.color import all_color_schemes
    return render_template("user-info.html",
                           all_colors=all_color_schemes.values(),
                           info=info, title="Userinfo")

# ./info again, but for POST!


@login_page.route("/info", methods=['POST'])
@login_required
def set_info():
    for k, v in request.form.items():
        setattr(current_user, k, v)
    current_user.save()
    flask.flash(Markup("Thank you for updating your details!"))
    return flask.redirect(url_for(".info"))





@login_page.route("/login", methods=["POST"])
def login(**kwargs):
    # login and validate the user …
    # remember = True sets a cookie to remember the user
    email = request.form["email"]
    password = request.form["password"]
    next = request.form["next"]
    remember = True if request.form["remember"] == "on" else False
    user = SeminarsUser(email)
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
    uid = current_user.get_id()
    pw_old = request.form['oldpwd']
    if not current_user.authenticate(pw_old):
        flash_error("Ooops, old password is wrong!")
        return flask.redirect(url_for(".info"))

    pw1 = request.form['password1']
    pw2 = request.form['password2']
    if pw1 != pw2:
        flash_error("Oops, new passwords do not match!")
        return flask.redirect(url_for(".info"))

    userdb.change_password(uid, pw1)
    flask.flash(Markup("Your password has been changed."))
    return flask.redirect(url_for(".info"))


@login_page.route("/logout")
@login_required
def logout():
    # FIXME delete color cookie
    logout_user()
    flask.flash(Markup("You are logged out now. Have a nice day!"))
    return flask.redirect(request.args.get("next") or request.referrer or url_for('.info'))


@login_page.route("/admin")
@login_required
@admin_required
def admin():
    return "success: only admins can read this!"
