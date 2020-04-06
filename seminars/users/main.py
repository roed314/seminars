# -*- encoding: utf-8 -*-
# this holds all the flask-login specific logic (+ url mapping an rendering templates)
# for the user management
# author: harald schilly <harald.schilly@univie.ac.at>

from __future__ import absolute_import
import flask
from functools import wraps
from seminars.app import app, send_email
from lmfdb.logger import make_logger
from flask import render_template, request, Blueprint, url_for,  redirect, make_response, session, send_file
from flask_login import login_required, login_user, current_user, logout_user, LoginManager
from lmfdb.utils import flash_error
from markupsafe import Markup
from icalendar import Calendar
from io import BytesIO

from lmfdb import db
assert db
from seminars.utils import timezones
from seminars.tokens import generate_timed_token, read_timed_token, read_token
import pytz, datetime


login_page = Blueprint("user", __name__, template_folder='templates')
logger = make_logger(login_page)


login_manager = LoginManager()

from .pwdmanager import userdb, SeminarsUser, SeminarsAnonymousUser


@login_manager.user_loader
def load_user(uid):
    return SeminarsUser(uid)

login_manager.login_view = "user.info"

login_manager.anonymous_user = SeminarsAnonymousUser

def get_username(uid):
    """returns the name of user @uid"""
    return SeminarsUser(uid).name


# globally define user properties and username
@app.context_processor
def ctx_proc_userdata():
    userdata = {'user': current_user,
                'usertime': datetime.datetime.now(tz=current_user.tz)}
    # used to display name of locks
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
        return redirect(next or url_for(".info"))
    flash_error("Oops! Wrong username or password.")
    return redirect(url_for(".info"))


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
    if current_user.is_authenticated:
        title = section = "Account"
    else:
        title = section = "Login"
    return render_template("user-info.html",
                           info=info,
                           title=title,
                           section=section,
                           timezones=timezones,
                           user=current_user,
                           session=session)

# ./info again, but for POST!


@login_page.route("/set_info", methods=['POST'])
@login_required
def set_info():
    for k, v in request.form.items():
        print(k, v)
        setattr(current_user, k, v)
    previous_email = current_user.email
    if current_user.save():
        flask.flash(Markup("Thank you for updating your details!"))
    if previous_email != current_user.email:
        send_confirmation_email(current_user.email)
    return redirect(url_for(".info"))




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
    return redirect(url_for(".info"))





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
                               timezones=timezones,
                               )
    elif request.method == 'POST':
        email = request.form['email']
        from email_validator import validate_email, EmailNotValidError
        try:
            validate_email(email)
        except EmailNotValidError as e:
            flash_error("""Oops, email '%s' is not allowed. %s""", email, str(e))
            return redirect(url_for(".register"))

        pw1 = request.form['password1']
        pw2 = request.form['password2']
        if pw1 != pw2:
            flash_error("Oops, passwords do not match!")
            return redirect(url_for(".register"))

        if len(pw1) < 8:
            flash_error("Oops, password too short. Minimum 8 characters please!")
            return redirect(url_for(".register"))

        password = pw1
        name = request.form['name']
        affiliation = request.form['affiliation']
        homepage = request.form['homepage']
        if homepage and not homepage.startswith("http://") and not homepage.startswith("https://"):
            homepage = "http://" + homepage
        timezone = request.form['timezone']
        if timezone and timezone not in pytz.all_timezones:
            flash_error("Invalid timezone '%s'.", timezone)
            return redirect(url_for(".register"))

        if userdb.user_exists(email):
            flash_error("Sorry, email '%s' already exists!", email)
            return redirect(url_for(".register"))

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
        return redirect(url_for(".info"))


@login_page.route("/change_password", methods=['POST'])
@login_required
def change_password():
    email = current_user.email
    pw_old = request.form['oldpwd']
    if not current_user.authenticate(pw_old):
        flash_error("Ooops, old password is wrong!")
        return redirect(url_for(".info"))

    pw1 = request.form['password1']
    pw2 = request.form['password2']
    if pw1 != pw2:
        flash_error("Oops, new passwords do not match!")
        return redirect(url_for(".info"))

    if len(pw1) < 8:
        flash_error("Oops, password too short. Minimum 8 characters please!")
        return redirect(url_for(".info"))

    userdb.change_password(email, pw1)
    flask.flash(Markup("Your password has been changed."))
    return redirect(url_for(".info"))


@login_page.route("/logout")
@login_required
def logout():
    logout_user()
    flask.flash(Markup("You are logged out now. Have a nice day!"))
    return redirect(request.args.get("next") or request.referrer or url_for('.info'))


@login_page.route("/admin")
@login_required
@admin_required
def admin():
    return "success: only admins can read this!"







# confirm email

def generate_confirmation_token(email):
    return generate_timed_token(email, salt='confirm email')

def send_confirmation_email(email):
    token = generate_confirmation_token(email)
    confirm_url = url_for('.confirm_email', token=token, _external=True, _scheme='https')
    html = render_template('confirm_email.html', confirm_url=confirm_url)
    subject = "Please confirm your email"
    send_email(email, subject, html)




@login_page.route('/confirm/<token>')
def confirm_email(token):
    try:
        # the users have 24h to confirm their email
        email = read_timed_token(token, 'confirm email', 86400)
    except Exception:
        flash_error('The confirmation link is invalid or has expired.')
    user = SeminarsUser(email=email)
    if user.email_confirmed:
        flash_error('Email already confirmed.')
    else:
        user.email_confirmed = True
        user.save()
        flask.flash('You have confirmed your email. Thanks!', 'success')
    return redirect(url_for('.info'))




