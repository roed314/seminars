from seminars.app import app
from seminars import db
from seminars.talk import talks_search, talks_lucky
from seminars.utils import topics, toggle, Toggle, languages_dict
from seminars.institution import institutions, WebInstitution
from flask import render_template, request, url_for
from seminars.seminar import seminars_search, all_seminars, all_organizers, seminars_lucky
from flask_login import current_user
import datetime
import pytz
from collections import Counter
from dateutil.parser import parse

from lmfdb.utils import (
    BasicSpacer,
    SearchArray,
    TextBox,
    SelectBox,
    to_dict,
    flash_error,
)
from lmfdb.utils.search_parsing import collapse_ors


def get_now():
    # Returns now in UTC, comparable to time-zone aware datetimes from the database
    return datetime.datetime.now(pytz.UTC)


def parse_topic(info, query, prefix):
    # of the talk
    topic = info.get(prefix + "_topic")
    if topic:
        query["topics"] = {"$contains": topic}


def parse_institution_sem(info, query, prefix="seminar"):
    inst = info.get(prefix + "_institution")
    if inst == "None":
        query["institutions"] = []
    elif inst:
        # one day we will do joins
        query["institutions"] = {"$contains": inst}


def parse_institution_talk(info, query, prefix="talk"):
    if info.get(prefix + "_institution"):
        sub_query = {}
        # one day we will do joins
        parse_institution_sem(info, sub_query, prefix="talk")
        sem_shortnames = list(seminars_search(sub_query, "shortname"))
        query["seminar_id"] = {"$in": sem_shortnames}


def parse_online(info, query, prefix):
    if info.get(prefix + "_online") == "yes":
        query["online"] = True


def parse_offline(info, query, prefix):
    if info.get(prefix + "_offline") == "yes":
        query["room"] = {"$exists": True}


def parse_substring(info, query, field, qfields, start="%", end="%"):
    if info.get(field):
        kwds = [elt.strip() for elt in info.get(field).split(",") if elt.strip()]
        collapse_ors(["$or", [{qfield: {"$ilike": start + elt + end}} for elt in kwds for qfield in qfields]], query)


def parse_access(info, query, prefix):
    # we want exact matches
    access = info.get(prefix + "_access")
    if access == "open":
        query["access"] = "open"
    elif access == "users":
        query["access"] = {"$or": ["open", "users"]}


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
            end = end + datetime.timedelta(hours=23, minutes=59, seconds=59)
            sub_query["$lte"] = end
        if sub_query:
            query["start_time"] = sub_query


def parse_video(info, query):
    v = info.get("video")
    if v == "yes":
        query["video_link"] = {"$not": None}

def parse_language(info, query, prefix):
    v = info.get(prefix + "_language")
    if v:
        query["language"] = v

def talks_parser(info, query):
    parse_topic(info, query, prefix="talk")
    parse_institution_talk(info, query)
    parse_online(info, query, prefix="talk")
    parse_offline(info, query, prefix="talk")
    parse_substring(info, query, "talk_keywords", ["title", "abstract"])
    parse_access(info, query, prefix="talk")

    parse_substring(info, query, "speaker", ["speaker"])
    parse_substring(info, query, "affiliation", ["speaker_affiliation"])
    parse_substring(info, query, "title", ["title"])
    parse_date(info, query)
    parse_video(info, query)
    parse_language(info, query, prefix="talk")
    query["display"] = True


def seminars_parser(info, query):
    parse_topic(info, query, prefix="seminar")
    parse_institution_sem(info, query)
    parse_online(info, query, prefix="seminar")
    parse_offline(info, query, prefix="seminar")
    parse_substring(info, query, "seminar_keywords", ["description", "comments", "name"])
    parse_access(info, query, prefix="seminar")
    parse_language(info, query, prefix="seminar")

    parse_substring(info, query, "name", ["name"])
    query["display"] = True


# Common boxes


def institutions_shortnames():
    return sorted(
        db.institutions.search({}, projection=["shortname", "name"]), key=lambda elt: elt["name"]
    )


textwidth = 400


