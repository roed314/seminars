from datetime import datetime, timedelta
from dateutil.parser import parse as parse_time
import pytz, re, iso639
from six import string_types
from flask import url_for, flash, render_template, request
from flask_login import current_user
from seminars import db
from functools import lru_cache
from lmfdb.backend.utils import IdentifierWrapper
from lmfdb.utils.search_boxes import SearchBox
from psycopg2.sql import SQL
from markupsafe import Markup, escape
from collections.abc import Iterable
from urllib.parse import urlparse
from email_validator import validate_email

weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
short_weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def topdomain():
    # return 'mathseminars.org'
    # return 'researchseminars.org'
    return '.'.join(urlparse(request.url).netloc.split('.')[-2:])

def validate_url(x):
    if not (x.startswith("http://") or x.startswith("https://")):
        return False
    try:
        result = urlparse(x)
        return all([result.scheme, result.netloc])
    except:
        return False

def make_links(x):
    """ Given a blob of text looks for URLs (beggining with http:// or https://) and makes them hyperlinks. """
    tokens = re.split(r'(\s+)',x)
    for i in range(len(tokens)):
        if validate_url(tokens[i]):
            tokens[i] = '<a href="%s">%s</a>'%(tokens[i], tokens[i][tokens[i].index("//")+2:])
    return ''.join(tokens)

def naive_utcoffset(tz):
    if isinstance(tz, str):
        tz = pytz.timezone(tz)
    for h in range(10):
        try:
            return tz.utcoffset(datetime.now() + timedelta(hours=h))
        except (pytz.exceptions.NonExistentTimeError, pytz.exceptions.AmbiguousTimeError):
            pass


