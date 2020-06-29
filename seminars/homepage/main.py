from seminars.app import app
from seminars import db
from seminars.talk import talks_search, talks_lucky, talks_lookup, WebTalk
from seminars.utils import (
    Toggle,
    ics_file,
    topdomain,
    maxlength,
    adapt_datetime,
    date_and_daytime_to_time,
    date_and_daytimes_to_times,
    process_user_input,
    url_for_with_args,
)
from seminars.topic import topic_dag
from seminars.language import languages
from seminars.institution import institutions, WebInstitution
from seminars.knowls import static_knowl
from flask import abort, render_template, request, redirect, url_for, Response, make_response
from seminars.seminar import seminars_search, all_seminars, all_organizers, seminars_lucky, next_talk_sorted, series_sorted, audience_options
from flask_login import current_user
import json
from datetime import datetime, timedelta
import pytz
from collections import Counter
from dateutil.parser import parse
from lmfdb.utils import (
    flash_error,
    to_dict,
)
from lmfdb.utils.search_boxes import (
    SearchArray,
    SearchBox,
    SelectBox,
    SearchButton,
    TextBox,
)

from lmfdb.utils.search_parsing import collapse_ors

DEFAULT_AUDIENCE = 5    # Show everything up to general audience by default

def get_now():
    # Returns now in UTC, comparable to time-zone aware datetimes from the database
    return datetime.now(pytz.UTC)


def parse_topic(info, query):
    # of the talk
    topic = info.get("topic")
    if topic:
        # FIXME: temporary bridge during addition of physics
        if "_" not in topic:
            topic = "math_" + topic
        query["topics"] = {"$or": [{"$contains": topic}, {"$contains": topic[5:]}]}
    # FIXME: temporary measure during addition of physics
    elif topdomain() == "mathseminars.org":
        query["topic"] = {"$contains": "math"}


def parse_institution_sem(info, query):
    inst = info.get("institution")
    if inst == "None":
        query["institutions"] = []
    elif inst:
        # one day we will do joins
        query["institutions"] = {"$contains": inst}


def parse_institution_talk(info, query):
    if info.get("institution"):
        sub_query = {}
        # one day we will do joins
        parse_institution_sem(info, sub_query)
        sem_shortnames = list(seminars_search(sub_query, "shortname"))
        query["seminar_id"] = {"$in": sem_shortnames}


def parse_venue(info, query):
    value = info.get("venue")
    if value == "online":
        query["online"] = True
    elif value == "in-person":
        query["room"] = {"$and": [{"$exists": True}, {"$ne": ""}]}


def parse_substring(info, query, field, qfields, start="%", end="%"):
    if info.get(field):
        kwds = [elt.strip() for elt in info.get(field).split(",") if elt.strip()]
        collapse_ors(
            [
                "$or",
                [{qfield: {"$ilike": start + elt + end}} for elt in kwds for qfield in qfields],
            ],
            query,
        )


def parse_daterange(info, query, time=True):
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
                sub_query["$gte"] = start if time else start.date()
            except Exception as e:
                flash_error("Could not parse start date %s.  Error: " + str(e), start)
        if end.strip():
            try:
                end = tz.localize(parse(end))
                end = end + timedelta(hours=23, minutes=59, seconds=59)
                sub_query["$lte"] = end if time else end.date()
            except Exception as e:
                flash_error("Could not parse end date %s.  Error: " + str(e), end)
        if sub_query:
            query["start_time" if time else "start_date"] = sub_query

def parse_recent_edit(info, query):
    recent = info.get("recent", "").strip()
    if recent:
        try:
            recent = float(recent)
        except Exception as e:
            flash_error("Could not parse recent edit input %s.  Error: " + str(e), recent)
        else:
            recent = datetime.now() - timedelta(hours=recent)
            query["edited_at"] = {"$gte": recent}

def parse_video(info, query):
    v = info.get("video")
    if v == "1":
        query["video_link"] = {"$ne": ''}

