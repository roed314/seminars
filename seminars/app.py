# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import time
import datetime

from flask import (Flask, g, render_template, request, make_response,
                   redirect, url_for, current_app, abort)
from lmfdb.utils import (
    SearchArray, TextBox, SelectBox, YesNoBox,
    to_dict, search_wrap
)

from lmfdb.logger import logger_file_handler, critical

SEMINARS_VERSION = "Seminars Release 0.1"

############################
#         Main app         #
############################

app = Flask(__name__)

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
#  * title = 'LMFDB'
#  * meta_description, shortthanks, feedbackpage
#  * DEBUG and BETA variables storing whether running in each mode
@app.context_processor
def ctx_proc_userdata():
    # insert an empty info={} as default
    # set the body class to some default, blueprints should
    # overwrite it with their name, using @<blueprint_object>.context_processor
    # see http://flask.pocoo.org/docs/api/?highlight=context_processor#flask.Blueprint.context_processor
    vars = {'info': {}, 'body_class': ''}

    # insert the default bread crumb hierarchy
    # overwrite this variable when you want to customize it
    # For example, [ ('Bread', '.'), ('Crumb', '.'), ('Hierarchy', '.')]
    vars['bread'] = None

    # default title
    vars['title'] = r'Bean Theory'

    # LMFDB version number displayed in footer
    vars['version'] = SEMINARS_VERSION

    # meta_description appears in the meta tag "description"
    vars['meta_description'] = r'Welcome to Bean Theory, a listing of mathematical research seminars and conferences.'
    vars['shortthanks'] = r'This project is supported by <a href="%s">grants</a> from the US National Science Foundation, the UK Engineering and Physical Sciences Research Council, and the Simons Foundation.' % (url_for('acknowledgment') + "#sponsors")
    vars['feedbackpage'] = r"https://docs.google.com/spreadsheet/viewform?formkey=dDJXYXBleU1BMTFERFFIdjVXVmJqdlE6MQ"
    vars['LINK_EXT'] = lambda a, b: '<a href="%s" target="_blank">%s</a>' % (b, a)

    # debug mode?
    vars['DEBUG'] = is_debug_mode()

    return vars

##############################
# Bottom link to google code #
##############################

branch = "bean"

