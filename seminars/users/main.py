# -*- encoding: utf-8 -*-
from __future__ import absolute_import
import flask, re, json
from email_validator import validate_email, EmailNotValidError
from urllib.parse import urlencode, quote
from functools import wraps
from seminars.app import app, send_email
from lmfdb.logger import make_logger
from flask import (
    render_template,
    request,
    Blueprint,
    url_for,
    redirect,
    make_response,
    session,
    Response,
)
from flask_login import (
    login_required,
    login_user,
    current_user,
    logout_user,
    LoginManager,
)
from lmfdb.utils import flash_error
from markupsafe import Markup

from seminars import db

from seminars.utils import (
    ics_file,
    process_user_input,
    format_errmsg,
    format_input_errmsg,
    show_input_errors,
    timestamp,
    timezones,
    topdomain,
    flash_infomsg,
)

from seminars.tokens import generate_timed_token, read_timed_token, read_token
from datetime import datetime

def user_options():
    author_ids = sorted(list(db.author_ids.search({})),key=lambda r: r["name"].lower())
    return { 'author_ids' : author_ids, 'timezones' : timezones }

login_page = Blueprint("user", __name__, template_folder="templates")
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
    userdata = {
        "user": current_user,
        "usertime": datetime.now(tz=current_user.tz),
    }
    # used to display name of locks
    userdata["get_username"] = get_username  # this is a function
    return userdata


# blueprint specific definition of the body_class variable
@login_page.context_processor
def body_class():
    return {"body_class": "login"}


@login_page.route("/login", methods=["POST"])
def login(**kwargs):
    # login and validate the user …
    email = request.form["email"]
    password = request.form["password"]
    if not email or not password:
        flash_error("Oops! Wrong username or password.")
        return redirect(url_for(".info"))
    # we always remember
    remember = True  # if request.form["remember"] == "on" else False
    user = SeminarsUser(email=email)
    if user.email and user.check_password(password):
        # this is where we set current_user = user
        login_user(user, remember=remember)
        if user.name:
            flask.flash(Markup("Hello %s, your login was successful!" % user.name))
        else:
            flask.flash(Markup("Hello, your login was successful!"))
        logger.info("login: '%s' - '%s'" % (user.get_id(), user.name))
        return redirect(request.form.get("next") or url_for(".info"))
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
        if not current_user.is_admin:
            return flask.abort(403)  # access denied
        return fn(*args, **kwargs)

    return decorated_view


def creator_required(fn):
    """
    wrap this around those entry points where you need to be a creator.
    """

    @wraps(fn)
    @email_confirmed_required
    def decorated_view(*args, **kwargs):
        logger.info("creator access attempt by %s" % current_user.get_id())
        if not current_user.is_creator:
            return flask.abort(403)  # access denied
        return fn(*args, **kwargs)

    return decorated_view


def email_confirmed_required(fn):
    """
    wrap this around those entry points where you need to be a creator.
    """

    @wraps(fn)
    @login_required
    def decorated_view(*args, **kwargs):
        logger.info("email confirmed access attempt by %s" % current_user.get_id())
        if not current_user.email_confirmed:
            flash_error("Oops, you haven't yet confirmed your email")
            return redirect(url_for("user.info"))
        return fn(*args, **kwargs)

    return decorated_view


@login_page.route("/info")
def info():
    if current_user.is_authenticated:
        title = section = "Account"
    else:
        title = section = "Login"
    return render_template(
        "user-info.html",
        next=request.args.get("next", ''),
        title=title,
        section=section,
        user=current_user,
        options=user_options(),
        session=session,
    )

@login_page.route("/display_data")
def display_data():
    # Return user data used in displaying talks on the browse page as json
    data = {"authenticated": current_user.is_authenticated,
            "timezone": current_user.timezone,
            "seminar_subscriptions": current_user.seminar_subscriptions,
            "talk_subscriptions": current_user.talk_subscriptions}
    return Response(json.dumps(data), mimetype="application/json")

# ./info again, but for POST!