def parse_slides(info, query):
    v = info.get("slides")
    if v == "1":
        query["slides_link"] = {"$ne": ''}

def parse_paper(info, query):
    v = info.get("paper")
    if v == "1":
        query["paper_link"] = {"$ne": ''}

def parse_access(info, query):
    v = info.get("access")
    if v == "1":
        query["access_control"] = {"$ne": 5}
        query["live_link"] = {"$ne": ""}

def parse_audience(info, query):
    v = info.get("audience")
    if v:
        query["audience"] = int(v)

def parse_language(info, query):
    v = info.get("language")
    if v:
        query["language"] = v


def talks_parser(info, query):
    parse_topic(info, query)
    parse_institution_talk(info, query)
    #parse_venue(info, query)
    parse_access(info, query)

    parse_substring(info, query, "speaker", ["speaker"])
    parse_substring(info, query, "affiliation", ["speaker_affiliation"])
    parse_substring(info, query, "title", ["title"])
    parse_video(info, query)
    parse_slides(info, query)
    parse_paper(info, query)
    parse_language(info, query)
    parse_daterange(info, query, time=True)
    parse_recent_edit(info, query)
    parse_audience(info, query)
    parse_access(info, query)
    query["display"] = True
    # TODO: remove this temporary measure allowing hidden to be None
    query["hidden"] = {"$or": [False, {"$exists": False}]}
    # These are necessary but not succificient conditions to display the talk
    # Also need that the seminar has visibility 2.

def series_keyword_columns():
    return ["name", "homepage", "shortname", "comments"]

def organizers_keyword_columns():
    return ["name", "homepage", "email"] if current_user.is_subject_admin(None) else ["name", "homepage"]

def seminars_parser(info, query, org_query, conference=False):
    parse_topic(info, query)
    parse_institution_sem(info, query)
    #parse_venue(info, query)
    parse_substring(info, org_query, "organizer", organizers_keyword_columns())
    parse_access(info, query)
    parse_language(info, query)
    if conference:
        parse_daterange(info, query, time=False)
    parse_substring(info, query, "name", ["name"])
    parse_audience(info, query)
    query["display"] = True
    query["visibility"] = 2


def institutions_shortnames():
    return sorted(
        db.institutions.search({}, projection=["shortname", "name"]), key=lambda elt: elt["name"]
    )


textwidth = 300

class TripleToggle(Toggle):
    def __init__(self, lname, llabel, mname, mlabel, rname, rlabel):
        Toggle.__init__(self, lname, llabel)
        self.mtoggle = Toggle(mname, mlabel)
        self.rtoggle = Toggle(rname, rlabel)
    def _input(self, info):
        left_toggle = Toggle._input(self, info)
        middle_label = self.mtoggle._label(info)
        middle_toggle = self.mtoggle._input(info)
        right_label = self.rtoggle._label(info)
        right_toggle = self.rtoggle._input(info)
        return ('<table><tr><td style="padding-left: 0px;">' +
                left_toggle +
                '<td style="padding-left: 2em;">%s</td><td>%s</td>' % (middle_label, middle_toggle) +
                '<td style="padding-left: 2em;">%s</td><td>%s</td>' % (right_label, right_toggle) +
                '</td></tr></table>'
        )

class PushForCookies(SearchButton):
    def __init__(self, value, description, disabled=False, **kwds):
        self.disabled = disabled
        SearchButton.__init__(self, value, description, **kwds)
    def _input(self, info):
        onclick = " onclick='pushForCookies(); return false;'"
        disabled = ' disabled="disabled"' if self.disabled else ""
        btext = "<button type='submit' name='search_type' value='{val}' style='width: {width}px;'{onclick}{disabled}>{desc}</button>"
        return btext.format(
            width=self.width,
            val=self.value,
            desc=self.description,
            onclick=onclick,
            disabled=disabled,
        )