def timestamp():
    return "[%s UTC]" % datetime.now(tz=pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")


def pretty_timezone(tz, dest="selecter"):
    foo = int(naive_utcoffset(tz).total_seconds())
    hours, remainder = divmod(abs(foo), 3600)
    minutes, seconds = divmod(remainder, 60)
    if dest == "selecter":  # used in time zone selecters
        if foo < 0:
            diff = "-{:02d}:{:02d}".format(hours, minutes)
        else:
            diff = "+{:02d}:{:02d}".format(hours, minutes)
        return "(UTC {}) {}".format(diff, tz)
    else:
        tz = str(tz).replace("_", " ")
        if minutes == 0:
            diff = "{}".format(hours)
        else:
            diff = "{}:{:02d}".format(hours, minutes)
        if foo < 0:
            diff = "-" + diff
        else:
            diff = "+" + diff
        if dest == "browse":  # used on browse page by filters
            return "{} (now UTC {})".format(tz, diff)
        else:
            return "{} (UTC {})".format(tz, diff)


timezones = [(v, pretty_timezone(v)) for v in sorted(pytz.common_timezones, key=naive_utcoffset)]


def is_nighttime(t):
    if t is None:
        return False
    # These are times that might be mixed up by using a 24 hour clock
    return 1 <= t.hour < 6


def simplify_language_name(name):
    name = name.split(";")[0]
    if "(" in name:
        name = name[: name.find("(") - 1]
    return name

@lru_cache(maxsize=None)
def languages_dict():
    return {lang["iso639_1"]: simplify_language_name(lang["name"]) for lang in iso639.data if lang["iso639_1"]}


def clean_language(inp):
    if inp not in languages_dict():
        return "en"
    else:
        return inp


def flash_warning(warnmsg, *args):
    flash(
        Markup("Warning: " + (warnmsg % tuple("<span style='color:black'>%s</span>" % escape(x) for x in args))),
        "error",
    )


def sanity_check_times(start_time, end_time):
    """
    Flashes warnings if time range seems suspsicious.  Note that end_time is (by definition) greater than start_time
    """
    if start_time is None or end_time is None:
        # Users are allowed to not fill in a time
        return
    if start_time > end_time:
        end_time = end_time + timedelta(days=1)
    if start_time + timedelta(hours=8) < end_time:
        flash_warning("Time range exceeds 8 hours, please update if that was unintended.")
    if is_nighttime(start_time) or is_nighttime(end_time):
        flash_warning(
            "Time range includes monring hours before 6am. Please update using 24-hour notation, or specify am/pm, if that was unintentional."
        )


def top_menu():
    if current_user.is_authenticated:
        account = "Account"
    else:
        account = "Login"
    if current_user.is_organizer:
        manage = "Manage"
    else:
        manage = "Create"
    return [
        (url_for("index"), "", "Browse"),
        (url_for("search"), "", "Search"),
        (url_for("create.index"), "", manage),
        (url_for("info"), "", "Info"),
        (url_for("user.info"), "", account),
    ]


shortname_re = re.compile("^[A-Za-z0-9_-]+$")


def allowed_shortname(shortname):
    return bool(shortname_re.match(shortname))


# Note the caching: if you add a topic you have to restart the server
@lru_cache(maxsize=None)
def topics():
    return sorted(
        ((rec["abbreviation"], rec["name"], rec["subject"]) for rec in db.topics.search({}, ["abbreviation", "name", "subject"])),
        key=lambda x: (x[2].lower(), x[1].lower()),
    )

# A temporary measure in case talks/seminars with physics topics are visible (they might be crosslisted with math)
@lru_cache(maxsize=None)
def physics_topic_dict():
    return dict([(rec["subject"] + "_" + rec["abbreviation"], rec["name"]) for rec in db.topics.search()])

def restricted_topics(talk_or_seminar=None):
    if topdomain() == 'mathseminars.org':
        if talk_or_seminar is None or talk_or_seminar.subjects is None:
            subjects = []
        else:
            subjects = talk_or_seminar.subjects
        return [('math_' + ab, name) for (ab, name, subj) in topics() if subj == "math" or subj in subjects]
    else:
        return user_topics(talk_or_seminar)

def user_topics(talk_or_seminar=None):
    subjects = []
    if talk_or_seminar is not None:
        subjects = sorted(set(subjects + talk_or_seminar.subjects))
    if len(subjects) == 1:
        subject = subjects[0]
        return [(subj + '_' + ab, name) for (ab, name, subj) in topics() if subj == subject]
    if len(subjects) == 0:
        # Show all subjects rather than none
        subjects = [subj for (subj, name) in subject_pairs()]
    return [(subj + '_' + ab, subj.capitalize() + ': ' + name) for (ab, name, subj) in topics() if subj in subjects]

@lru_cache(maxsize=None)
def subject_pairs():
    return sorted(
        tuple(set(((rec["subject"], rec["subject"].capitalize()) for rec in db.topics.search({}, ["subject"])))),
        key=lambda x: x[1].lower(),
    )


@lru_cache(maxsize=None)
def subject_dict():
    return dict(subject_pairs())

@lru_cache(maxsize=None)
def topic_dict(include_subj=True):
    if include_subj:
        return {subj + "_" + ab: subj.capitalize() + ": " + name for (ab, name, subj) in topics()}
    else:
        return {subj + "_" + ab: name for (ab, name, subj) in topics()}



def clean_topics(inp):
    if inp is None:
        return []
    if isinstance(inp, str):
        inp = inp.strip()
        if inp and inp[0] == "[" and inp[-1] == "]":
            inp = [elt.strip().strip("'") for elt in inp[1:-1].split(",")]
            if inp == [""]:  # was an empty array
                return []
        else:
            inp = [inp]
    if isinstance(inp, Iterable):
        inp = [elt for elt in inp if elt in topic_dict()]
    return inp

def clean_subjects(inp):
    if inp is None:
        return []
    if isinstance(inp, str):
        inp = inp.strip()
        if inp and inp[0] == "[" and inp[-1] == "]":
            inp = [elt.strip().strip("'") for elt in inp[1:-1].split(",")]
            if inp == [""]: # was an empty array
                return []
        else:
            inp = [inp]
    if isinstance(inp, Iterable):
        inp = [elt for elt in inp if elt in subject_dict()]
    return inp

def count_distinct(table, counter, query={}, include_deleted=False):
    query = dict(query)
    if not include_deleted:
        query["deleted"] = {"$or": [False, {"$exists": False}]}
    cols = SQL(", ").join(map(IdentifierWrapper, table.search_cols))
    tbl = IdentifierWrapper(table.search_table)
    qstr, values = table._build_query(query, sort=[])
    counter = counter.format(cols, tbl, qstr)
    cur = table._execute(counter, values)
    return int(cur.fetchone()[0])


def max_distinct(table, maxer, col, constraint={}, include_deleted=False):
    # Note that this will return None for the max of an empty set
    constraint = dict(constraint)
    if not include_deleted:
        constraint["deleted"] = {"$or": [False, {"$exists": False}]}
    cols = SQL(", ").join(map(IdentifierWrapper, table.search_cols))
    tbl = IdentifierWrapper(table.search_table)
    qstr, values = table._build_query(constraint, sort=[])
    maxer = maxer.format(IdentifierWrapper(col), cols, tbl, qstr)
    cur = table._execute(maxer, values)
    return cur.fetchone()[0]


def search_distinct(
    table,
    selecter,
    counter,
    iterator,
    query={},
    projection=1,
    limit=None,
    offset=0,
    sort=None,
    info=None,
    include_deleted=False,
):
    """
    Replacement for db.*.search to account for versioning, return Web* objects.

    Doesn't support split_ors, raw or extra tables.  Always computes count.

    INPUT:

    - ``table`` -- a search table, such as db.seminars or db.talks
    - ``counter`` -- an SQL object counting distinct entries
    - ``selecter`` -- an SQL objecting selecting distinct entries
    - ``iterator`` -- an iterator taking the same arguments as ``_search_iterator``
    """
    if offset < 0:
        raise ValueError("Offset cannot be negative")
    query = dict(query)
    if not include_deleted:
        query["deleted"] = {"$or": [False, {"$exists": False}]}
    all_cols = SQL(", ").join(map(IdentifierWrapper, ["id"] + table.search_cols))
    search_cols, extra_cols = table._parse_projection(projection)
    cols = SQL(", ").join(map(IdentifierWrapper, search_cols + extra_cols))
    tbl = IdentifierWrapper(table.search_table)
    nres = count_distinct(table, counter, query)
    if limit is None:
        qstr, values = table._build_query(query, sort=sort)
    else:
        qstr, values = table._build_query(query, limit, offset, sort)
    fselecter = selecter.format(cols, all_cols, tbl, qstr)
    cur = table._execute(
        fselecter,
        values,
        buffered=(limit is None),
        slow_note=(table.search_table, "analyze", query, repr(projection), limit, offset),
    )
    results = iterator(cur, search_cols, extra_cols, projection)
    if limit is None:
        if info is not None:
            # caller is requesting count data
            info["number"] = nres
        return results
    if info is not None:
        if offset >= nres > 0:
            # We're passing in an info dictionary, so this is a front end query,
            # and the user has requested a start location larger than the number
            # of results.  We adjust the results to be the last page instead.
            offset -= (1 + (offset - nres) / limit) * limit
            if offset < 0:
                offset = 0
            return search_distinct(table, selecter, counter, iterator, query, projection, limit, offset, sort, info)
        info["query"] = dict(query)
        info["number"] = nres
        info["count"] = limit
        info["start"] = offset
        info["exact_count"] = True
    return list(results)


def lucky_distinct(table, selecter, construct, query={}, projection=2, offset=0, sort=[], include_deleted=False):
    query = dict(query)
    if not include_deleted:
        query["deleted"] = {"$or": [False, {"$exists": False}]}
    all_cols = SQL(", ").join(map(IdentifierWrapper, ["id"] + table.search_cols))
    search_cols, extra_cols = table._parse_projection(projection)
    cols = SQL(", ").join(map(IdentifierWrapper, search_cols + extra_cols))
    qstr, values = table._build_query(query, 1, offset, sort=sort)
    tbl = table._get_table_clause(extra_cols)
    fselecter = selecter.format(cols, all_cols, tbl, qstr)
    cur = table._execute(fselecter, values)
    if cur.rowcount > 0:
        rec = cur.fetchone()
        if projection == 0 or isinstance(projection, string_types):
            rec = rec[0]
        else:
            rec = {k: v for k, v in zip(search_cols + extra_cols, rec)}
        return construct(rec)


def localize_time(t, newtz=None):
    """
    Takes a time or datetime object and adds in a timezone if not already present.
    """
    if t.tzinfo is None:
        if newtz is None:
            newtz = current_user.tz
        return newtz.localize(t)
    else:
        return t


def adapt_datetime(t, newtz=None):
    """
    Converts a time-zone-aware datetime object into a specified time zone
    (current user's time zone by default).
    """
    if t is None:
        return None
    if newtz is None:
        newtz = current_user.tz
    return t.astimezone(newtz)


def adapt_weektime(t, oldtz, newtz=None, weekday=None):
    """
    Converts a weekday and time in a given time zone to the specified new time zone using the next valid date.
    """
    if isinstance(oldtz, str):
        oldtz = pytz.timezone(oldtz)
    now = datetime.now(oldtz)
    # The t we obtain from psycopg2 comes with tzinfo, but we need to forget it
    # in order to compare with now.time()
    tblank = t.replace(tzinfo=None).time()
    if weekday is None:
        days_ahead = 0 if now.time() <= tblank else 1
    else:
        days_ahead = weekday - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.time() > tblank):
            days_ahead += 7
    next_t = oldtz.localize(datetime.combine(now.date() + timedelta(days=days_ahead), t.time()))
    next_t = adapt_datetime(next_t, newtz)
    if weekday is None:
        return None, next_t.time()
    else:
        return next_t.weekday(), next_t.time()


