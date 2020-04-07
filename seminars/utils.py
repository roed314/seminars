from datetime import datetime, timedelta, time
from dateutil.parser import parse as parse_time
import pytz, re
from six import string_types
from flask import url_for, flash
from flask_login import current_user
from seminars import db
from sage.misc.cachefunc import cached_function
from lmfdb.backend.utils import IdentifierWrapper
from lmfdb.utils import flash_error
from psycopg2.sql import SQL
from markupsafe import Markup, escape

weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def naive_utcoffset(tz):
    for h in range(10):
        try:
            return pytz.timezone(tz).utcoffset(datetime.now() + timedelta(hours=h))
        except (pytz.exceptions.NonExistentTimeError, pytz.exceptions.AmbiguousTimeError):
            pass

def pretty_timezone(tz):
    foo = naive_utcoffset(tz)
    hours, remainder = divmod(int(foo.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours < 0:
        diff = '{:03d}:{:02d}'.format(hours, minutes)
    else:
        diff = '+{:02d}:{:02d}'.format(hours, minutes)
    return "(GMT {}) {}".format(diff, tz)

timezones = [(v, pretty_timezone(v)) for v in sorted(pytz.common_timezones, key=naive_utcoffset)]

def is_nighttime(t):
    # These are times that might be mixed up by using a 24 hour clock
    return 1 <= t.hour < 8

def flash_warning(warnmsg, *args):
    flash(Markup("Warning: " + (warnmsg % tuple("<span style='color:black'>%s</span>" % escape(x) for x in args))), "error")

def check_time(start_time, end_time):
    """
    Flashes errors/warnings and returns True when an error should be raised.
    """
    if start_time > end_time:
        if is_nighttime(end_time):
            flash_error("Your start time is after your end time; perhaps you forgot pm")
        else:
            flash_error("Your start time is after your end time")
        return True
    if is_nighttime(start_time) or is_nighttime(end_time):
        flash_warning("Your seminar is scheduled between midnight and 8am; if that was unintentional you should edit again using 24-hour notation or including pm")

def top_menu():
    if current_user.is_authenticated:
        account = "Account"
    else:
        account = "Login"
    return [
        (url_for("index"), "", "Browse"),
        (url_for("search"), "", "Search"),
        (url_for("create.index"), "", "Create"),
        (url_for("info"), "", "Info"),
        (url_for("user.info"), "", account)
    ]

shortname_re = re.compile("^[A-Za-z0-9_-]+$")
def allowed_shortname(shortname):
    return bool(shortname_re.match(shortname))

# Note the caching: if you add a category you have to restart the server
@cached_function
def categories():
    return sorted(((rec["abbreviation"], rec["name"]) for rec in db.categories.search({}, ["abbreviation", "name"])), key=lambda x: x[1].lower())

@cached_function
def category_dict():
    return dict(categories())

def count_distinct(table, counter, query={}):
    cols = SQL(", ").join(map(IdentifierWrapper, table.search_cols))
    tbl = IdentifierWrapper(table.search_table)
    qstr, values = table._build_query(query, sort=[])
    counter = counter.format(cols, tbl, qstr)
    cur = table._execute(counter, values)
    return int(cur.fetchone()[0])

def max_distinct(table, maxer, col, constraint={}):
    # Note that this will return None for the max of an empty set
    cols = SQL(", ").join(map(IdentifierWrapper, table.search_cols))
    tbl = IdentifierWrapper(table.search_table)
    qstr, values = table._build_query(constraint, sort=[])
    maxer = maxer.format(IdentifierWrapper(col), cols, tbl, qstr)
    cur = table._execute(maxer, values)
    return cur.fetchone()[0]

def search_distinct(table, selecter, counter, iterator, query={}, projection=1, limit=None, offset=0, sort=None, info=None):
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
    search_cols, extra_cols = table._parse_projection(projection)
    cols = SQL(", ").join(map(IdentifierWrapper, search_cols + extra_cols))
    tbl = IdentifierWrapper(table.search_table)
    nres = count_distinct(table, counter, query)
    if limit is None:
        qstr, values = table._build_query(query, sort=sort)
    else:
        qstr, values = table._build_query(query, limit, offset, sort)
    selecter = selecter.format(cols, tbl, qstr)
    cur = table._execute(
        selecter,
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

def lucky_distinct(table, selecter, construct, query={}, projection=2, offset=0, sort=[]):
    search_cols, extra_cols = table._parse_projection(projection)
    cols = SQL(", ").join(map(IdentifierWrapper, search_cols + extra_cols))
    qstr, values = table._build_query(query, 1, offset, sort=sort)
    tbl = table._get_table_clause(extra_cols)
    selecter = selecter.format(cols, tbl, qstr)
    cur = table._execute(selecter, values)
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
    t = t.replace(tzinfo=None)
    if weekday is None:
        days_ahead = 0 if now.time() <= t else 1
    else:
        days_ahead = weekday - now.weekday()
        if days_ahead < 0 or (days_ahead == 0 and now.time() > t):
            days_ahead += 7
    next_t = datetime.combine(now.date() + timedelta(days=days_ahead), t)
    next_t = adapt_datetime(next_t, newtz)
    if weekday is None:
        return None, next_t.time()
    else:
        return next_t.weekday(), next_t.time()

def process_user_input(inp, typ, tz):
    """
    INPUT:

    - ``inp`` -- unsanitized input, as a string
    - ``typ`` -- a Postgres type, as a string
    """
    if inp is None:
        return None
    if typ == 'timestamp with time zone':
        # Need to sanitize more, include time zone
        return localize_time(parse_time(inp), tz)
    elif typ == 'time with time zone':
        return localize_time(parse_time(inp), tz)
    elif typ == 'boolean':
        if inp in ['yes', 'true', 'y', 't']:
            return True
        elif inp in ['no', 'false', 'n', 'f']:
            return False
        raise ValueError
    elif typ == 'text':
        # should sanitize somehow?
        return inp
    elif typ in ['int', 'smallint', 'bigint', 'integer']:
        return int(inp)
    elif typ == 'text[]':
        # Temporary measure until we incorporate https://www.npmjs.com/package/select-pure (demo: https://www.cssscript.com/demo/multi-select-autocomplete-selectpure/)
        return [inp]
    else:
        raise ValueError("Unrecognized type %s" % typ)

