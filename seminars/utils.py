from collections.abc import Iterable
from datetime import datetime, timedelta
from datetime import time as maketime
from dateutil.parser import parse as parse_time
from email_validator import validate_email
from flask import url_for, flash, render_template, request, send_file
from flask_login import current_user
from functools import lru_cache
from icalendar import Calendar
from io import BytesIO
from lmfdb.backend.utils import IdentifierWrapper
from lmfdb.utils.search_boxes import SearchBox
from markupsafe import Markup, escape
from psycopg2.sql import SQL
from seminars import db
from six import string_types
from urllib.parse import urlparse, urlencode
from psycopg2.sql import Placeholder
import pytz
import re
from lmfdb.backend.searchtable import PostgresSearchTable
from .toggle import toggle


weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
short_weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
daytime_re_string = r"\d{1,4}|\d{1,2}:\d\d|"
daytime_re = re.compile(daytime_re_string)
dash_re = re.compile(r'[\u002D\u058A\u05BE\u1400\u1806\u2010-\u2015\u2E17\u2E1A\u2E3A\u2E3B\u2E40\u301C\u3030\u30A0\uFE31\uFE32\uFE58\uFE63\uFF0D]')

# the columns speaker, speaker_email, speaker_homepage, and speaker_affiliation are
# text strings that may contain delimited lists (which should all have the same length, empty items are OK)
SPEAKER_DELIMITER = '|'

# Bounds on input field lengths
MAX_SHORTNAME_LEN = 32
MAX_DESCRIPTION_LEN = 64
MAX_HINT_LEN = 64
MAX_NAME_LEN = 100
MAX_TITLE_LEN = 256
MAX_EMAIL_LEN = 256
MAX_URL_LEN = 256
MAX_TEXT_LEN = 8192
MAX_SLOTS = 12 # Must be a multiple of 3
MAX_SPEAKERS = 8
MAX_ORGANIZERS = 10

maxlength = {
    'abstract' : MAX_TEXT_LEN,
    'access_hint' : MAX_HINT_LEN,
    'access_registration' : MAX_URL_LEN,
    'aliases' : MAX_NAME_LEN,
    'chat_link' : MAX_URL_LEN,
    'city' : MAX_NAME_LEN,
    'comments' : MAX_TEXT_LEN,
    'description' : MAX_DESCRIPTION_LEN,
    'homepage' : MAX_URL_LEN,
    'institutions.name' : MAX_DESCRIPTION_LEN,
    'live_link' : MAX_URL_LEN,
    'name' : MAX_NAME_LEN,
    'organizers' : MAX_ORGANIZERS,
    'paper_link' : MAX_URL_LEN,
    'room' : MAX_NAME_LEN,
    'shortname' : MAX_SHORTNAME_LEN,
    'slides_link' : MAX_URL_LEN,
    'speaker': MAX_SPEAKERS*MAX_NAME_LEN, # FIXME once multiple speakers are properly supported
    'speakers' : MAX_SPEAKERS,
    'speaker_affiliation': MAX_SPEAKERS*MAX_NAME_LEN, # FIXME once multiple speakers are properly supported
    'speaker_email': MAX_SPEAKERS*MAX_EMAIL_LEN,
    'speaker_homepage': MAX_SPEAKERS*MAX_URL_LEN,
    'stream_link' : MAX_URL_LEN,
    'time_slots' : MAX_SLOTS,
    'title' : MAX_TITLE_LEN,
    'video_link' : MAX_URL_LEN,
    'weekdays' : MAX_SLOTS,
}


def tba_like(s):
    x = s.replace(' ','').replace('.','').lower()
    return x in ["tba", "tbd", "tobeannounced", "tobedetermined", "unknown", "notknown", "notyetknown"]

def comma_list(items):
    """ return list of stringe as list in English (e.g. [Bill] = Bill, [Bill, Ted] = Bill and Ted, [Bill, Ted, Jane] = Bill, Ted, and Jane) """
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    elif len(items) == 2:
        return items[0] + " and " + items[1]
    else:
        return ', '.join(items[:-1]) + ', and ' + items[-1]