class ComboBox(TextBox):
    def __init__(self, name, label, spantext, spanextras="", **kwds):
        TextBox.__init__(self, name, label, **kwds)
        self.spantext = spantext
        self.spanextras = spanextras
    def _input(self, info):
        inp = TextBox._input(self, info)
        span = '<span{extras}>{text}</span>'.format(extras=self.spanextras, text=self.spantext)
        return inp + span

class SemSearchArray(SearchArray):
    def __init__(self):
        self.institution = SelectBox(
            name="institution",
            label="Institution",
            options=[("", ""), ("None", "No institution",),]
            + [(elt["shortname"], elt["name"]) for elt in institutions_shortnames()],
            width=textwidth+10, # select boxes need 10px more than text areas
        )
        self.venue = SelectBox(
            name="venue",
            label=static_knowl("venue"),
            options=[("", ""),
                     ("online", "online"),
                     ("in-person", "in-person")
            ]
        )

        self.recent = ComboBox(
            name="recent",
            label="Edited within",
            spantext="hours",
            spanextras=' style="margin-left:5px;"',
            example="168",
            example_span=False,
            width=50,
        )
        self.audience = SelectBox(
            name="audience",
            label="Audience",
            width=textwidth+10, # select boxes need 10px more than text areas
            options=[("", "")] + [(str(code), desc) for (code, desc) in audience_options if code <= DEFAULT_AUDIENCE],
        )

    def main_table(self, info=None):
        return self._print_table(self.array, info, layout_type="horizontal")

    def hidden(self, info):
        return []  # [("talk_start", "talk_start")]

    def buttons(self, info=None):
        active_search = info and any(info.get(elt.name) for row in self.array for elt in row)
        if active_search:
            button = PushForCookies("reload", "Applied", disabled=True)
        else:
            button = PushForCookies("reload", "Apply")
        return self._print_table([[button]], info, layout_type="vertical")

class TalkSearchArray(SemSearchArray):
    def __init__(self, past=False):
        SemSearchArray.__init__(self)
        speaker = TextBox(
            name="speaker",
            label="Speaker",
            width=textwidth,
            extra=['style="width:300px; margin-right:64px;"'],
        )
        affiliation = TextBox(
            name="affiliation",
            label="Affiliation",
            width=textwidth,
        )
        date = TextBox(
            name="daterange",
            id="daterange",
            label="Date",
            example=datetime.now(current_user.tz).strftime("%B %d, %Y -"),
            example_value=True,
            example_span=False,
            width=textwidth,
            extra=['autocomplete="off"'],
        )
        time = TextBox(
            name="timerange",
            label="Time",
            example="8:00 - 18:00",
            example_span=False,
            width=textwidth,
        )
        livestream_available = Toggle("access", "Livestream available")

        videoslidespaper = TripleToggle("video", "Has video", "slides", "slides", "paper", "paper")
        self.array = [
            [self.institution, self.audience],
            [speaker, videoslidespaper if past else self.recent],
            [affiliation] if past else [affiliation, livestream_available],
            [date, time],
        ]

class SeriesSearchArray(SemSearchArray):
    def __init__(self, conference=False, past=False):
        SemSearchArray.__init__(self)
        organizer = TextBox(
            name="organizer",
            label="Organizer",
            width=textwidth,
        )
        date = TextBox(
            name="daterange",
            id="daterange",
            label="Date",
            example=datetime.now(current_user.tz).strftime("%B %d, %Y -"),
            example_value=True,
            width=textwidth,
            extra=['autocomplete="off"'],
        )

        self.array = [
            [self.institution, self.audience],
            [organizer] if past else [organizer, self.recent],
        ]
        if conference:
            self.array.append([date])

        assert conference in [True, False]
        self.conference = conference

@app.route("/", methods=["GET"])
def index():
    if request.args.get("submit"):
        x = request.args["submit"].strip().split(' ')
        subsection=x[0]
        keywords = ' '.join(x[1:])
        return redirect(url_for_with_args(subsection+"_index", {'keywords': keywords} if keywords else {}))
    return _talks_index(subsection="talks")