class TalkSearchArray(SearchArray):
    noun = "talk"
    plural_noun = "talks"

    def __init__(self):
        ## topics
        topic = SelectBox(name="talk_topic", label="Topics", options=[("", "")] + topics())

        ## pick institution where it is held
        institution = SelectBox(
            name="talk_institution",
            label="Institution",
            options=[("", ""), ("None", "No institution",),]
            + [(elt["shortname"], elt["name"]) for elt in institutions_shortnames()],
        )

        ## online only?
        online = Toggle(name="talk_online", label="Online")
        offline = Toggle(name="talk_offline", label="Offline")

        ## keywords for seminar or talk
        keywords = TextBox(
            name="talk_keywords",
            label="Keywords",
            knowl="keywords",
            colspan=(1, 2, 1),
            width=textwidth,
        )
        ## type of access
        access = SelectBox(
            name="talk_access",
            label="Access",
            options=[
                ("", ""),
                ("open", "Any visitor can view link"),
                ("users", "Any logged-in user can view link"),
            ],
        )
        ## number of results to display
        # count = TextBox(name="talk_count", label="Results to display", example=50, example_value=True)

        speaker = TextBox(
            name="speaker",
            label="Speaker",
            colspan=(1, 2, 1),
            width=textwidth,
            example="Pythagoras o Samios",
        )
        affiliation = TextBox(
            name="affiliation",
            label="Affiliation",
            colspan=(1, 2, 1),
            width=160 * 2 - 1 * 20,
            example="Monsters University",
        )
        title = TextBox(
            name="title",
            label="Title",
            colspan=(1, 2, 1),
            width=textwidth,
            example="A rigorous definition of rigorous",
        )
        date = TextBox(
            name="daterange",
            id="daterange",
            label="Date",
            example=datetime.datetime.now(current_user.tz).strftime("%B %d, %Y -"),
            example_value=True,
            colspan=(1, 2, 1),
            width=160 * 2 - 1 * 20,
        )
        lang_dict = languages_dict()
        language = SelectBox(
            name="talk_language",
            label="Language",
            options=[("", ""), ("en", "English")] + [(code, lang_dict[code]) for code in sorted(db.talks.distinct('language')) if code != "en"]
        )
        video = Toggle(name="video", label="Has video")
        self.array = [
            [topic, keywords],
            [institution, title],
            [online, speaker],
            [offline, affiliation],
            [access, language],
            [video, date],
            # [count],
        ]

    def main_table(self, info=None):
        return self._print_table(self.array, info, layout_type="horizontal")

    def search_types(self, info):
        return [
            ("talks", "Search for talks"),
            BasicSpacer("Times in %s" % (current_user.show_timezone("browse"))),
        ]

    def hidden(self, info):
        return []  # [("talk_start", "talk_start")]


class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"

    def __init__(self):
        ## topics
        topic = SelectBox(name="seminar_topic", label="Topics", options=[("", "")] + topics())

        ## pick institution where it is held
        institution = SelectBox(
            name="seminar_institution",
            label="Institution",
            options=[("", ""), ("None", "No institution",),]
            + [(elt["shortname"], elt["name"]) for elt in institutions_shortnames()],
        )

        ## online only?
        online = Toggle(name="seminar_online", label="Online")
        # offline = Toggle(name="seminar_offline", label="Offline")

        ## keywords for seminar or talk
        keywords = TextBox(
            name="seminar_keywords", label="Keywords", width=textwidth,
        )
        ## type of access
        access = SelectBox(
            name="seminar_access",
            label="Access",
            options=[
                ("", ""),
                ("open", "Any visitor can view link"),
                ("users", "Any logged-in user can view link"),
            ],
        )
        lang_dict = languages_dict()
        language = SelectBox(
            name="seminar_language",
            label="Language",
            options=[("", ""), ("en", "English")] + [(code, lang_dict[code]) for code in sorted(db.talks.distinct('language')) if code != "en"]
        )
        ## number of results to display
        # count = TextBox(name="seminar_count", label="Results to display", example=50, example_value=True)

        name = TextBox(
            name="name",
            label="Name",
            width=textwidth,
            example="What Do They Know? Do They Know Things?? Let's Find Out!",
        )

        self.array = [
            [topic, keywords],
            [institution, name],
            [language, access],
            [online],
            # [count],
        ]

    def main_table(self, info=None):
        return self._print_table(self.array, info, layout_type="horizontal")

    def search_types(self, info):
        return [
            ("seminars", "Search for seminars"),
            BasicSpacer("Times in %s" % (current_user.show_timezone("browse"))),
        ]

    def hidden(self, info):
        return []  # [("seminar_start", "seminar_start")]


@app.route("/")
def index():
    # Eventually want some kind of cutoff on which talks are included.
    talks = list(
        talks_search(
            {"display": True, "end_time": {"$gte": datetime.datetime.now()}},
            sort=["start_time"],
            seminar_dict=all_seminars(),
        )
    )
    topic_counts = Counter()
    language_counts = Counter()
    for talk in talks:
        if talk.topics:
            for topic in talk.topics:
                topic_counts[topic] += 1
        language_counts[talk.language] += 1
    lang_dict = languages_dict()
    languages = [(code, lang_dict[code]) for code in language_counts]
    languages.sort(key=lambda x: (-language_counts[x[0]], x[1]))
    # menu[0] = ("#", "$('#filter-menu').slideToggle(400); return false;", "Filter")
    return render_template(
        "browse.html",
        title="Math Seminars (beta)",
        topic_counts=topic_counts,
        languages=languages,
        language_counts=language_counts,
        talks=talks,
        section="Browse",
        toggle=toggle,
    )