def how_long(delta):
    minute = timedelta(minutes=1)
    if delta < minute:
        return "less than a minute"
    if delta < 90 * minute:
        return "%s minutes" % round(delta / minute)
    if delta < 36 * 60 * minute:
        return "%s hours" % round(delta / (60*minute))
    day = timedelta(days=1)
    if delta < 11 * day:
        return "%s days" % round(delta / day)
    if delta < 7 * 7 * day:
        return "%s weeks" % round(delta / (7*day))
    year = timedelta(days=365.25)
    if delta < 2 * year:
        return "%s months" % round(delta / timedelta(days=30.4))
    return "%s years" % round(delta / year)

def killattr(obj,attr):
    if hasattr(obj,attr):
        delattr(obj,attr)

def domain():
    return urlparse(request.url).netloc

def topdomain():
    return ".".join(domain().split(".")[-2:])

def valid_url(x):
    if not (x.startswith("http://") or x.startswith("https://")):
        return False
    try:
        result = urlparse(x)
        return all([result.scheme, result.netloc])
    except:
        return False

def valid_email(x):
    if not "@" in x:
        return False
    try:
        result = validate_email(x)
        return True if result else False
    except:
        return False

def similar_urls(x,y):
    a, b = urlparse(x), urlparse(y)
    return a[1] == b[1] and (a[2] == b[2] or a[2] == b[2] + "/" or a[2] + "/" == b[2])

def cleanse_dashes(s):
    # replace unicode variants of dashes (which users might cut-and-paste in) with ascii dashes
    return '-'.join(re.split(dash_re,s))

def validate_daytime(s):
    if not daytime_re.fullmatch(s):
        return None
    if len(s) <= 2:
        h, m = int(s), 0
    elif not ":" in s:
        h, m = int(s[:-2]), int(s[-2:])
    else:
        t = s.split(":")
        h, m = int(t[0]), int(t[1])
    return "%02d:%02d" % (h, m) if (0 <= h < 24) and (0 <= m <= 59) else None


def validate_daytimes(s):
    t = s.split('-')
    if len(t) != 2:
        return None
    start, end = validate_daytime(t[0].strip()), validate_daytime(t[1].strip())
    if start is None or end is None:
        return None
    return start + "-" + end


def daytime_minutes(s):
    t = s.split(":")
    return 60 * int(t[0]) + int(t[1])


def daytimes_start_minutes(s):
    return daytime_minutes(s.split('-')[0])

def midnight(date, tz):
    return localize_time(datetime.combine(date, maketime()), tz)

def weekstart(date, tz):
    t = midnight(date,tz)
    return t - timedelta(days=1)*t.weekday()

def date_and_daytime_to_time(date, s, tz):
    d = localize_time(datetime.combine(date, maketime()), tz)
    m = timedelta(minutes=1)
    return d + m * daytime_minutes(s)

def date_and_daytimes_to_times(date, s, tz):
    d = localize_time(datetime.combine(date, maketime()), tz)
    m = timedelta(minutes=1)
    t = s.split("-")
    start = d + m * daytime_minutes(t[0])
    end = d + m * daytime_minutes(t[1])
    if end < start:
        end += timedelta(days=1)
    return start, end


def daytimes_early(s):
    t = s.split("-")
    start, end = daytime_minutes(t[0]), daytime_minutes(t[1])
    return start > end or start < 6 * 60


def daytimes_minutes(s):
    t = s.split('-')
    start, end = daytime_minutes(t[0]), daytime_minutes(t[1])
    length = end - start if end > start else 24*60-start + end
    return length

def daytimes_long(s):
    return daytimes_minutes(s) > 8*60

