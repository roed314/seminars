from seminars.app import app
from seminars import db
from seminars.talk import WebTalk, talks_search, talks_lucky
from seminars.seminar import seminars_lucky
from seminars.utils import basic_top_menu, categories
from seminars.institution import institutions, WebInstitution
from flask import render_template, request, url_for
from seminars.seminar import seminars_search
from seminars.talk import talks_search
from flask_login import current_user
import datetime
import pytz
from collections import Counter
from lmfdb.utils.search_parsing import search_parser
from dateutil.parser import parse

from lmfdb.utils import (
    SearchArray,
    TextBox,
    SelectBox,
    YesNoBox,
    to_dict,
    search_wrap,
    flash_error,
)


def get_now():
    # Returns now in UTC, comparable to time-zone aware datetimes from the database
    return datetime.datetime.now(pytz.UTC)


def parse_category(info, query):
    # of the talk
    if info.get("category"):
        query["categories"] = {"$contains": info.get("category")}


def parse_institution_sem(info, query):
    if info.get("institution") == "None":
        query["institutions"] = None
    elif info.get("institution"):
        # one day we will do joins
        query["institutions"] = {"$contains": info.get("institution")}


def parse_institution_talk(info, query):
    if info.get("institution"):
        sub_query = {}
        # one day we will do joins
        parse_institution_sem(info, sub_query)
        sem_shortnames = list(db.seminars.search(sub_query, "shortname"))
        query["seminar_id"] = {"$in": sem_shortnames}


def parse_online(info, query):
    online = info.get("online")
    if online  and  online != "all":
        query["online"] = {"": True, "exclude": "False"}[online]


def parse_substring(info, query, field, qfield, start="%", end="%"):
    if info.get("field"):
        kwds = [elt.strip() for elt in info.get("field").split(",") if elt.strip()]
        query[qfield] = {"$or": [{"$LIKE": start + elt + end} for elt in kwds]}


def parse_access(info, query):
    # we want exact matches
    parse_substring(info, query, "access", "access", start="", end="")


def parse_date(info, query):
    tz = current_user.tz
    date = info.get("daterange")
    if date:
        sub_query = {}
        if "-" not in date:
            # make it into a range
            date = date + "-" + date
        start, end = date.split("-")
        if start.strip():
            try:
                start = tz.localize(parse(start))
            except Exception:
                flash_error("Could not parse date: %s", start)
            sub_query["$gte"] = start
        if end.strip():
            try:
                end = tz.localize(parse(end))
            except Exception:
                flash_error("Could not parse date: %s", end)
            end = end + timedelta(hours=23, minutes=59, seconds=59)
            sub_query["$lte"] = end
        if sub_query:
            query["start_time"] = sub_query


def parse_video(info, query):
    v = info.get("video")
    if v == "yes":
        query["video"] = {"$not": None}
    elif v == "no":
        query["video"] = None


def talks_parser(info, query):
    parse_category(info, query)
    parse_institution_talk(info, query)
    parse_online(info, query)
    parse_substring(info, query, "keywords", "keywords")
    parse_access(info, query)

    parse_substring(info, query, "speaker", "speaker")
    parse_substring(info, query, "affiliation", "speaker_affiliation")
    parse_substring(info, query, "title", "title")
    parse_date(info, query)
    parse_video(info, query)


def seminars_parser(info, query):
    parse_category(info, query)
    parse_institution_sem(info, query)
    parse_online(info, query)
    parse_substring(info, query, "keywords", "keywords")
    parse_access(info, query)

    parse_substring(info, query, "name", "name")


# Common boxes
## categories
category = SelectBox(
    name="category", label="Category", options=[("", "")] + categories()
)
## pick institution where it is held


def institutions_shortnames():
    return sorted(db.institutions.search({}, projection="shortname"))