@app.route("/search")
def search():
    info = to_dict(
        request.args, seminar_search_array=SemSearchArray(), talks_search_array=TalkSearchArray()
    )
    if "search_type" not in info:
        info["talk_online"] = info["seminar_online"] = True
        info["daterange"] = info.get(
            "daterange", datetime.datetime.now(current_user.tz).strftime("%B %d, %Y -")
        )
    try:
        seminar_count = int(info["seminar_count"])
        talk_count = int(info["talk_count"])
        seminar_start = int(info["seminar_start"])
        if seminar_start < 0:
            seminar_start += (1 - (seminar_start + 1) // seminar_count) * seminar_count
        talk_start = int(info["talk_start"])
        if talk_start < 0:
            talk_start += (1 - (talk_start + 1) // talk_count) * talk_count
    except (KeyError, ValueError):
        seminar_count = info["seminar_count"] = 50
        talk_count = info["talk_count"] = 50
        seminar_start = info["seminar_start"] = 0
        talk_start = info["talk_start"] = 0
    seminar_query = {}
    seminars_parser(info, seminar_query)
    info["seminar_results"] = seminars_search(
        seminar_query, sort=["weekday", "start_time", "name"], organizer_dict=all_organizers(),
    )  # limit=seminar_count, offset=seminar_start,
    talk_query = {}
    talks_parser(info, talk_query)
    info["talk_results"] = talks_search(
        talk_query, sort=["start_time", "speaker"], seminar_dict=all_seminars()
    )  # limit=talk_count, offset=talk_start
    return render_template(
        "search.html", title="Search seminars", info=info, section="Search", bread=None,
    )


@app.route("/institutions/")
def list_institutions():
    section = "Manage" if current_user.is_creator else None
    return render_template(
        "institutions.html",
        title="Institutions",
        section=section,
        subsection="institutions",
        institutions=institutions(),
    )


@app.route("/seminar/<shortname>")
def show_seminar(shortname):
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None:
        return render_template("404.html", title="Seminar not found")
    talks = seminar.talks(projection=3)
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
    if current_user.email in seminar.editors() or current_user.is_admin:
        section = "Manage"
    else:
        section = None
    return render_template(
        "seminar.html",
        title="View seminar",
        future=future,
        past=past,
        seminar=seminar,
        section=section,
        subsection="view",
        bread=None,
    )

@app.route("/seminar_raw/<shortname>")
def show_seminar_raw(shortname):
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None:
        return render_template("404.html", title="Seminar not found")
    talks = seminar.talks(projection=3)
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
        "seminar_raw.html",
        title=seminar.name,
        future=future,
        past=past,
        seminar=seminar
    )


@app.route("/talk/<semid>/<int:talkid>/")
def show_talk(semid, talkid):
    token = request.args.get("token", "")  # save the token so user can toggle between view and edit
    talk = talks_lucky({"seminar_id": semid, "seminar_ctr": talkid})
    if talk is None:
        return render_template("404.html", title="Talk not found")
    kwds = dict(
        title="View talk", talk=talk, seminar=talk.seminar, subsection="viewtalk", token=token
    )
    if token:
        kwds["section"] = "Manage"
        # Also want to override top menu
        from seminars.utils import top_menu

        menu = top_menu()
        menu[2] = (url_for("create.index"), "", "Manage")
        kwds["top_menu"] = menu
    elif (
        current_user.is_admin
        or current_user.email_confirmed
        and (
            current_user.email in talk.seminar.editors() or current_user.email == talk.speaker_email
        )
    ):
        kwds["section"] = "Manage"
    return render_template("talk.html", **kwds)


@app.route("/institution/<shortname>/")
def show_institution(shortname):
    institution = db.institutions.lookup(shortname)
    if institution is None:
        return render_template("404.html", title="Institution not found")
    institution = WebInstitution(shortname, data=institution)
    section = "Manage" if current_user.is_creator else None
    query = {"institutions": {"$contains": shortname}}
    if not current_user.is_admin:
        query["display"] = True
    events = list(seminars_search(
        query, sort=["weekday", "start_time", "name"], organizer_dict=all_organizers(),
    ))
    seminars = [S for S in events if not S.is_conference]
    conferences = [S for S in events if S.is_conference]
    conferences.sort(key=lambda S:(S.start_date, S.name))
    return render_template(
        "institution.html",
        seminars=seminars,
        conferences=conferences,
        title="View institution",
        institution=institution,
        section=section,
        subsection="viewinst",
    )



@app.route("/info")
def info():
    return render_template("info.html", title="Features", section="Info", subsection="features")


@app.route("/faq")
def faq():
    return render_template("faq.html", title="FAQ", section="Info", subsection="faq")


# @app.route("/<topic>")
# def by_topic(topic):
#    # raise error if not existing topic?
#    return search({"seminars_topic": topic, "talks_topic": topic})