def make_links(x):
    """ Given a blob of text looks for URLs (beggining with http:// or https://) and makes them hyperlinks. """
    tokens = re.split(r"(\s+)", x)
    for i in range(len(tokens)):
        if valid_url(tokens[i]):
            tokens[i] = '<a href="%s">%s</a>'%(tokens[i], tokens[i][tokens[i].index("//")+2:])
    return ''.join(tokens)

def naive_utcoffset(tz):
    if isinstance(tz, str):
        tz = pytz.timezone(tz)
    for h in range(10):
        try:
            return tz.utcoffset(datetime.now() + timedelta(hours=h))
        except (
            pytz.exceptions.NonExistentTimeError,
            pytz.exceptions.AmbiguousTimeError,
        ):
            pass


def timestamp():
    return "[%s UTC]" % datetime.now(tz=pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")


def log_error(msg):
    from seminars.app import app
    import traceback
    try:
        raise RuntimeError()
    except Exception:
        app.logger.error(timestamp() + " ERROR logged at: " + traceback.format_stack()[-2].split('\n')[0])
        app.logger.error(timestamp() + " ERROR message is:  " + msg)

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


timezones = [
    (v, pretty_timezone(v)) for v in sorted(pytz.common_timezones, key=naive_utcoffset)
]


def is_nighttime(t):
    if t is None:
        return False
    # These are times that might be mixed up by using a 24 hour clock
    return 1 <= t.hour < 6


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
        #(url_for("search_seminars"), "", "Search"),
        (url_for("create.index"), "", manage),
        (url_for("info"), "", "Info"),
        (url_for("user.info"), "", account),
    ]


shortname_re = re.compile("^[A-Za-z0-9_-]+$")


def allowed_shortname(shortname):
    return bool(shortname_re.match(shortname))




@lru_cache(maxsize=None)
def subject_pairs():
    return sorted(
        [
            (rec["subject_id"], rec["name"])
            for rec in db.subjects.search({}, ["subject_id", "name"])
        ],
        key=lambda x: x[1].lower(),
    )