def process_user_input(inp, col, typ, tz):
    """
    INPUT:

    - ``inp`` -- unsanitized input, as a string (or None)
    - ''col'' -- column name (names ending in ''link'', ''page'', ''time'', ''email'' get special handling
    - ``typ`` -- a Postgres type, as a string
    """
    if inp:
        inp = inp.strip()
    if not inp:
        return False if typ == "boolean" else ("" if typ == "text" else None)
    elif typ == "time":
        # Note that parse_time, when passed a time with no date, returns
        # a datetime object with the date set to today.  This could cause different
        # relative orders around daylight savings time, so we store all times
        # as datetimes on Jan 1, 2020.
        if inp.isdigit():
            inp += ":00"  # treat numbers as times not dates
        t = parse_time(inp)
        t = t.replace(year=2020, month=1, day=1)
        return localize_time(t, tz)
    elif (col.endswith("page") or col.endswith("link")) and typ == "text":
        if not validate_url(inp) and not (col == "live_link" and (inp == "see comments" or inp == "See comments")):
            raise ValueError("Invalid URL")
        return inp
    elif col.endswith("email") and typ == "text":
        return validate_email(inp.strip())["email"]
    elif typ == "timestamp with time zone":
        return localize_time(parse_time(inp), tz)
    elif typ == "date":
        return parse_time(inp).date()
    elif typ == "boolean":
        if inp in ["yes", "true", "y", "t"]:
            return True
        elif inp in ["no", "false", "n", "f"]:
            return False
        raise ValueError("Invalid boolean")
    elif typ == "text":
        # should sanitize somehow?
        return "\n".join(inp.splitlines())
    elif typ in ["int", "smallint", "bigint", "integer"]:
        return int(inp)
    elif typ == "text[]":
        if inp:
            if inp[0] == "[" and inp[-1] == "]":
                res = [elt.strip().strip("'") for elt in inp[1:-1].split(",")]
                if res == [""]:  # was an empty array
                    return []
                else:
                    return res
            else:
                # Temporary measure until we incorporate https://www.npmjs.com/package/select-pure (demo: https://www.cssscript.com/demo/multi-select-autocomplete-selectpure/)
                return [inp]
        else:
            return []
    else:
        raise ValueError("Unrecognized type %s" % typ)


