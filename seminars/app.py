# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import time
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from flask import (
    Flask,
    render_template,
    request,
    make_response,
    redirect,
    url_for,
    current_app,
    abort,
)
from flask_mail import Mail, Message
from flask_cors import CORS

from lmfdb.logger import logger_file_handler
from seminars.utils import (
    domain,
    top_menu,
    topdomain,
    url_for_with_args,
)
from seminars.topic import topic_dag
from seminars.language import languages
from seminars.toggle import toggle, toggle3way
from seminars.knowls import static_knowl
from .seminar import series_header
from .talk import talks_header

SEMINARS_VERSION = "Seminars Release 0.1"

############################
#         Main app         #
############################

app = Flask(__name__, static_url_path="", static_folder="static",)
# disable cache temporarily
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

mail_settings = {
    "MAIL_SERVER": "heaviside.mit.edu",
    "MAIL_PORT": 465,
    "MAIL_USE_TLS": False,
    "MAIL_USE_SSL": True,
    "MAIL_USERNAME": "researchseminarsnoreply",
    "MAIL_PASSWORD": os.environ.get("EMAIL_PASSWORD_MIT", ""),
}

app.config.update(mail_settings)
mail = Mail(app)


# Enable cross origin for fonts
CORS(app, resources={r"/fontawesome/webfonts/*": {"origins": "*"}, r"/api/*": {"origins": "*"}})

############################
# App attribute functions  #
############################


def is_debug_mode():
    from flask import current_app

    return current_app.debug


app.is_running = False


def set_running():
    app.is_running = True


def is_running():
    return app.is_running


############################
# Global app configuration #
############################

app.logger.addHandler(logger_file_handler())

# If the debug toolbar is installed then use it
if app.debug:
    try:
        from flask_debugtoolbar import DebugToolbarExtension
        app.config["SECRET_KEY"] = """shh, it's a secret"""
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

# secret key, necessary for sessions and tokens
# sessions are in turn necessary for users to login
from lmfdb.utils.config import get_secret_key
app.secret_key = get_secret_key()

# tell jinja to remove linebreaks
app.jinja_env.trim_blocks = True

# enable break and continue in jinja loops
app.jinja_env.add_extension("jinja2.ext.loopcontrols")
app.jinja_env.add_extension("jinja2.ext.do")

# the following context processor inserts
#  * empty info={} dict variable
#  * body_class = ''
#  * bread = None for the default bread crumb hierarch
#  * meta_description, shortthanks, feedbackpage
#  * DEBUG and BETA variables storing whether running in each mode
@app.context_processor
def ctx_proc_userdata():
    # insert an empty info={} as default
    # set the body class to some default, blueprints should
    # overwrite it with their name, using @<blueprint_object>.context_processor
    # see http://flask.pocoo.org/docs/api/?highlight=context_processor#flask.Blueprint.context_processor
    data = {"info": {}, "body_class": ""}

    # insert the default bread crumb hierarchy
    # overwrite this variable when you want to customize it
    # For example, [ ('Bread', '.'), ('Crumb', '.'), ('Hierarchy', '.')]
    data["bread"] = None

    # default title - Research seminars already included in base.html
    data["title"] = r""

    # meta_description appears in the meta tag "description"
    data[
        "meta_description"
    ] = r"Welcome to {topdomain}, a list of research seminars and conferences!".format(topdomain = topdomain())
    data[
        "feedbackpage"
    ] = r"https://docs.google.com/forms/d/e/1FAIpQLSdJNJ0MwBXzqZleN5ibAI9u1gPPu9Aokzsy08ot802UitiDRw/viewform"
    data["LINK_EXT"] = lambda a, b: '<a href="%s" target="_blank">%s</a>' % (b, a)

    # debug mode?
    data["DEBUG"] = is_debug_mode()

    data["top_menu"] = top_menu()

    data["talks_header"] = talks_header
    data["series_header"] = series_header
    data["static_knowl"] = static_knowl
    data["domain"] = domain()
    data["topdomain"] = topdomain()
    data["toggle"] = toggle
    data["toggle3way"] = toggle3way
    data["topic_dag"] = topic_dag
    data["languages"] = languages
    data["url_for_with_args"] = url_for_with_args

    return data



##############################
#      Jinja formatters      #
##############################

# you can pass in a datetime python object and via
# {{ <datetimeobject> | fmtdatetime }} you can format it inside a jinja template
# if you want to do more than just the default, use it for example this way:
# {{ <datetimeobject>|fmtdatetime('%H:%M:%S') }}
@app.template_filter("fmtdatetime")
def fmtdatetime(value, format="%Y-%m-%d %H:%M:%S"):
    if isinstance(value, datetime):
        return value.strftime(format)
    else:
        return "-"


# You can use this formatter to turn newlines in a string into HTML line breaks
@app.template_filter("nl2br")
def nl2br(s):
    return s.replace("\n", "<br/>\n")


# You can use this formatter to encode a dictionary into a url string
@app.template_filter("urlencode")
def urlencode(kwargs):
    from six.moves.urllib.parse import urlencode

    return urlencode(kwargs)


# Use this to have None print as the empty string
@app.template_filter("blanknone")
def blanknone(x):
    if x is None:
        return ""
    return str(x)


##############################
#    Redirects and errors    #
##############################