@login_page.route("/set_info", methods=["POST"])
@login_required
def set_info():
    errmsgs = []
    data = {}
    previous_email = current_user.email
    external_ids = []
    for col, val in request.form.items():
        if col == "ids":
            continue
        try:
            # handle external id values separately, these are not named columns, they all go in external_ids
            if col.endswith("_value"):
                name = col.split("_")[0]
                value = val.strip()
                # external id values are validated against regex by the form, but the user can still click update
                if value:
                    if not re.match(db.author_ids.lookup(name,"regex"),value):
                        errmsgs.append(format_input_errmsg("Invalid %s format"%(db.author_ids.lookup(name,"display_name")), val, name))
                    else:
                        external_ids.append(name + ":" + value)
                continue
            typ = db.users.col_type[col]
            data[col] = process_user_input(val, col, typ)
        except Exception as err:  # should only be ValueError's but let's be cautious
            errmsgs.append(format_input_errmsg(err, val, col))
    if not data.get("name"):
        errmsgs.append(format_errmsg('Name cannot be left blank.  See the user behavior section of our <a href="' + url_for('policies') + '" target="_blank">policies</a> page for details.'))
    if errmsgs:
        return show_input_errors(errmsgs)
    data["external_ids"] = external_ids
    for k in data.keys():
        setattr(current_user, k, data[k])
    if current_user.save():
        flask.flash(Markup("Thank you for updating your details!"))
    if previous_email != current_user.email:
        if send_confirmation_email(current_user.email):
            flask.flash(Markup("New confirmation email has been sent!"))
    return redirect(url_for(".info"))


@login_page.route("/send_confirmation_email")
@login_required
def resend_confirmation_email():
    if send_confirmation_email(current_user.email):
        flask.flash(Markup("New confirmation email has been sent!"))
    return redirect(url_for(".info"))


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


