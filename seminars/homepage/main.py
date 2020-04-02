from seminars.app import app
from seminars import db
from seminars.talk import WebTalk, talks_search, talks_lucky
from seminars.seminar import seminars_lucky
from seminars.utils import basic_top_menu, categories
from seminars.institution import institutions, WebInstitution
from flask import render_template, request, url_for
from flask_login import current_user
import datetime
import pytz

from lmfdb.utils import (
    SearchArray,
    TextBox,
    SelectBox,
    YesNoBox,
    to_dict,
    search_wrap,
)


def get_now():
    # Returns now in UTC, comparable to time-zone aware datetimes from the database
    return datetime.datetime.now(pytz.UTC)


class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"

    def __init__(self):
        category = SelectBox(
            name="category", label="Category", options=[("", "")] + categories()
        )
        speaker = TextBox(name="speaker",
                          label="Speaker",
                          colspan=(1,2,1),
                          width=160*2 - 1*20)
        affiliation = TextBox(name="affiliation",
                              label="Affiliation",
                              colspan=(1,2,1),
                              width=160*2 - 1*20)
        institutions_shortnames = [(elt, elt) for elt in sorted(db.institutions.search({}, projection="shortname"))]
        institutions_options = [("", ""), ("No institution", "None")] + institutions_shortnames
        institution = SelectBox(
            name="institution",
            label="Institution",
            options=institutions_options
        )
        title = TextBox(name="title",
                        label="Title",
                        colspan=(1,2,1),
                        width=160*2 - 1*20)
        keywords = TextBox(name="keywords",
                           label="Keywords",
                           colspan=(1,2,1),
                           width=160*2 - 1*20)
        online = SelectBox(
            name="online",
            label="Online",
            options=[("", "only"), ("all", "and offline"), ("exclude", "exclude")],
        )
        date = TextBox(  # should have date widget?
            name="daterange",
            id="daterange",
            label="Date",
            colspan=(1, 2, 1),
            width=160*2 - 1*20,
        )
        video = YesNoBox(name="video", label="Has video")
        access = SelectBox(
            name="access", label="Access", options=[("", ""), ("open", "open only")]
        )
        count = TextBox(name="count", label="Results to display", example=50)
        self.browse_array = [
            [category, keywords],
            [institution, title],
            [online, speaker],
            [video, affiliation],
            [access, date],
            [count],
        ]


@app.route("/")
def index():
    # Eventually want some kind of cutoff on which talks are included.
    # Deal with time zone right
    talks = talks_search(
        {"display": True, "end_time": {"$gte": datetime.datetime.now()}},
        sort=["start_time"],
    )
    menu = basic_top_menu()
    menu[0] = ("#", "$('#filter-menu').slideToggle(400); return false;", "Filter")
    return render_template(
        "browse.html",
        title="Math Seminars",
        info={},
        categories=categories(),
        talks=talks,
        top_menu=menu,
        bread=None,
    )


@app.route("/search")
def search():
    info = to_dict(request.args, search_array=SemSearchArray())
    if len(request.args) > 0:
        st = info.get("search_type", info.get("hst", "talks"))
        if st == "talks":
            return search_talks(info)
        elif st == "seminars":
            return search_seminars(info)
    menu = basic_top_menu()
    menu.pop(1)
    return render_template(
        "search.html",
        title="Search",
        info=info,
        categories=categories(),
        top_menu=menu,
        bread=None,
    )


@app.route("/institutions/")
def list_institutions():
    return render_template(
        "institutions.html",
        title="Institutions",
        institutions=institutions(),
        top_menu=basic_top_menu(),
    )


@app.route("/seminar/<shortname>")
def show_seminar(shortname):
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None:
        return render_template("404.html", title="Seminar not found")
    organizers = list(db.seminar_organizers.search({"seminar_id": shortname}))
    talks = talks_search({"display": True, "seminar_id": shortname}, projection=3)
    now = get_now()
    future = []
    past = []
    for talk in talks:
        if talk.end_time >= now:
            future.append(talk)
        else:
            past.append(talk)
    future.sort(key=lambda talk: talk.start_time)
    past.sort(key=lambda talk: talk.start_time, reverse=True)
    return render_template(
        "seminar.html",
        title="View seminar",
        future=future,
        past=past,
        seminar=seminar,
        top_menu=basic_top_menu(),
        bread=None,
    )


@app.route("/talk/<semid>/<int:talkid>/")
def show_talk(semid, talkid):
    talk = talks_lucky({"seminar_id": semid, "seminar_ctr": talkid})
    if talk is None:
        return render_template("404.html", title="Talk not found")
    utcoffset = int(talk.start_time.utcoffset().total_seconds() / 60)
    return render_template(
        "talk.html",
        title="View talk",
        talk=talk,
        utcoffset=utcoffset,
        top_menu=basic_top_menu(),
    )


@app.route("/institution/<shortname>/")
def show_institution(shortname):
    institution = db.institutions.lookup(shortname)
    if institution is None:
        return render_template("404.html", title="Institution not found")
    institution = WebInstitution(shortname, data=institution)
    return render_template(
        "institution.html",
        title="View institution",
        institution=institution,
        top_menu=basic_top_menu(),
    )


@app.route("/subscribe")
def subscribe():
    # redirect to login page if not logged in, with message about what subscription is
    # If logged in, give a link to download the .ics file, the list of seminars/talks currently followed, and instructions on adding more
    menu = basic_top_menu()
    menu.pop(2)
    return render_template(
        "subscribe.html", title="Subscribe", top_menu=menu, bread=None
    )
    raise NotImplementedError


@app.route("/about")
def about():
    menu = basic_top_menu()
    menu.pop(4)
    return render_template("about.html", title="About", top_menu=menu)


@app.route("/<category>")
def by_category(category):
    # raise error if not existing category?
    return search({"category": category})


@search_wrap(
    template="seminar_search_results.html",
    table=db.seminars,
    title="Seminar Search Results",
    err_title="Seminar Search Input Error",
    bread=lambda: [("Search results", " ")],
)
def search_seminars(info, query):
    # For now, just ignore the info and return all results
    pass
