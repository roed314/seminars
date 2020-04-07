# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import time
import datetime
from urllib.parse import urlparse

from flask import (Flask, g, render_template, request, make_response,
                   redirect, url_for, current_app, abort, session)
from flask_mail import Mail, Message

from lmfdb.logger import logger_file_handler, critical
from seminars.utils import topics, top_menu
from .seminar import seminars_header
from .talk import talks_header

SEMINARS_VERSION = "Seminars Release 0.1"

############################
#         Main app         #
############################

app = Flask(__name__)

mail_settings = {
    "MAIL_SERVER": 'smtp.gmail.com',
    "MAIL_PORT": 465,
    "MAIL_USE_TLS": False,
    "MAIL_USE_SSL": True,
    "MAIL_USERNAME": 'info.mathseminars@gmail.com',
    "MAIL_PASSWORD": os.environ.get('EMAIL_PASSWORD','')
}

app.config.update(mail_settings)
mail = Mail(app)

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
        app.config['SECRET_KEY'] = '''shh, it's a secret'''
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

# tell jinja to remove linebreaks
app.jinja_env.trim_blocks = True

# enable break and continue in jinja loops
app.jinja_env.add_extension('jinja2.ext.loopcontrols')
app.jinja_env.add_extension('jinja2.ext.do')

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
    data = {'info': {}, 'body_class': ''}

    # insert the default bread crumb hierarchy
    # overwrite this variable when you want to customize it
    # For example, [ ('Bread', '.'), ('Crumb', '.'), ('Hierarchy', '.')]
    data['bread'] = None

    # default title - Math seminars already included in base.html
    data['title'] = r''

    # meta_description appears in the meta tag "description"
    data['meta_description'] = r'Welcome to Math Seminars, a listing of mathematical research seminars, talks and conferences!'
    data['feedbackpage'] = r"https://forms.gle/5HoL6M6PSNEEwLZk6"
    data['LINK_EXT'] = lambda a, b: '<a href="%s" target="_blank">%s</a>' % (b, a)

    # debug mode?
    data['DEBUG'] = is_debug_mode()

    data['topics'] = topics()
    data['top_menu'] = top_menu()

    data['talks_header'] = talks_header
    data['seminars_header'] = seminars_header

    return data

##############################
#      Jinja formatters      #
##############################

# you can pass in a datetime.datetime python object and via
# {{ <datetimeobject> | fmtdatetime }} you can format it inside a jinja template
# if you want to do more than just the default, use it for example this way:
# {{ <datetimeobject>|fmtdatetime('%H:%M:%S') }}
@app.template_filter("fmtdatetime")
def fmtdatetime(value, format='%Y-%m-%d %H:%M:%S'):
    if isinstance(value, datetime.datetime):
        return value.strftime(format)
    else:
        return "-"

# You can use this formatter to turn newlines in a string into HTML line breaks
@app.template_filter("nl2br")
def nl2br(s):
    return s.replace('\n', '<br/>\n')

# You can use this formatter to encode a dictionary into a url string
@app.template_filter('urlencode')
def urlencode(kwargs):
    from six.moves.urllib.parse import urlencode
    return urlencode(kwargs)

# Use this to have None print as the empty string
@app.template_filter("blanknone")
def blanknone(x):
    if x is None:
        return ''
    return str(x)

##############################
#    Redirects    #
##############################

@app.before_request
def timezone_cookie_enforcer():
    urlparts = urlparse(request.url)
    if not (request.cookies.get('browser_timezone') or urlparts.path.startswith('/user/ics/')):
        # sets a cookie and goes back to the original url
        return render_template("timezone.html", url=request.url)


def timestamp():
    return '[%s UTC]' % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

@app.errorhandler(404)
def not_found_404(error):
    app.logger.info('%s 404 error for URL %s %s' % (timestamp(), request.url, error.description))
    messages = error.description if isinstance(error.description, (list, tuple)) else (error.description,)
    return render_template("404.html", title='Page Not Found', messages=messages), 404

@app.errorhandler(500)
def not_found_500(error):
    app.logger.error("%s 500 error on URL %s %s"%(timestamp(), request.url, error.args))
    return render_template("500.html", title='Error'), 500

@app.errorhandler(503)
def not_found_503(error):
    return render_template("503.html"), 503

##############################
#           Cookies          #
##############################

#@app.before_request
#def get_menu_cookie():
#    """
#    sets cookie for show/hide sidebar
#    """
#    g.show_menu = str(request.cookies.get('showmenu')) != "False"

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

@app.route("/acknowledgment")
def acknowledgment():
    bread = [("Acknowledgments" , '')]
    return render_template("acknowledgment.html", title="Acknowledgments", bread=bread)

@app.route("/editorial-board")
@app.route("/management-board")
@app.route("/management")
def editorial_board():
    t = "Editorial Board"
    b = [(t, url_for("editorial_board"))]
    return render_template('management.html', title=t, bread=b)

@app.route("/contact")
def contact():
    t = "Contact and Feedback"
    b = [(t, url_for("contact"))]
    return render_template('contact.html', title=t, body_class='', bread=b)

@app.route("/robots.txt")
def robots_txt():
    #if "mathseminars.org" in request.url_root.lower():
    #    fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "robots.txt")
    #    if os.path.exists(fn):
    #        return open(fn).read()
    return "User-agent: *\nDisallow: / \n"

# geeky pages have humans.txt
@app.route("/humans.txt")
def humans_txt():
    return render_template("acknowledgment.html", title="Acknowledgments")

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
    return sorted(links, key= lambda elt: elt[1])

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
    return {'color': Slate().dict()}

@app.route("/style.css")
def css():
    response = make_response(render_template("style.css"))
    response.headers['Content-type'] = 'text/css'
    # don't cache css file, if in debug mode.
    if current_app.debug:
        response.headers['Cache-Control'] = 'no-cache, no-store'
    else:
        response.headers['Cache-Control'] = 'public, max-age=600'
    return response

##############################
#       Static files         #
##############################

def root_static_file(name):
    def static_fn():
        fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", name)
        if os.path.exists(fn):
            return open(fn, "rb").read()
        critical("root_static_file: file %s not found!" % fn)
        return abort(404, 'static file %s not found.' % fn)
    app.add_url_rule('/%s' % name, 'static_%s' % name, static_fn)


for fn in ["favicon/apple-touch-icon-57x57.png",
           "favicon/apple-touch-icon-114x114.png",
           "favicon/apple-touch-icon-72x72.png",
           "favicon/apple-touch-icon-144x144.png",
           "favicon/apple-touch-icon-60x60.png",
           "favicon/apple-touch-icon-120x120.png",
           "favicon/apple-touch-icon-76x76.png",
           "favicon/apple-touch-icon-152x152.png",
           "favicon/favicon-196x196.png",
           "favicon/favicon-96x96.png",
           "favicon/favicon-32x32.png",
           "favicon/favicon-16x16.png",
           "favicon/favicon-128.png"]:
    root_static_file(fn)



##############################
#           Mail             #
##############################

def send_email(to, subject, message):
    from html2text import html2text
    app.logger.info("%s sending email to %s..." % (timestamp(), to))
    mail.send(Message(subject=subject,
                  html=message,
                  body=html2text(message), # a plain text version of our email
                  sender="info.mathseminars@gmail.com",
                  recipients=[to]))
    app.logger.info("%s done sending email to %s" % (timestamp(), to))