@app.route("/talks")
def talks_index():
    return _talks_index(subsection="talks")

@app.route("/conferences")
def conferences_index():
    return _series_index({"is_conference": True}, subsection="conferences", conference=True)

@app.route("/seminar_series")
def seminar_series_index():
    return _series_index({"is_conference": False}, subsection="seminar_series", conference=False)

@app.route("/past_talks")
def past_talks_index():
    return _talks_index(subsection="past_talks", past=True)

@app.route("/past_conferences")
def past_conferences_index():
    return _series_index({"is_conference": True}, subsection="past_conferences", conference=True, past=True)

def read_search_cookie(search_array):
    info = {}
    for row in search_array.array:
        for box in row:
            if isinstance(box, TripleToggle):
                for name in [box.name, box.mtoggle.name, box.rtoggle.name]:
                    info[name] = request.cookies.get("search_" + name, "")
            elif isinstance(box, SearchBox):
                info[box.name] = request.cookies.get("search_" + box.name, "")
    return info

def _get_counters(objects):
    topic_counts = Counter()
    language_counts = Counter()
    for object in objects:
        if object.topics:
            for topic in object.topics:
                topic_counts[topic] += 1
        language_counts[object.language] += 1
    langs = [(code, languages.show(code)) for code in language_counts]
    langs.sort(key=lambda x: (-language_counts[x[0]], x[1]))
    return {"topic_counts": topic_counts, "language_counts": language_counts}

def _get_row_attributes(objects):
    filtered_topics = topic_dag.filtered_topics()
    filter_topic = request.cookies.get('filter_topic', '-1') == '1'
    filtered_languages = set(request.cookies.get('languages', '').split(','))
    filter_language = request.cookies.get('filter_language', '-1') == '1'
    filter_calendar = request.cookies.get('filter_calendar', '-1') == '1'
    filter_more = request.cookies.get('filter_more', '-1') == '1'
    def filter_classes(obj):
        filtered = False
        classes = ['talk']

        topic_filtered = True
        for topic in obj.topics:
            classes.append("topic-" + topic)
            if topic in filtered_topics:
                topic_filtered = False
        if topic_filtered:
            classes.append('topic-filtered')
            if filter_topic:
                filtered = True

        classes.append("lang-" + obj.language)
        if obj.language not in filtered_languages:
            classes.append("language-filtered")
            if filter_language:
                filtered = True
        if not obj.is_subscribed():
            classes.append("calendar-filtered")
            if filter_calendar:
                filtered = True
        if not obj.more:
            classes.append("more-filtered")
            if filter_more:
                filtered = True
        return classes, filtered

    attributes = []
    visible_counter = 0
    for obj in objects:
        classes, filtered = filter_classes(obj)
        if isinstance(obj, WebTalk) and obj.blackout_date() and obj.rescheduled():
            classes.append("blm")
        style = ""
        if filtered:
            style = ' style="display: none;"'
        else:
            if visible_counter % 2: # odd
                classes.append("oddrow")
                #style = "background: #E3F2FD;"
            else:
                classes.append("evenrow")
                #style = "background: none;"
            visible_counter += 1
        row_attributes = 'class="{classes}"{style}'.format(
            classes=' '.join(classes),
            style=style)
        attributes.append(row_attributes)

    return attributes


