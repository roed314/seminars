# -*- encoding: utf-8 -*-
# this holds all the flask-login specific logic (+ url mapping an rendering templates)
# for the user management
# author: harald schilly <harald.schilly@univie.ac.at>

from __future__ import absolute_import
import flask
from functools import wraps
from seminars.app import app, send_email
from lmfdb.logger import make_logger
from flask import render_template, request, Blueprint, url_for, make_response
from flask_login import login_required, login_user, current_user, logout_user, LoginManager
from distutils.version import StrictVersion
from lmfdb.utils import flash_error
from markupsafe import Markup

from lmfdb import db
assert db
from seminars.utils import timezones, basic_top_menu
from seminars.tokens import generate_token, confirm_token
import pytz


login_page = Blueprint("user", __name__, template_folder='templates')
logger = make_logger(login_page)


login_manager = LoginManager()

from .pwdmanager import userdb, SeminarsUser, SeminarsAnonymousUser


@login_manager.user_loader
def load_user(uid):
    return SeminarsUser(uid)

login_manager.login_view = "user.info"

# this anonymous user has the is_admin() method
login_manager.anonymous_user = SeminarsAnonymousUser

def get_username(uid):
    """returns the name of user @uid"""
    return SeminarsUser(uid).name


# globally define user properties and username
@app.context_processor
def ctx_proc_userdata():
    userdata = {'user': current_user} # this should be sufficient....
    userdata['userid'] = 'anon' if current_user.is_anonymous() else current_user._uid
    userdata['username'] = 'Anonymous' if current_user.is_anonymous() else current_user.name
    userdata['user_is_authenticated'] = current_user.is_authenticated
    userdata['user_is_admin'] = current_user.is_admin()
    userdata['user_is_editor'] = current_user.is_editor()
    userdata['get_username'] = get_username  # this is a function
    return userdata

# blueprint specific definition of the body_class variable
@login_page.context_processor
def body_class():
    return {'body_class': 'login'}


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
        logger.info("editor access attempt by %s" % current_user.get_id())
        if not current_user.is_editor():
            return flask.abort(403)  # access denied
        return fn(*args, **kwargs)
    return decorated_view

def creator_required(fn):
    """
    wrap this around those entry points where you need to be a creator.
    """
    @wraps(fn)
    @login_required
    def decorated_view(*args, **kwargs):
        logger.info("creator access attempt by %s" % current_user.get_id())
        if not current_user.is_creator():
            return flask.abort(403)  # access denied
        return fn(*args, **kwargs)
    return decorated_view

@login_page.route("/info")
def info():
    menu = basic_top_menu()
    menu.pop(-1)
    title = "Account"
    return render_template("user-info.html",
                           info=info,
                           title=title,
                           top_menu=menu,
                           timezones=timezones,
                           user=current_user,
                           next=request.referrer)

# ./info again, but for POST!


@login_page.route("/set_info", methods=['POST'])
@login_required
def set_info():
    for k, v in request.form.items():
        setattr(current_user, k, v)
    previous_email = current_user.email
    if current_user.save():
        flask.flash(Markup("Thank you for updating your details!"))
    if previous_email != current_user.email:
        send_confirmation_email(current_user.email)
    return flask.redirect(url_for(".info"))


@login_page.route("/institutions")
@editor_required
def list_institutions():
    raise NotImplementedError

@login_page.route("/requests")
@editor_required
def list_requests():
    raise NotImplementedError

@login_page.route("/seminars")
@creator_required
def list_seminars():
    raise NotImplementedError


@login_page.route("/subscriptions")
@creator_required
def list_subscriptions():
    raise NotImplementedError



@login_page.route("/send_confirmation_email")
@login_required
def resend_confirmation_email():
    send_confirmation_email(current_user.email)
    flask.flash(Markup("New email has been sent!"))
    return flask.redirect(url_for(".info"))





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

        send_confirmation_email(email)
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




def generate_confirmation_token(email):
    return generate_token(email, salt='confirm email')

def generate_password_token(email):
    return generate_token(email, salt='reset password')

def send_confirmation_email(email):
    token = generate_confirmation_token(email)
    confirm_url = url_for('.confirm_email', token=token, _external=True, _scheme='https')
    html = render_template('confirm_email.html', confirm_url=confirm_url)
    subject = "Please confirm your email"
    send_email(email, subject, html)

def send_reset_password(email):
    token = generate_password_token(email)
    reset_url = url_for('.reset_password_wtoken', token=token, _external=True, _scheme='https')
    html = render_template('reset_password_email.html', reset_url=reset_url)
    subject = "Resetting password"
    send_email(email, subject, html)



@login_page.route('/confirm/<token>')
def confirm_email(token):
    try:
        # the users have 24h to confirm their email
        email = confirm_token(token, 'confirm email', 86400)
    except Exception:
        flash_error('The confirmation link is invalid or has expired.')
    user = SeminarsUser(email=email)
    if user.email_confirmed:
        flash_error('Account already confirmed. Please login.')
    else:
        user.email_confirmed = True
        user.save()
        flask.flash('You have confirmed your email. Thanks!', 'success')
    return flask.redirect(url_for('.info'))

@login_page.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        return render_template("reset_password_ask_email.html",
                               title="Forgot Password",
                               next=request.referrer or "/"
                               )
    elif request.method == "POST":
        email = request.form['email']
        if userdb.user_exists(email):
            send_reset_password(email)
        return flask.redirect(url_for(".info"))

@login_page.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password_wtoken(token):
    try:
        # the users have one hour to use previous token
        email = confirm_token(token, 'reset password', 3600)
    except Exception:
        flash_error('The link is invalid or has expired.')
        return redirect(url_for('.info'))
    if not userdb.exists(email):
        flash_error('The link is invalid or has expired.')
        return redirect(url_for('.info'))
    if request.method == "GET":
        return render_template("reset_password_wtoken.html",
                               title="Reset password",
                               next=request.referrer or "/",
                               token=token
                               )
    elif request.method == 'POST':
        pw1 = request.form['password1']
        pw2 = request.form['password2']
        if pw1 != pw2:
            flash_error("Oops, passwords do not match!")
            return flask.redirect(url_for(".reset_password_wtoken", token=token))

        if len(pw1) < 8:
            flash_error("Oops, password too short. Minimum 8 characters please!")
            return flask.redirect(url_for(".reset_password_wtoken", token=token))

        userdb.change_password(email, pw1)
        flask.flash(Markup("Your password has been changed. Please login with your new password."))
        return flask.redirect(url_for(".info"))