def clean_topics(inp):
    from .topic import topic_dag # avoiding circular import
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
        filled = set(elt for elt in inp if elt in topic_dag.by_id)
        size = 0
        while len(filled) != size:
            size = len(filled)
            for elt in set(filled):
                for supertopic in topic_dag.by_id[elt].parents:
                    filled.add(supertopic.id)
        return sorted(filled)
    return []


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
    include_pending=False,
    more=False,
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
    tbl = IdentifierWrapper(table.search_table)
    nres = count_distinct(table, counter, query)
    if limit is None:
        qstr, values = table._build_query(query, sort=sort)
    else:
        qstr, values = table._build_query(query, limit, offset, sort)
    prequery = {} if include_pending else {'$or': [{'display': True}, {'by_api': False}]}
    if prequery:
        # We filter the records before finding the most recent (normal queries filter after finding the most recent)
        # This is mainly used for setting display=False or display=True
        # We take advantage of the fact that the WHERE clause occurs just after the table name in all of our query constructions
        pqstr, pqvalues = table._parse_dict(prequery)
        if pqstr is not None:
            tbl = tbl + SQL(" WHERE {0}").format(pqstr)
            values = pqvalues + values
    if more is not False: # might empty dictionary
        more, moreval = table._parse_dict(more)
        if more is None:
            more = Placeholder()
            moreval = [True]

        cols = SQL(", ").join(list(map(IdentifierWrapper, search_cols + extra_cols)) + [more])
        extra_cols = extra_cols + ("more",)
        values = moreval + values
    else:
        cols = SQL(", ").join(map(IdentifierWrapper, search_cols + extra_cols))
    fselecter = selecter.format(cols, all_cols, tbl, qstr)
    cur = table._execute(
        fselecter,
        values,
        buffered=(limit is None),
        slow_note=(
            table.search_table,
            "analyze",
            query,
            repr(projection),
            limit,
            offset,
        ),
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
            return search_distinct(
                table,
                selecter,
                counter,
                iterator,
                query,
                projection,
                limit,
                offset,
                sort,
                info,
            )
        info["query"] = dict(query)
        info["number"] = nres
        info["count"] = limit
        info["start"] = offset
        info["exact_count"] = True
    return list(results)


def lucky_distinct(
    table,
    selecter,
    construct,
    query={},
    projection=2,
    offset=0,
    sort=[],
    include_deleted=False,
    include_pending=False,
):
    query = dict(query)
    if not include_deleted:
        query["deleted"] = {"$or": [False, {"$exists": False}]}
    all_cols = SQL(", ").join(map(IdentifierWrapper, ["id"] + table.search_cols))
    search_cols, extra_cols = table._parse_projection(projection)
    cols = SQL(", ").join(map(IdentifierWrapper, search_cols + extra_cols))
    qstr, values = table._build_query(query, 1, offset, sort=sort)
    tbl = table._get_table_clause(extra_cols)
    prequery = {} if include_pending else {'$or': [{'display': True}, {'by_api': False}]}
    if prequery:
        # We filter the records before finding the most recent (normal queries filter after finding the most recent)
        # This is mainly used for setting display=False or display=True
        # We take advantage of the fact that the WHERE clause occurs just after the table name in all of our query constructions
        pqstr, pqvalues = table._parse_dict(prequery)
        if pqstr is not None:
            tbl = tbl + SQL(" WHERE {0}").format(pqstr)
            values = pqvalues + values
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


def adapt_weektimes(weekday, daytimes, oldtz, newtz):
    """
    Converts a weekday in [0,7] and daytimes HH:MM-HH:MM from oldtz to newtz (returns integer in [0,7] and string HH:MM-HH:MM).
    Note that weekday is for the start time, the end time could be the following day (this is implied by end time <= start time)
    """
    if isinstance(oldtz, str):
        oldtz = pytz.timezone(oldtz)
    if isinstance(newtz, str):
        newtz = pytz.timezone(newtz)
    if newtz == oldtz:
        return weekday, daytimes
    oneday = timedelta(days=1)
    oneminute = timedelta(minutes=1)
    start = weekstart(datetime.now(oldtz),oldtz) + weekday*oneday + daytimes_start_minutes(daytimes)*oneminute
    start = adapt_datetime(start, newtz=newtz)
    end = start + daytimes_minutes(daytimes)*oneminute
    return start.weekday(), start.strftime("%H:%M") + "-" + end.strftime("%H:%M")


def process_user_input(inp, col, typ, tz=None):
    """
    INPUT:

    - ``inp`` -- unsanitized input, as a string (or None)
    - ''col'' -- column name (names ending in ''link'', ''page'', ''time'', ''email'' get special handling
    - ``typ`` -- a Postgres type, as a string
    """
    if inp and isinstance(inp, str):
        inp = inp.strip()
    if inp == "":
        return False if typ == "boolean" else ("" if typ == "text" else None)
    if col in maxlength and len(inp) > maxlength[col]:
        raise ValueError("Input exceeds maximum length permitted")
    if typ == "time":
        # Note that parse_time, when passed a time with no date, returns
        # a datetime object with the date set to today.  This could cause different
        # relative orders around daylight savings time, so we store all times
        # as datetimes on Jan 1, 2020.
        if inp.isdigit():
            inp += ":00"  # treat numbers as times not dates
        t = parse_time(inp)
        t = t.replace(year=2020, month=1, day=1)
        assert tz is not None
        return localize_time(t, tz)
    elif (col.endswith("page") or col.endswith("link")) and typ == "text":
        # allow lists of URLs for speakers
        if col.startswith("speaker"):
            urls = [s.strip() for s in inp.split(SPEAKER_DELIMITER)]
            if any([not valid_url(x) for x in urls if x]):
                raise ValueError("Invalid URL")
            return (' ' + SPEAKER_DELIMITER + ' ').join(urls)
        if not valid_url(inp):
            raise ValueError("Invalid URL")
        return inp
    elif col.endswith("email") and typ == "text":
        # allow lists of emails for speakers
        if col.startswith("speaker"):
            emails = [s.strip() for s in inp.split(SPEAKER_DELIMITER)]
            return (' ' + SPEAKER_DELIMITER + ' ').join([(validate_email(x)["email"] if x else '') for x in emails])
        return validate_email(inp)["email"]
    elif typ == "timestamp with time zone":
        assert tz is not None
        return localize_time(parse_time(inp), tz)
    elif typ == "daytime":
        res = validate_daytime(inp)
        if res is None:
            raise ValueError("Invalid time of day, expected format is hh:mm")
        return res
    elif typ == "daytimes":
        inp = cleanse_dashes(inp)
        res = validate_daytimes(inp)
        if res is None:
            raise ValueError("Invalid times of day, expected format is hh:mm-hh:mm")
        return res
    elif typ == "weekday_number":
        res = int(inp)
        if res < 0 or res >= 7:
            raise ValueError("Invalid day of week, must be an integer in [0,6]")
        return res
    elif typ == "date":
        return parse_time(inp).date()
    elif typ == "boolean":
        if inp in ["yes", "true", "y", "t", True]:
            return True
        elif inp in ["no", "false", "n", "f", False]:
            return False
        raise ValueError("Invalid boolean")
    elif typ == "text":
        if col.endswith("timezone"):
            return inp if pytz.timezone(inp) else ""
        # should sanitize somehow?
        return "\n".join(inp.splitlines())
    elif typ in ["int", "smallint", "bigint", "integer"]:
        return int(inp)
    elif typ == "text[]":
        if inp == "":
            return []
        elif isinstance(inp, str):
            if inp[0] == "[" and inp[-1] == "]":
                res = [elt.strip().strip("'") for elt in inp[1:-1].split(",")]
                if res == [""]:  # was an empty array
                    return []
                else:
                    return res
            else:
                # Temporary measure until we incorporate https://www.npmjs.com/package/select-pure (demo: https://www.cssscript.com/demo/multi-select-autocomplete-selectpure/)
                return [inp]
        elif isinstance(inp, Iterable):
            return [str(x) for x in inp]
        else:
            raise ValueError("Unrecognized input")
    else:
        raise ValueError("Unrecognized type %s" % typ)


def format_errmsg(errmsg, *args):
    return Markup(
        "Error: "
        + (
            errmsg
            % tuple("<span style='color:black'>%s</span>" % escape(x) for x in args)
        )
    )


def format_input_errmsg(err, inp, col):
    return format_errmsg(
        "Unable to process input %s for property %s: {0}".format(err),
        '"' + str(inp) + '"',
        col,
    )


def format_warning(warnmsg, *args):
    return Markup(
        "Warning: "
        + (
            warnmsg
            % tuple("<span style='color:red'>%s</span>" % escape(x) for x in args)
        )
    )


def flash_warnmsg(warnmsg, *args):
    flash(format_warning(warnmsg, *args), "warning")

def format_infomsg(infomsg, *args):
    return Markup(infomsg % tuple("<span style='color:black'>%s</span>" % escape(x) for x in args))


def flash_infomsg(infomsg, *args):
    flash(format_infomsg(infomsg, *args), "info")

def show_input_errors(errmsgs):
    """ Flashes a list of specific user input error messages then displays a generic message telling the user to fix the problems and resubmit. """
    assert errmsgs
    for msg in errmsgs:
        flash(msg, "error")
    return render_template("inputerror.html", messages=errmsgs)


def sanity_check_times(start_time, end_time, warn=flash_warnmsg):
    """
    Flashes warnings if time range seems suspsicious.  Note that end_time is (by definition) greater than start_time
    """
    if start_time is None or end_time is None:
        # Users are allowed to not fill in a time
        return
    if start_time > end_time:
        end_time = end_time + timedelta(days=1)
    if start_time + timedelta(hours=8) < end_time:
        warn("Time range exceeds 8 hours, please update if that was unintended.")
    if is_nighttime(start_time) or is_nighttime(end_time):
        warn("Time range includes morning hours before 6am. Please update using 24-hour notation, or specify am/pm, if that was unintentional.")


class Toggle(SearchBox):
    def _input(self, info=None):
        main = toggle(
            tglid="toggle_%s" % self.name,
            name=self.name,
            value=int(info.get(self.name, -1)),
        )
        return '<span style="display: inline-block">%s</span>' % (main,)


def ics_file(talks, filename, user=None):
    if user is None: user = current_user
    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", topdomain())
    cal.add("CALSCALE", "GREGORIAN")
    cal.add("X-WR-CALNAME", topdomain())

    for talk in talks:
        cal.add_component(talk.event(user=user))

    bIO = BytesIO()
    bIO.write(cal.to_ical())
    bIO.seek(0)
    return send_file(
        bIO, attachment_filename=filename, as_attachment=True, add_etags=False
    )

def num_columns(labels):
    if not labels:
        return 1
    mlen = max(len(label) for label in labels)
    # The following are guesses that haven't been tuned much.
    if mlen > 50:
        return 1
    elif mlen > 34:
        return 2
    elif mlen > 20:
        return 3
    elif mlen > 16:
        return 4
    elif mlen > 10:
        return 5
    else:
        return 6

def url_for_with_args(name, args, **kwargs):
    query = ('?' + urlencode(args)) if args else ''
    return url_for(name, **kwargs) + query

# For API calls, we only allow certain columns, both because of deprecated parts of the schema and for privacy/security
whitelisted_cols = [
    "abstract",
    "access_control",
    "access_time",
    "access_hint",
    "access_registration",
    "audience",
    "by_api",
    "chat_link",
    "comments",
    "deleted",
    "deleted_with_seminar",
    "description",
    "display",
    "edited_at",
    "end_date",
    "end_time",
    "frequency",
    "homepage",
    "institutions",
    "is_conference",
    "language",
    #"live_link", # maybe allow searching on this once access control refined
    "name",
    "online",
    "paper_link",
    "per_day",
    "room",
    "seminar_ctr",
    "seminar_id",
    "shortname",
    "slides_link",
    "speaker",
    "speaker_affiliation",
    "speaker_email",
    "speaker_homepage",
    "start_date",
    "start_time",
    "stream_link",
    "time_slots",
    "timezone",
    "title",
    "topics",
    "video_link",
    "visibility",
    "weekdays",
]

class APIError(Exception):
    def __init__(self, error={}, status=400):
        self.error = error
        self.status = status

@lru_cache(maxsize=None)
def sanitized_table(name):
    cur = db._execute(SQL(
        "SELECT name, label_col, sort, count_cutoff, id_ordered, out_of_order, "
        "has_extras, stats_valid, total, include_nones FROM meta_tables WHERE name=%s"
    ), [name])
    def update(self, query, changes, resort=False, restat=False, commit=True):
        raise APIError({"code": "update_prohibited"})
    def insert_many(self, data, resort=False, reindex=False, restat=False, commit=True):
        raise APIError({"code": "insert_prohibited"})
    # We remove the raw argument from search and lucky keywords since these allow the execution of arbitrary SQL
    def search(self, *args, **kwds):
        kwds.pop("raw", None)
        return PostgresSearchTable.search(self, *args, **kwds)
    def lucky(self, *args, **kwds):
        kwds.pop("raw", None)
        return PostgresSearchTable.lucky(self, *args, **kwds)
    from seminars import count
    table = PostgresSearchTable(db, *cur.fetchone())
    table.update = update.__get__(table)
    table.count = count.__get__(table)
    table.search = search.__get__(table)
    table.lucky = lucky.__get__(table)
    table.insert_many = insert_many.__get__(table)
    table.search_cols = [col for col in table.search_cols if col in whitelisted_cols]
    table.col_type = {col: typ for (col, typ) in table.col_type.items() if col in whitelisted_cols}
    return table