textwidth = 400
institution = SelectBox(
    name="institution",
    label="Institution",
    options=[("", ""), ("None", "No institution", ),]
    + [(elt, elt) for elt in institutions_shortnames()],
)
## online only?
online = SelectBox(
    name="online",
    label="Online",
    options=[("", "only"), ("all", "and offline"), ("exclude", "exclude")],
)
## keywords for seminar or talk
keywords = TextBox(
    name="keywords", label="Keywords", colspan=(1, 2, 1), width=textwidth
)
## type of access
access = SelectBox(
    name="access", label="Access", options=[("", ""), ("open", "open only")]
)
## number of results to display
count = TextBox(name="count", label="Results to display", example=50)


class TalkSearchArray(SearchArray):
    noun = "talk"
    plural_noun = "talks"

    def __init__(self):
        speaker = TextBox(
            name="speaker", label="Speaker", colspan=(1, 2, 1), width=textwidth
        )
        affiliation = TextBox(
            name="affiliation",
            label="Affiliation",
            colspan=(1, 2, 1),
            width=160 * 2 - 1 * 20,
        )
        title = TextBox(
            name="title", label="Title", colspan=(1, 2, 1), width=textwidth
        )
        date = TextBox(  # should have date widget?
            name="daterange",
            id="daterange",
            label="Date",
            colspan=(1, 2, 1),
            width=160 * 2 - 1 * 20,
        )
        video = YesNoBox(name="video", label="Has video")
        self.browse_array = [
            [category, keywords],
            [institution, title],
            [online, speaker],
            [access, affiliation],
            [video, date],
            [count],
        ]
    def search_types(self, info):
        st = self._st(info)
        if st is None or st == 'seminars':
            return [('talks', 'List of talks')]
        else:
            return [('talks', 'Search again')]


class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"

    def __init__(self):
        name = TextBox(
            name="name", label="Name", colspan=(1, 2, 1), width=textwidth
        )

        self.browse_array = [
            [category, keywords],
            [institution, name],
            [online, access],
            [count],
        ]
    def search_types(self, info):
        st = self._st(info)
        if st is None or st == 'talks':
            return [('seminars', 'List of seminars')]
        else:
            return [('seminars', 'Search again')]


@app.route("/")
def index():
    # Eventually want some kind of cutoff on which talks are included.
    talks = list(talks_search(
        {"display": True, "end_time": {"$gte": datetime.datetime.now()}},
        sort=["start_time"],
    ))
    category_counts = Counter()
    for talk in talks:
        category_counts["ALL"] += 1
        if talk.categories:
            for cat in talk.categories:
                category_counts[cat] += 1
    menu = basic_top_menu()
    menu[0] = ("#", "$('#filter-menu').slideToggle(400); return false;", "Filter")
    return render_template(
        "browse.html",
        title="Math Seminars",
        category_counts=category_counts,
        talks=talks,
        top_menu=menu,
        bread=None,
    )


@app.route("/search")
def search():
    info = to_dict(request.args,
                   seminar_search_array=SemSearchArray(),
                   talks_search_array=TalkSearchArray())
    if len(request.args) > 0:
        st = info["search_type"] = info.get("search_type", info.get("hst", "talks"))
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

@app.route("/faq")
def faq():
    return render_template("faq.html", title="FAQ", top_menu=basic_top_menu())

@app.route("/<category>")
def by_category(category):
    # raise error if not existing category?
    return search({"category": category})


def search_seminars(info):
    query = {}
    seminars_parser(info, query)
    info['seminar_results'] = seminars_search(query)
    menu = basic_top_menu()
    menu.pop(1)
    return render_template(
        "search.html",
        title="Search seminars",
        info=info,
        top_menu=menu,
        bread=None,
    )


def search_talks(info):
    query = {}
    talks_parser(info, query)
    info['talk_results'] = talks_search(query)
    menu = basic_top_menu()
    menu.pop(1)
    return render_template(
        "search.html",
        title="Search talks",
        info=info,
        top_menu=menu,
        bread=None,
    )