def git_infos():
    try:
        from subprocess import Popen, PIPE
        # cwd should be the root of git repo
        cwd = os.path.join(os.path.dirname(os.path.realpath(__file__)),"..")
        git_rev_cmd = '''git rev-parse HEAD'''
        git_date_cmd = '''git show --format="%ci" -s HEAD'''
        git_contains_cmd = '''git branch --contains HEAD'''
        git_reflog_cmd = '''git reflog -n5'''
        git_graphlog_cmd = '''git log --graph  -n 10'''
        rev = Popen([git_rev_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        date = Popen([git_date_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        contains = Popen([git_contains_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        reflog = Popen([git_reflog_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        graphlog = Popen([git_graphlog_cmd], shell=True, stdout=PIPE, cwd=cwd).communicate()[0]
        pairs = [[git_rev_cmd, rev],
                [git_date_cmd, date],
                [git_contains_cmd, contains],
                [git_reflog_cmd, reflog],
                [git_graphlog_cmd, graphlog]]
        summary = "\n".join("$ %s\n%s" % (c, o) for c, o in pairs)
        return rev, date, summary
    except Exception:
        return '-', '-', '-'


git_rev, git_date, _  = git_infos()

# Creates link to the source code at the most recent commit.
_url_source = 'https://github.com/LMFDB/lmfdb/tree/'
_current_source = '<a href="%s%s">%s</a>' % (_url_source, git_rev, "Source")

# Creates link to the list of revisions on the master, where the most recent commit is on top.
_url_changeset = 'https://github.com/LMFDB/lmfdb/commits/%s' % branch
_latest_changeset = '<a href="%s">%s</a>' % (_url_changeset, git_date)

@app.context_processor
def link_to_current_source():
    return {'current_source': _current_source,
            'latest_changeset': _latest_changeset}

##############################
#      Jinja formatters      #
##############################

# you can pass in a datetime.datetime python object and via
# {{ <datetimeobject> | fmtdatetime }} you can format it inside a jinja template
# if you want to do more than just the default, use it for example this way:
# {{ <datetimeobject>|fmtdatetime('%H:%M:%S') }}
@app.template_filter("fmtdatetime")
def fmtdatetime(value, format='%Y-%m-%d %H:%M:%S'):
    import datetime
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

##############################
#    Redirects and errors    #
##############################


#@app.before_request
#def netloc_redirect():
#    """
#        Redirect lmfdb.org -> www.lmfdb.org
#        Redirect {www, beta, }.lmfdb.com -> {www, beta, }.lmfdb.org
#        Force https on www.lmfdb.org
#        Redirect non-whitelisted routes from www.lmfdb.org to beta.lmfdb.org
#    """
#    from six.moves.urllib.parse import urlparse, urlunparse
#
#    urlparts = urlparse(request.url)
#
#    if (
#        urlparts.netloc == "beantheory.org"
#        and request.headers.get("X-Forwarded-Proto", "http") != "https"
#        and request.url.startswith("http://")
#    ):
#        url = request.url.replace("http://", "https://", 1)
#        return redirect(url, code=301)


def timestamp():
    return '[%s UTC]' % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

@app.errorhandler(404)
def not_found_404(error):
    app.logger.info('%s 404 error for URL %s %s' % (timestamp(), request.url, error.description))
    messages = error.description if isinstance(error.description, (list, tuple)) else (error.description,)
    return render_template("404.html", title='LMFDB Page Not Found', messages=messages), 404

@app.errorhandler(500)
def not_found_500(error):
    app.logger.error("%s 500 error on URL %s %s"%(timestamp(), request.url, error.args))
    return render_template("500.html", title='LMFDB Error'), 500

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

categories = [
    ("ag", "algebraic geometry"),
    ("at", "algebraic topology"),
    ("ap", "analysis of PDEs"),
    ("ct", "category theory"),
    ("ca", "classical analysis and ODEs"),
    ("co", "combinatorics"),
    ("ac", "commutative algebra"),
    ("cv", "complex variables"),
    ("dg", "differential geometry"),
    ("ds", "dynamical systems"),
    ("fa", "functional analysis"),
    ("gm", "general mathematics"),
    ("gn", "general topology"),
    ("gt", "geometric topology"),
    ("gr", "group theory"),
    ("ho", "history and overview"),
    ("it", "information theory"),
    ("kt", "K-theory and homology"),
    ("lo", "logic"),
    ("mp", "mathematical physics"),
    ("mg", "metric geometry"),
    ("nt", "number theory"),
    ("na", "numerical analysis"),
    ("oa", "operator algebras"),
    ("oc", "optimization and control"),
    ("pr", "probability"),
    ("qa", "quantum algebra"),
    ("rt", "representation theory"),
    ("ra", "rings and algebras"),
    ("sp", "spectral theory"),
    ("st", "statistics theory"),
    ("sg", "symplectic geometry")]

class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"
    def __init__(self):
        category = SelectBox(
            name="category",
            label="Category",
            options=[("", "")] + categories)
        keywords = TextBox(
            name="keywords",
            label="Keywords")
        speaker = TextBox(
            name="speaker",
            label="Speaker")
        affiliation = TextBox(
            name="affiliation",
            label="Affiliation")
        institution = TextBox(
            name="institution",
            label="Institution")
        title = TextBox(
            name="title",
            label="Title")
        online = SelectBox(
            name="online",
            label="Online",
            options=[("", "only"),
                     ("all", "and offline"),
                     ("exclude", "exclude")])
        when = SelectBox(
            name="when",
            label="Occuring in",
            options=[("", ""),
                     ("future", "the future"),
                     ("past", "the past")])
        date = TextBox( # should have date widget?
            name="date",
            label="Date")
        video = YesNoBox(
            name="video",
            label="Has video")
        avail = SelectBox(
            name="access",
            label="Access",
            options=[("", ""),
                     ("open", "open only")])
        count = TextBox(
            name="count",
            label="Results to display",
            example=50)
        self.browse_array = [[category, keywords], [speaker, affiliation], [title, institution], [when, date], [online], [video, avail], [count]]

@app.route("/")
def index():
    info = to_dict(request.args, search_array=SemSearchArray())
    if len(request.args) > 0:
        return search(info)
    today = datetime.datetime.today().weekday() # account for time zone....
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    if today not in [5, 6]: # weekday
        days = days[today:] + days[:today]
        days[0] = "Today"
        if today !=  4:
            days[1] = "Tomorrow"

    return render_template(
        'browse.html',
        title="Math Seminars",
        info=info,
        categories=categories,
        days=days,
        bread=None)

@app.route("/<category>")
def by_category(category):
    # raise error if not existing category?
    return search({"category":category})

def search(info):
    # TODO
    pass

@app.route("/about")
def about():
    return render_template("about.html", title="About Math Seminars")

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

@app.route("/info")
def info():
    from socket import gethostname
    output = ""
    output += "HOSTNAME = %s\n\n" % gethostname()
    output += "# PostgreSQL info\n"
    from . import db
    if not db.is_alive():
        output += "db is offline\n"
    else:
        conn_str = "%s" % db.conn
        output += "Connection: %s\n" % conn_str.replace("<","").replace(">","")
        output += "User: %s\n" % db._user
        output += "Read only: %s\n" % db._read_only
        output += "Read and write to userdb: %s\n" % db._read_and_write_userdb
        output += "Read and write to knowls: %s\n" % db._read_and_write_knowls
    output += "\n# GIT info\n"
    output += git_infos()[-1]
    output += "\n\n"
    return output.replace("\n", "<br>")


@app.route("/acknowledgment")
def acknowledgment():
    bread = [("Acknowledgments" , '')]
    return render_template("acknowledgment.html", title="Acknowledgments", bread=bread)

# google's CSE for www.lmfdb.org/* (and *only* those pages!)
@app.route("/search")
def search():
    return render_template("search.html", title="Search LMFDB", bread=[('Search', url_for("search"))])

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

def root_static_file(name):
    def static_fn():
        fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", name)
        if os.path.exists(fn):
            return open(fn, "rb").read()
        critical("root_static_file: file %s not found!" % fn)
        return abort(404, 'static file %s not found.' % fn)
    app.add_url_rule('/%s' % name, 'static_%s' % name, static_fn)


for fn in ['favicon.ico']:
    root_static_file(fn)


@app.route("/robots.txt")
def robots_txt():
    #if "beantheory.org".lower() in request.url_root.lower():
    #    fn = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "robots.txt")
    #    if os.path.exists(fn):
    #        return open(fn).read()
    return "User-agent: *\nDisallow: / \n"

# geeky pages have humans.txt
@app.route("/humans.txt")
def humans_txt():
    return render_template("acknowledgment.html", title="Acknowledgments")

@app.context_processor
def add_colors():
    from .color import Slate
    D = Slate().dict()
    print(D['header_background'])
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
#         Intro pages        #
##############################

# common base class and bread
_bc = 'intro'
intro_bread = lambda: [('Intro', url_for("introduction"))]

# template displaying just one single knowl as an KNOWL_INC
_single_knowl = 'single.html'


#@app.route("/intro/features")
#def introduction_features():
#    b = intro_bread()
#    b.append(('Features', url_for("introduction_features")))
#    return render_template(_single_knowl, title="Features", kid='intro.features', body_class=_bc, bread=b)

#@app.route("/news")
#def news():
#    t = "News"
#    b = [(t, url_for('news'))]
#    return render_template(_single_knowl, title="LMFDB in the News", kid='doc.news.in_the_news', body_class=_bc, bread=b)


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