@app.before_request
def netloc_redirect():
    """
        Redirect beantheory.org, www.mathseminars.org -> mathseminars.org
    """

    urlparts = urlparse(request.url)
    # *beantheory.org, *mathseminars.org, *rsem.org -> *researchseminars.org
    for otherdomain in ["beantheory.org", "mathseminars.org", "rsem.org"]:
        if urlparts.netloc.endswith(otherdomain):
            newnetloc = urlparts.netloc[:-len(otherdomain)] + "researchseminars.org"
            replaced = urlparts._replace(netloc=newnetloc, scheme="https")
            return redirect(urlunparse(replaced), code=301)
    if urlparts.netloc == "www.researchseminars.org":
        replaced = urlparts._replace(netloc="researchseminars.org", scheme="https")
        return redirect(urlunparse(replaced), code=301)


def timestamp():
    return "[%s UTC]" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


@app.errorhandler(404)
def not_found_404(error):
    app.logger.info("%s 404 error for URL %s %s" % (timestamp(), request.url, error.description))
    messages = (
        error.description if isinstance(error.description, (list, tuple)) else (error.description,)
    )
    return render_template("404.html", title="Page not found", messages=messages), 404


@app.errorhandler(500)
def not_found_500(error):
    app.logger.error("%s 500 error on URL %s %s" % (timestamp(), request.url, error.args))
    return render_template("500.html", title="Error"), 500


@app.errorhandler(503)
def not_found_503(error):
    return render_template("503.html"), 503


##############################
#       Top-level pages      #
##############################

# Code for the main browse pages is contained in the homepage/ folder


@app.route("/health")
@app.route("/alive")
def alive():
    """
    a basic health check
    """
    from . import db

    if db.is_alive():
        return "Bean Theory!"
    else:
        abort(503)


@app.route("/acknowledgments")
def acknowledgment():
    return render_template(
        "acknowledgments.html", title="Acknowledgments", section="Info", subsection="acknowledgments"
    )


@app.route("/contact")
def contact():
    t = "Contact and feedback"
    return render_template("contact.html", title=t, section="Info", subsection="contact")


@app.route("/robots.txt")
def robots_txt():
    if "researchseminars.org" in request.url_root.lower():
        fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "robots.txt")
        if os.path.exists(fn):
            return open(fn).read()
    return "User-agent: *\nDisallow: / \n"


# geeky pages have humans.txt
@app.route("/humans.txt")
def humans_txt():
    return render_template("acknowledgments.html", title="Acknowledgments")


def routes():
    """
    Returns all routes
    """
    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        # and rules that require parameters
        if "GET" in rule.methods:  # and has_no_empty_params(rule):
            try:
                url = url_for(rule.endpoint, **(rule.defaults or {}))
            except Exception:
                url = None
            links.append((url, str(rule)))
    return sorted(links, key=lambda elt: elt[1])


@app.route("/sitemap")
def sitemap():
    """
    Listing all routes
    """
    return (
        "<ul>"
        + "\n".join(
            [
                '<li><a href="{0}">{1}</a></li>'.format(url, endpoint)
                if url is not None
                else "<li>{0}</li>".format(endpoint)
                for url, endpoint in routes()
            ]
        )
        + "</ul>"
    )


##############################
#       CSS Styling          #
##############################


@app.context_processor
def add_colors():
    from .color import Slate

    return {"color": Slate().dict()}


@app.route("/style.css")
def css():
    response = make_response(render_template("style.css"))
    response.headers["Content-type"] = "text/css"
    # don't cache css file, if in debug mode.
    if current_app.debug:
        response.headers["Cache-Control"] = "no-cache, no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=600"
    return response


##############################
#           Mail             #
##############################


def send_email(to, subject, message):
    from html2text import html2text

    sender = "researchseminarsnoreply@math.mit.edu"
    app.logger.info("%s sending email from %s to %s..." % (timestamp(), sender, to))
    mail.send(
        Message(
            subject=subject,
            html=message,
            body=html2text(message),  # a plain text version of our email
            sender=sender,
            recipients=[to],
        )
    )
    app.logger.info("%s sending email from %s to %s..." % (timestamp(), sender, to))


def git_infos():
    try:
        from subprocess import Popen, PIPE

        # cwd should be the root of git repo
        cwd = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..")
        git_rev_cmd = """git rev-parse HEAD"""
        git_date_cmd = """git show --format="%ci" -s HEAD"""
        git_contains_cmd = """git branch --contains HEAD"""
        git_reflog_cmd = """git reflog -n5"""
        git_graphlog_cmd = """git log --graph  -n 10"""
        rev = Popen([git_rev_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        date = Popen([git_date_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        contains = Popen([git_contains_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        reflog = Popen([git_reflog_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        graphlog = Popen([git_graphlog_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        pairs = [
            [git_rev_cmd, rev],
            [git_date_cmd, date],
            [git_contains_cmd, contains],
            [git_reflog_cmd, reflog],
            [git_graphlog_cmd, graphlog],
        ]
        summary = "\n".join("$ %s\n%s" % (c, o.decode("utf8")) for c, o in pairs)
        return rev, date, summary
    except Exception:
        return "-", "-", "-"


@app.route("/raw_info")
def raw_info():
    from socket import gethostname

    output = ""
    output += "HOSTNAME = %s\n\n" % gethostname()
    output += "# PostgreSQL info\n"
    output += "\n# GIT info\n"
    output += git_infos()[-1]
    output += "\n\n"
    return output.replace("\n", "<br>")