def format_errmsg(errmsg, *args):
    return Markup("Error: " + (errmsg % tuple("<span style='color:black'>%s</span>" % escape(x) for x in args)))

def format_input_errmsg(err, inp, col):
    return format_errmsg('Unable to process input %s for property %s: {0}'.format(err), '"' + str(inp) + '"', col)

def format_warning(errmsg, *args):
    return Markup("Warning: " + (errmsg % tuple("<span style='color:black'>%s</span>" % escape(x) for x in args)))


def show_input_errors(errmsgs):
    """ Flashes a list of specific user input error messages then displays a generic message telling the user to fix the problems and resubmit. """
    assert errmsgs
    for msg in errmsgs:
        flash(msg, "error")
    return render_template("inputerror.html", messages=errmsgs)


def toggle(tglid, value, checked=False, classes="", onchange="", name=""):
    if classes:
        classes += " "
    return """
<input type="checkbox" class="{classes}tgl tgl-light" value="{value}" id="{tglid}" onchange="{onchange}" name="{name}" {checked}>
<label class="tgl-btn" for="{tglid}"></label>
""".format(
        tglid=tglid, value=value, checked="checked" if checked else "", classes=classes, onchange=onchange, name=name,
    )


class Toggle(SearchBox):
    def _input(self, info=None):
        main = toggle(
            tglid="toggle_%s" % self.name,
            name=self.name,
            value="yes",
            checked=info is not None and info.get(self.name, False),
        )
        return '<span style="display: inline-block">%s</span>' % (main,)
