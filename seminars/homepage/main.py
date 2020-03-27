
from seminars.app import app
from seminars import db
from sage.misc.cachefunc import cached_function

from flask import render_template, request, url_for
from flask_login import current_user
import datetime
import pytz
from tzlocal import get_localzone

from lmfdb.utils import (
    SearchArray, TextBox, SelectBox, YesNoBox,
    to_dict, search_wrap,
)

def get_now():
    # Returns now in the server's time zone, comparable to time-zone aware datetimes from the database
    return datetime.datetime.now(tz=get_localzone())

def basic_top_menu():
    return [
        (url_for("index"), "", "Browse"),
        (url_for("search"), "", "Search"),
        (url_for("subscribe"), "", "Subscribe"),
        (url_for("about"), "", "About"),
        (url_for("users.info"), "", "Account" if current_user.is_authenticated else "Login")
    ]

@cached_function
def categories():
    return sorted(((rec["abbreviation"], rec["name"]) for rec in db.categories.search()), key=lambda x: x[1].lower())

class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"
    def __init__(self):
        category = SelectBox(
            name="category",
            label="Category",
            options=[("", "")] + categories())
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
    # Eventually want some kind of cutoff on which talks are included.
    talks = list(db.talks.search({'display':True}, projection=["id", "categories", "datetime", "seminar_id", "seminar_name", "speaker", "title"])) # include id
    menu = basic_top_menu()
    menu[0] = ("#", "$('#filter-menu').slideToggle(400); return false;", "Filter")
    return render_template(
        'browse.html',
        title="Math Seminars",
        info={},
        categories=categories(),
        talks=talks,
        top_menu=menu,
        bread=None)

@app.route("/search")
def search():
    info = to_dict(request.args, search_array=SemSearchArray())
    if len(request.args) > 0:
        st = info.get("search_type", info.get("hst", "talks"))
        if st == "talks":
            return search_talks(info)
        elif st == "seminars":
            return search_seminars(info)
    return render_template(
        "search.html",
        title="Search seminars",
        info=info,
        categories=categories(),
        menu=basic_top_menu(),
        bread=None)

@app.route("/seminar/<semid>")
def show_seminar(semid):
    try:
        semid = int(semid)
        info = db.seminars.lucky({'id': semid})
        if info is None: raise ValueError
    except ValueError:
        return render_template("404.html", title="Seminar not found")
    organizers = list(db.seminar_organizers.search({'seminar_id': semid}))
    talks = list(db.talks.search({'display':True, 'seminar_id': semid}, projection=3))
    now = get_now()
    info['future'] = []
    info['past'] = []
    for talk in talks:
        if talk['datetime'] + talk.get('duration', datetime.timedelta(hours=1)) >= now:
            info['future'].append(talk)
        else:
            info['past'].append(talk)
    info['future'].sort(key=lambda talk: talk['datetime'])
    info['past'].sort(key=lambda talk: talk['datetime'], reverse=True)
    return render_template(
        "seminar.html",
        title="View seminar",
        info=info,
        top_menu=basic_top_menu(),
        bread=None)

@app.route("/talk/<talkid>")
def show_talk(talkid):
    try:
        talkid = int(talkid)
        info = db.talks.lucky({'id': talkid})
        if info is None: raise ValueError
    except ValueError:
        return render_template("404.html", title="Talk not found")
    if info.get("abstract"):
        info["abstract"] = info["abstract"].split("\n\n")
    print(info.keys())
    utcoffset = int(info["datetime"].utcoffset().total_seconds() / 60)
    return render_template(
        "talk.html",
        title="View talk",
        info=info,
        utcoffset=utcoffset,
        top_menu=basic_top_menu(),
        bread=None)

@app.route("/subscribe")
def subscribe():
    # redirect to login page if not logged in, with message about what subscription is
    # If logged in, give a link to download the .ics file, the list of seminars/talks currently followed, and instructions on adding more
    raise NotImplementedError

@app.route("/<category>")
def by_category(category):
    # raise error if not existing category?
    return search({"category":category})

@search_wrap(template="seminar_search_results.html",
             table=db.seminars,
             title="Seminar Search Results",
             err_title="Seminar Search Input Error",
             bread=lambda:[("Search results", " ")])
def search_seminars(info, query):
    # For now, just ignore the info and return all results
    pass