@login_page.route("/register/", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        pw1 = request.form["password1"]
        pw2 = request.form["password2"]
        try:
            email = validate_email(email)['email']
        except EmailNotValidError as e:
            flash_error("""Oops, email '%s' is not allowed. %s""", email, str(e))
            return make_response(render_template("register.html", title="Register", email=email))
        if pw1 != pw2:
            flash_error("Oops, passwords do not match!")
            return make_response(render_template("register.html", title="Register", email=email))

        if len(pw1) < 8:
            flash_error("Oops, password too short.  Minimum 8 characters, please!")
            return make_response(render_template("register.html", title="Register", email=email))

        password = pw1
        if userdb.user_exists(email=email):
            flash_error("The email address '%s' is already registered!", email)
            return make_response(render_template("register.html", title="Register", email=email))

        newuser = userdb.new_user(email=email, password=password,)

        send_confirmation_email(email)
        login_user(newuser, remember=True)
        flask.flash(Markup("Hello! Congratulations, you are a new user!"))
        logger.info("new user: '%s' - '%s'" % (newuser.get_id(), newuser.email))
        return redirect(url_for(".info"))
    return render_template("register.html", title="Register", email="")


@login_page.route("/change_password", methods=["POST"])
@login_required
def change_password():
    email = current_user.email
    pw_old = request.form["oldpwd"]
    if not current_user.check_password(pw_old):
        flash_error("Oops, old password is wrong!")
        return redirect(url_for(".info"))

    pw1 = request.form["password1"]
    pw2 = request.form["password2"]
    if pw1 != pw2:
        flash_error("Oops, new passwords do not match!")
        return redirect(url_for(".info"))

    if len(pw1) < 8:
        flash_error("Oops, password too short.  Minimum 8 characters, please!")
        return redirect(url_for(".info"))

    userdb.change_password(email, pw1)
    flask.flash(Markup("Your password has been changed."))
    return redirect(url_for(".info"))


@login_page.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flask.flash(Markup("You are now logged out.  Have a nice day!"))
    return redirect(url_for(".info"))

@login_page.route("/permanently_deleteme")
@login_required
def permanently_deleteme():
    current_user.delete()
    logout_user()
    flask.flash(Markup("Your account has been deleted.  Have a nice day!"))
    return redirect(url_for(".info"))


@login_page.route("/admin")
@admin_required
def admin():
    return "success: only admins can read this!"


@login_page.route("/loginas/<emailorid>")
@admin_required
def loginas(emailorid):
    try:
        uid = int(emailorid)
        user = SeminarsUser(uid=uid)
    except ValueError:
        email = emailorid
        user = SeminarsUser(email=email)
    if user.id:
        logout_user()
        login_user(user)
        flask.flash(Markup("Using your superpowers, you are now logged in as %s" % (user.email)))
        return redirect(url_for(".info"))
    else:
        return "No user matches the email/id provided."

# confirm email


def generate_confirmation_token(email):
    return generate_timed_token(email, salt="confirm email")


def send_confirmation_email(email):
    token = generate_confirmation_token(email)
    confirm_url = url_for(".confirm_email", token=token, _external=True, _scheme="https")
    html = render_template("confirm_email.html", confirm_url=confirm_url)
    subject = "Please confirm your email"
    try:
        send_email(email, subject, html)
        return True
    except:
        import sys

        flash_error(
            'Unable to send email confirmation link; please contact <a href="mailto:researchseminars@math.mit.edu">researchseminars@math.mit.edu</a> directly to confirm your email.'
        )
        app.logger.error("%s unable to send email to %s due to error: %s" % (timestamp(), email, sys.exc_info()[0]))
        return False




@login_page.route("/confirm/<token>")
@login_required
def confirm_email(token):
    try:
        # the users have 24h to confirm their email
        email = read_timed_token(token, "confirm email", 86400)
    except Exception:
        flash_error("The confirmation link is invalid or has expired.")
    else:
        if current_user.email.lower() != email.lower():
            flash_error("The link is not valid for this account.")
        elif current_user.email_confirmed:
            flash_error("Email already confirmed.")
        else:
            current_user.email_confirmed = True
            current_user.save()
            flask.flash("Thank you for confirming your email!", "success")
    return redirect(url_for(".info"))


# reset password


def generate_password_token(email):
    return generate_timed_token(email, salt="reset password")


def send_reset_password(email):
    token = generate_password_token(email)
    reset_url = url_for(".reset_password_wtoken", token=token, _external=True, _scheme="https")
    html = render_template("reset_password_email.html", reset_url=reset_url)
    subject = "Resetting password"
    send_email(email, subject, html)


@login_page.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form["email"]
        if userdb.user_exists(email):
            send_reset_password(email)
        flask.flash(Markup("Check your email's inbox for instructions on how to reset your password."))
        return redirect(url_for(".info"))
    return render_template("reset_password_ask_email.html", title="Forgot Password",)


@login_page.route("/reset/<token>", methods=["GET", "POST"])
def reset_password_wtoken(token):
    try:
        # the users have one hour to use previous token
        email = read_timed_token(token, "reset password", 3600)
    except Exception:
        flash_error("The link is invalid or has expired.")
        return redirect(url_for(".info"))
    if not userdb.user_exists(email):
        flash_error("The link is invalid or has expired.")
        return redirect(url_for(".info"))
    if request.method == "POST":
        pw1 = request.form["password1"]
        pw2 = request.form["password2"]
        if pw1 != pw2:
            flash_error("Oops, passwords do not match!")
            return redirect(url_for(".reset_password_wtoken", token=token))

        if len(pw1) < 8:
            flash_error("Oops, password too short.  Minimum 8 characters, please!")
            return redirect(url_for(".reset_password_wtoken", token=token))

        userdb.change_password(email, pw1)
        flask.flash(Markup("Your password has been changed.  Please login with your new password."))
        return redirect(url_for(".info"))
    return render_template("reset_password_wtoken.html", title="Reset password", token=token)


@login_page.route("/reset_api_token")
@creator_required
def reset_api_token():
    userdb.reset_api_token(current_user._uid)
    return redirect(url_for(".info"))

# endorsement


@login_page.route("/endorse", methods=["POST"])
@creator_required
def get_endorsing_link():
    email = request.form["email"].strip()
    try:
        email = validate_email(email)["email"]
    except EmailNotValidError as e:
        flash_error("""Oops, email '%s' is not allowed. %s""", email, str(e))
        return redirect(url_for(".info"))
    rec = userdb.lookup(email, ["name", "creator", "email_confirmed"])
    if rec is None or not rec["email_confirmed"]:  # No account or email unconfirmed
        if db.preendorsed_users.count({'email':email}):
            flash_infomsg("The email address %s has already been pre-endorsed.", email)
            return redirect(url_for(".info"))
        else:
            db.preendorsed_users.insert_many([{"email": email, "endorser": current_user._uid}])
            to_send = """Hello,

    I am offering you permission to add content (e.g., create a seminar)
    on the {topdomain} website.

    To accept this invitation:

    1. Register at {register} using this email address.

    2. Click on the link the system emails you, to confirm your email address.

    3. Now any content you create will be publicly viewable.


    Best,
    {name}
    """.format(
                name = current_user.name,
                topdomain = topdomain(),
                register = url_for('.register', _external=True, _scheme='https'),
            )
            data = {
                "body": to_send,
                "subject": "An invitation to collaborate on " + topdomain(),
            }
            endorsing_link = """
    <p>
    The person {email} will be able to create content after registering and confirming the email address.</br>
    <button onClick="window.open('mailto:{email}?{msg}')">
    Send email
    </button> to let them know.
    </p>
    """.format(
                email=email, msg=urlencode(data, quote_via=quote)
            )
        flash_infomsg("""
            The person %s will be able to create content after registering and confirming the email address.  Click the "Send email" button below to let them know.""",email)
        session["endorsing link"] = endorsing_link
        return redirect(url_for(".info"))
    else:
        target_name = rec["name"]
        if rec["creator"]:
            flash_infomsg("%s is already able to create content.", target_name)
            return redirect(url_for(".info"))
        else:
            welcome = "Hello" if not target_name else ("Dear " + target_name)
            to_send = """{welcome},<br>
<p>
You have been endorsed you on {topdomain} and any content you create will
be publicly viewable.
</p>
<p>
Thanks for using {topdomain}!
</p>

""".format(
                welcome = welcome,
                topdomain = topdomain()
            )
            subject = "Endorsement to create content on " + topdomain()
            send_email(email, subject, to_send)
            userdb.make_creator(email, int(current_user.id))
            flash_infomsg("%s is now able to create content.", target_name if target_name else email)
            return redirect(url_for(".info"))
    raise Exception("The function get_endorsing_link did not return a value")

def generate_endorsement_token(endorser, email):
    rec = [int(endorser.id), email]
    return generate_timed_token(rec, "endorser")


def endorser_link(endorser, email):
    token = generate_endorsement_token(endorser, email)
    return url_for(".endorse_wtoken", token=token, _external=True, _scheme="https")


@login_page.route("/endorse/<token>")
@login_required
@email_confirmed_required
def endorse_wtoken(token):
    try:
        # tokens last forever
        endorser, email = read_timed_token(token, "endorser", None)
    except Exception:
        return flask.abort(404, "The link is invalid or has expired.")
        return redirect(url_for(".info"))
    if current_user.is_creator:
        flash_error("Account already has creator privileges.")
    elif current_user.email.lower() != email.lower():
        flash_error("The link is not valid for this account.")
    else:
        current_user.endorser = int(endorser)  # must set endorser first
        current_user.creator = True  # this will update the db
    return redirect(url_for(".info"))


@login_page.route("/subscribe/<shortname>")
@login_required
def seminar_subscriptions_add(shortname):
    code, msg = current_user.seminar_subscriptions_add(shortname)
    current_user.save()
    return msg, code


@login_page.route("/unsubscribe/<shortname>")
@login_required
def seminar_subscriptions_remove(shortname):
    code, msg = current_user.seminar_subscriptions_remove(shortname)
    current_user.save()
    return msg, code


@login_page.route("/subscribe/<shortname>/<ctr>")
@login_required
def talk_subscriptions_add(shortname, ctr):
    code, msg = current_user.talk_subscriptions_add(shortname, int(ctr))
    current_user.save()
    return msg, code


@login_page.route("/unsubscribe/<shortname>/<ctr>")
@login_required
def talk_subscriptions_remove(shortname, ctr):
    code, msg = current_user.talk_subscriptions_remove(shortname, int(ctr))
    current_user.save()
    return msg, code


@login_page.route("/ics/<token>")
def user_ics_file(token):
    from itsdangerous.exc import BadSignature
    try:
        try:
            uid = read_token(token, "ics")
        except BadSignature:
            # old key
            return flask.abort(404, "Invalid link")
        user = SeminarsUser(uid=int(uid))
        if not user.email_confirmed:
            return flask.abort(404, "The email address has not yet been confirmed!")
    except Exception:
        return flask.abort(404, "Invalid link")

    talks = [t for t in user.talks if not (t.hidden or t.seminar.visibility == 0)]
    for seminar in user.seminars:
        # Organizers may have hidden seminar
        if seminar.visibility == 0:
            continue
        for talk in seminar.talks():
            talks.append(talk)
    return ics_file(
        talks=talks,
        filename="seminars.ics",
        user=user)



@login_page.route("/public/")
@login_required
@email_confirmed_required
def public_users():
    user_list = sorted(
        [
            (r["affiliation"], r["name"], r["homepage"])
            for r in db.users.search({"homepage": {"$ne": ""}, "affiliation": {"$ne": ""}, "name": {"$ne": ""}, "creator": True})
        ]
    )
    user_list += sorted(
        [
            (r["affiliation"], r["name"], r["homepage"])
            for r in db.users.search({"homepage": {"$ne": ""}, "affiliation":"", "name": {"$ne": ""}, "creator": True})
        ]
    )
    return render_template("public_users.html", title="Public users", public_users=user_list)