# reset password

def generate_password_token(email):
    return generate_timed_token(email, salt='reset password')

def send_reset_password(email):
    token = generate_password_token(email)
    reset_url = url_for('.reset_password_wtoken', token=token, _external=True, _scheme='https')
    html = render_template('reset_password_email.html', reset_url=reset_url)
    subject = "Resetting password"
    send_email(email, subject, html)

@login_page.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        return render_template("reset_password_ask_email.html",
                               title="Forgot Password",
                               )
    elif request.method == "POST":
        email = request.form['email']
        if userdb.user_exists(email):
            send_reset_password(email)
        flask.flash(Markup("Check your mailbox for instructions on how to reset your password"))
        return redirect(url_for(".info"))

@login_page.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password_wtoken(token):
    try:
        # the users have one hour to use previous token
        email = read_timed_token(token, 'reset password', 3600)
    except Exception:
        flash_error('The link is invalid or has expired.')
        return redirect(url_for('.info'))
    if not userdb.user_exists(email):
        flash_error('The link is invalid or has expired.')
        return redirect(url_for('.info'))
    if request.method == "GET":
        return render_template("reset_password_wtoken.html",
                               title="Reset password",
                               token=token
                               )
    elif request.method == 'POST':
        pw1 = request.form['password1']
        pw2 = request.form['password2']
        if pw1 != pw2:
            flash_error("Oops, passwords do not match!")
            return redirect(url_for(".reset_password_wtoken", token=token))

        if len(pw1) < 8:
            flash_error("Oops, password too short. Minimum 8 characters please!")
            return redirect(url_for(".reset_password_wtoken", token=token))

        userdb.change_password(email, pw1)
        flask.flash(Markup("Your password has been changed. Please login with your new password."))
        return redirect(url_for(".info"))


# endorsement

@login_required
@login_page.route('/endorse', methods=["POST"])
@creator_required
def get_endorsing_link():
    email = request.form['email']
    from email_validator import validate_email, EmailNotValidError
    try:
        validate_email(email)
    except EmailNotValidError as e:
        flash_error("""Oops, email '%s' is not allowed. %s""", email, str(e))
        return redirect(url_for(".info"))
    phd = bool(request.form.get('phd', False))
    link = endorser_link(current_user, email, phd)
    session['endorsing link'] = "<p>The link to endorse %s is:<br>%s</p>" % (email, link)
    return redirect(url_for(".info"))


def generate_endorsement_token(endorser, email, phd):
    rec = tuple([int(endorser.id), email, int(endorser.phd and phd)])
    return generate_timed_token(rec, "endorser")

def endorser_link(endorser, email, phd):
    token = generate_endorsement_token(endorser, email, phd)
    return url_for('.endorse_wtoken', token=token, _external=True, _scheme='https')


@login_page.route('/endorse/<token>')
@login_required
def endorse_wtoken(token):
    try:
        # tokens last forever
        endoser, email, phd = read_timed_token(token, 'endorser', None)
    except Exception:
        flash_error('The link is invalid or has expired.')
    if current_user.creator:
        flash_error('Account already has creator privileges.')
    elif current_user.email != email:
        flash_error('The link is not valid for this account.')
    elif not current_user.email_confirmed:
        flash_error('You must confirm your email first.')
    else:
        current_user.endorser = int(endorser)
        current_user.creator = True
        current_user.phd = bool(phd)
        current_user.save()
        flask.flash('You can now create seminars. Thanks!', 'success')
    return redirect(url_for('.info'))

@login_page.route('/subscribe/<shortname>')
@login_required
def seminar_subscriptions_add(shortname):
    current_user.seminar_subscriptions_add(shortname)
    current_user.save()
    return "success"

@login_page.route('/unsubscribe/<shortname>')
@login_required
def seminar_subscriptions_remove(shortname):
    current_user.seminar_subscriptions_remove(shortname)
    current_user.save()
    return "success"

@login_page.route('/subscribe/<shortname>/<ctr>')
@login_required
def talk_subscriptions_add(shortname, ctr):
    current_user.talk_subscriptions_add(shortname, int(ctr))
    current_user.save()
    return "success"

@login_page.route('/unsubscribe/<shortname>/<ctr>')
@login_required
def talk_subscriptions_remove(shortname, ctr):
    current_user.talk_subscriptions_remove(shortname, int(ctr))
    current_user.save()
    return "success"



@login_page.route('/ics/<token>')
def ics_file(token):
    try:
        uid = read_token(token, "ics")
        user = SeminarsUser(uid=int(uid))
        if not user.email_confirmed:
            return abort(404, 'Email has not yet been confirmed!')
    except Exception:
        return abort(404, 'Invalid link')


    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", "mathseminars.org")
    cal.add("CALSCALE", "GREGORIAN")
    cal.add("X-WR-CALNAME", "mathseminars.org")

    for talk in user.talks:
        cal.add_component(talk.event(user))
    for seminar in user.seminars:
        for talk in seminar.talks():
            cal.add_component(talk.event(user))
    bIO = BytesIO()
    bIO.write(cal.to_ical())
    bIO.seek(0)
    return send_file(bIO, attachment_filename='mathseminars.ics', as_attachment=True, add_etags=False)