def _talks_index(query={}, sort=None, subsection=None, past=False, keywords=""):
    # Eventually want some kind of cutoff on which talks are included.
    search_array = TalkSearchArray(past=past)
    info = to_dict(read_search_cookie(search_array), search_array=search_array)
    info.update(request.args)
    if keywords:
        info["keywords"] = keywords
    query = dict(query)
    parse_substring(info, query, "keywords",
                    ["title",
                     "abstract",
                     "speaker",
                     "speaker_affiliation",
                     "seminar_id",
                     "comments",
                     "speaker_homepage",
                     "paper_link"])
    more = {} # we will be selecting talks satsifying the query and recording whether they satisfy the "more" query
    # Note that talks_parser ignores the "time" field at the moment; see below for workaround
    talks_parser(info, more)
    if topdomain() == "mathseminars.org":
        query["topics"] = {"$contains": "math"}
    query["display"] = True
    query["hidden"] = {"$or": [False, {"$exists": False}]}
    query["audience"] = {"$lte" : DEFAULT_AUDIENCE}
    if past:
        query["end_time"] = {"$lt": datetime.now(pytz.UTC)}
        query["seminar_ctr"] = {"$gt": 0} # don't show rescheduled talks
        if sort is None:
            sort = [("start_time", -1), "seminar_id"]
    else:
        query["end_time"] = {"$gte": datetime.now(pytz.UTC)}
        if sort is None:
            sort = ["start_time", "seminar_id"]
    talks = list(talks_search(query, sort=sort, seminar_dict=all_seminars(), more=more))
    # Filtering on display and hidden isn't sufficient since the seminar could be private
    talks = [talk for talk in talks if talk.searchable()]
    # While we may be able to write a query specifying inequalities on the timestamp in the user's timezone, it's not easily supported by talks_search.  So we filter afterward
    timerange = info.get("timerange", "").strip()
    if timerange:
        tz = current_user.tz
        try:
            timerange = process_user_input(timerange, col="search", typ="daytimes")
        except ValueError:
            try:
                onetime = process_user_input(timerange, col="search", typ="daytime")
            except ValueError:
                flash_error("Invalid time range input: %s", timerange)
            else:
                for talk in talks:
                    if talk.more:
                        talkstart = adapt_datetime(talk.start_time, tz)
                        t = date_and_daytime_to_time(talkstart.date(), onetime, tz)
                        talk.more = (t == talkstart)
        else:
            for talk in talks:
                if talk.more:
                    talkstart = adapt_datetime(talk.start_time, tz)
                    talkend = adapt_datetime(talk.end_time, tz)
                    t0, t1 = date_and_daytimes_to_times(talkstart.date(), timerange, tz)
                    talk.more = (t0 <= talkstart) and (talkend <= t1)
    counters = _get_counters(talks)
    row_attributes = _get_row_attributes(talks)
    response = make_response(render_template(
        "browse_talks.html",
        title="Browse past talks" if past else "Browse talks",
        section="Browse",
        info=info,
        subsection=subsection,
        talk_row_attributes=zip(talks, row_attributes),
        past=past,
        **counters
    ))
    if request.cookies.get("topics", ""):
        # TODO: when we move cookie data to server with ajax calls, this will need to get updated again
        # For now we set the max_age to 30 years
        response.set_cookie("topics_dict", topic_dag.port_cookie(), max_age=60*60*24*365*30)
        response.set_cookie("topics", "", max_age=0)
    return response

def _series_index(query, sort=None, subsection=None, conference=True, past=False, keywords=""):
    search_array = SeriesSearchArray(conference=conference, past=past)
    info = to_dict(read_search_cookie(search_array), search_array=search_array)
    info.update(request.args)
    if keywords:
        info["keywords"] = keywords
    query = dict(query)
    if conference:
        # Be permissive on end-date since we don't want to miss ongoing conferences, and we could have time zone differences.
        # Ignore the possibility that the user/conference is in Kiribati.
        recent = datetime.now().date() - timedelta(days=1)
        query["end_date"] = {"$lt" if past else "$gte": recent}
    query["visibility"] = 2 # only show public talks
    query["display"] = True # don't show talks created by users who have not been endorsed
    kw_query = query.copy()
    parse_substring(info, kw_query, "keywords", series_keyword_columns())
    org_query, more = {}, {}
    # we will be selecting talks satsifying the query and recording whether they satisfy the "more" query
    seminars_parser(info, more, org_query)
    results = list(seminars_search(kw_query, organizer_dict=all_organizers(org_query), more=more))
    if info.get("keywords", ""):
        parse_substring(info, org_query, "keywords", organizers_keyword_columns())
        results += list(seminars_search(query, organizer_dict=all_organizers(org_query), more=more))
        unique = {s.shortname:s for s in results}
        results = [unique[key] for key in unique]
    series = series_sorted(results, conference=conference, reverse=past)
    counters = _get_counters(series)
    row_attributes = _get_row_attributes(series)
    response = make_response(render_template(
        "browse_series.html",
        title="Browse " + ("past " if past else "") + ("conferences" if conference else "seminar series"),
        section="Browse",
        subsection=subsection,
        info=info,
        series_row_attributes=zip(series, row_attributes),
        is_conference=conference,
        past=past,
        **counters
    ))
    if request.cookies.get("topics", ""):
        # TODO: when we move cookie data to server with ajax calls, this will need to get updated again
        # For now we set the max_age to 30 years
        response.set_cookie("topics_dict", topic_dag.port_cookie(), max_age=60*60*24*365*30)
        response.set_cookie("topics", "", max_age=0)
    return response

@app.route("/institutions/")
def list_institutions():
    section = "Manage" if current_user.is_creator else None
    return render_template(
        "institutions.html",
        title="Institutions",
        section=section,
        subsection="institutions",
        maintained_institutions=institutions({'admin':current_user.email}),
        institutions=institutions(),
        maxlength=maxlength,
    )


@app.route("/seminar/<shortname>")
def show_seminar(shortname):
    # We need organizers to be able to see seminars with display=False
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None:
        return abort(404, "Seminar not found")
    if not seminar.visible():
        # There may be a non-API version of the seminar that can be shown
        seminar = seminars_lucky({"shortname": shortname})
        if seminar is None or not seminar.visible():
            flash_error("You do not have permission to view %s", seminar.name)
            return redirect(url_for("seminar_series_index"), 302)
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
    if current_user.email in seminar.editors() or current_user.is_subject_admin(seminar):
        section = "Manage"
    else:
        section = None
    return render_template(
        "seminar.html",
        title="View series",
        future=future,
        past=past,
        seminar=seminar,
        section=section,
        subsection="view",
        bread=None,
    )


def talks_search_api(shortname, projection=1):
    query = {"seminar_id": shortname, "seminar_ctr": {"$gt": 0}, "display": True, "hidden": {"$or": [False, {"$exists": False}]}}
    reverse_sort = False
    if 'daterange' in request.args:
        if request.args.get('daterange') == 'past':
            query["start_time"] = {'$lte': get_now()}
        elif request.args.get('daterange') == 'future':
            query["start_time"] = {'$gte': get_now()}
        else:
            parse_daterange(request.args, query, time=True)
    elif 'past' in request.args and 'future' in request.args:
        # no restriction on date
        pass
    elif 'past' in request.args:
        query["start_time"] = {'$lte': get_now()}
        reverse_sort = True
    elif 'future' in request.args:
        query["start_time"] = {'$gte': get_now()}
    talks = list(talks_search(query, projection=3))
    talks.sort(key=lambda talk: talk.start_time, reverse=reverse_sort)
    return talks

@app.route("/seminar/<shortname>/bare")
def show_seminar_bare(shortname):
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None or not seminar.visible():
        # There may be a non-API version of the seminar that can be shown
        seminar = seminars_lucky({"shortname": shortname})
        if seminar is None or not seminar.visible():
            return abort(404, "Seminar not found")
    talks = talks_search_api(shortname)
    timezone = seminar.tz
    if 'timezone' in request.args:
        try:
            timezone = pytz.timezone(request.args.get("timezone"))
        except pytz.UnknownTimeZoneError:
            pass
    resp = make_response(render_template("seminar_bare.html",
                                         title=seminar.name, talks=talks,
                                         seminar=seminar,
                                         _external=( '_external' in request.args ),
                                         site_footer=( 'site_footer' in request.args ),
                                         timezone=timezone))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

@app.route("/seminar/<shortname>/json")
def show_seminar_json(shortname):
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None or not seminar.visible():
        # There may be a non-API version of the seminar that can be shown
        seminar = seminars_lucky({"shortname": shortname})
        if seminar is None or not seminar.visible():
            return abort(404, "Seminar not found")
    # FIXME
    cols = [
        'speaker',
        'video_link',
        'slides_link',
        'title',
        'room',
        'comments',
        'abstract',
        'start_time',
        'end_time',
        'speaker_affiliation',
        'speaker_homepage',
        'language',
        'deleted',
        'paper_link',
        'stream_link',
    ]
    talks = [
        {c: getattr(elt, c) for c in cols}
        for elt in talks_search_api(shortname, projection=["seminar_id"] + cols)
    ]
    callback = request.args.get("callback", False)
    if callback:
        return Response(
            "{}({})".format(str(callback), json.dumps(talks, default=str)),
            mimetype="application/javascript",
        )
    else:
        return Response(json.dumps(talks, default=str), mimetype="application/json")

@app.route("/embeddable_schedule.js")
def show_seminar_js():
    """
    Usage example:
    <div class="embeddable_schedule" shortname="LATeN" daterange="future"></div>
    <div class="embeddable_schedule" shortname="LATeN" daterange="past"></div>
    <div class="embeddable_schedule" shortname="LATeN" daterange="future"></div>
    <script src="http://localhost:37778/embeddable_schedule.js" onload='embed_schedule();'></script>
    """
    resp = make_response(render_template('seminar_raw.js', scheme=request.scheme))
    resp.headers['Content-type'] = 'text/javascript'
    return resp

@app.route("/embed_seminars.js")
def embed_seminar_js():
    """
    Usage example:
    <div class="embeddable_schedule" shortname="LATeN" daterange="April 23, 2020 - April 29, 2020"></div>
    <div class="embeddable_schedule" shortname="LATeN" daterange="past"></div>
    <div class="embeddable_schedule" shortname="LATeN" daterange="future"></div>
    <script src="http://localhost:37778/embed_seminars.js" onload="seminarEmbedder.initialize({'addCSS': true});"></script>
    """
    resp = make_response(render_template('embed_seminars.js', scheme=request.scheme))
    resp.headers['Content-type'] = 'text/javascript'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

@app.route("/seminar/<shortname>/ics")
def ics_seminar_file(shortname):
    seminar = seminars_lucky({"shortname": shortname})
    if seminar is None or not seminar.visible():
        # There may be a non-API version of the seminar that can be shown
        seminar = seminars_lucky({"shortname": shortname})
        if seminar is None or not seminar.visible():
            return abort(404, "Seminar not found")

    return ics_file(
        seminar.talks(),
        filename="{}.ics".format(shortname),
        user=current_user)


@app.route("/talk/<seminar_id>/<int:talkid>/ics")
def ics_talk_file(seminar_id, talkid):
    talk = talks_lucky({"seminar_id": seminar_id, "seminar_ctr": talkid})
    if talk is None:
        return abort(404, "Talk not found")
    return ics_file(
        [talk],
        filename="{}_{}.ics".format(seminar_id, talkid),
        user=current_user)


@app.route("/talk/<seminar_id>/<int:talkid>/")
def show_talk(seminar_id, talkid):
    token = request.args.get("token", "")  # save the token so user can toggle between view and edit
    talk = talks_lucky({"seminar_id": seminar_id, "seminar_ctr": talkid})
    if talk is None:
        return abort(404, "Talk not found")
    if not talk.visible():
        # There may be a non-API version of the seminar that can be shown
        talk = talks_lucky({"seminar_id": seminar_id, "seminar_ctr": talkid})
        if talk is None or not talk.visible():
            flash_error("You do not have permission to view %s/%s", seminar_id, talkid)
            return redirect(url_for("seminar_series_index"))
    kwds = dict(
        title="View talk", talk=talk, seminar=talk.seminar, subsection="viewtalk", token=token
    )
    if token:
        kwds["section"] = "Manage"
        # Also want to override top menu
        from seminars.utils import top_menu

        menu = top_menu()
        menu[1] = (url_for("create.index"), "", "Manage")
        kwds["top_menu"] = menu
    elif (
        current_user.is_subject_admin(talk)
        or current_user.email_confirmed
        and (
            current_user.email in talk.seminar.editors() or current_user.email == talk.speaker_email
        )
    ):
        kwds["section"] = "Manage"
    return render_template("talk.html", **kwds)


@app.route("/register/talk/<seminar_id>/<int:talkid>/")
def register_for_talk(seminar_id, talkid):
    from flask import flash
    talk = talks_lucky({"seminar_id": seminar_id, "seminar_ctr": talkid})
    if talk is None:
        return abort(404, "Talk not found")
    # If registration isn't required just send them to the talk page
    # where the user will see an appropriate livestream link
    if talk.access_control != 4:
        return redirect(url_for('show_talk',seminar_id=seminar_id,talkid=talkid))
    if current_user.is_anonymous:
        return redirect(url_for("user.info", next=url_for("register_for_talk", seminar_id=seminar_id, talkid=talkid)))
    if not current_user.email_confirmed:
        flash_error("You need to confirm your email before you can register.")
        return redirect(url_for('show_talk',seminar_id=seminar_id,talkid=talkid))
    if not talk.live_link:
        return abort(404, "Livestream link for talk not found")
    if talk.register_user():
        flash("You have been registered, enjoy the talk!")
    else:
        flash("Previous registration confirmed, enjoy the talk!")
    if talk.is_starting_soon():
        return redirect(talk.live_link)
    else:
        return redirect(url_for('show_talk',seminar_id=seminar_id,talkid=talkid))


# We allow async queries for title knowls
@app.route("/knowl/talk/<series_id>/<int:series_ctr>")
def title_knowl(series_id, series_ctr, **kwds):
    talk = talks_lookup(series_id, series_ctr)
    if talk is None:
        return render_template("404_content.html"), 404
    else:
        # tz = None, uses the users timezone
        return render_template("talk-knowl.html", talk=talk, tz=None)


@app.route("/institution/<shortname>/")
def show_institution(shortname):
    institution = db.institutions.lookup(shortname)
    if institution is None:
        return abort(404, "Institution not found")
    institution = WebInstitution(shortname, data=institution)
    section = "Manage" if current_user.is_creator else None
    query = {"institutions": {"$contains": shortname}}
    if not current_user.is_admin:
        query["display"] = True
    events = next_talk_sorted(list(seminars_search(query, organizer_dict=all_organizers())))
    seminars = [S for S in events if not S.is_conference]
    conferences = [S for S in events if S.is_conference]
    conferences.sort(key=lambda S: (S.start_date, S.name))
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

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", title="Privacy policy", section="Info", subsection="privacy")

@app.route("/policies")
def policies():
    return render_template("policies.html", title="Policies", section="Info", subsection="policies")


@app.route("/faq")
def faq():
    return render_template("faq.html", title="Frequently asked questions", section="Info", subsection="faq")


@app.route("/ams")
def ams():
    seminars = next_talk_sorted(
        seminars_search(
            query={"topics": {'$contains': "math"}},
            organizer_dict=all_organizers(),
        )
    )
    from collections import defaultdict
    math_topics = {rec["topic_id"]: rec["name"].capitalize() for rec in db.new_topics.search({"topic_id":{"$in":list(db.new_topics.lookup("math", "children"))}})}
    seminars_dict = defaultdict(list)
    for sem in seminars:
        for topic in sem.topics:
            if topic in math_topics:
                seminars_dict[topic].append(sem)
    return render_template("ams.html",
                           title="AMS example",
                           math_topics=sorted(math_topics.items(), key=lambda x: x[1]),
                           seminars_dict=seminars_dict)


