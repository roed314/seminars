from datetime import datetime, timedelta
import pytz, re
from six import string_types
from flask import url_for
from flask_login import current_user
from seminars import db
from sage.misc.cachefunc import cached_function
from lmfdb.backend.utils import IdentifierWrapper
from psycopg2.sql import SQL

def naive_utcoffset(tz):
    for h in range(10):
        try:
            return pytz.timezone(tz).utcoffset(datetime.now() + timedelta(hours=h))
        except pytz.exceptions.NonExistentTimeError:
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

def basic_top_menu():
    if current_user.is_authenticated:
        account = "Account"
    else:
        account = "Login"
    return [
        (url_for("index"), "", "Browse"),
        (url_for("search"), "", "Search"),
        (url_for("subscribe"), "", "Subscribe"),
        (url_for("create.index"), "", "Create"),
        (url_for("about"), "", "About"),
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
        qstr, values = self._build_query(query, limit, offset, sort)
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

def process_user_input(inp, typ, lookup={}):
    """
    INPUT:

    - ``inp`` -- unsanitized input, as a string
    - ``typ`` -- a Postgres type, as a string
    """
    if inp is None:
        return None
    if typ == 'timestamp with time zone':
        # Need to sanitize more, include time zone
        return datetime.strptime(inp, "%Y-%m-%d-%H:%M")
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
    elif typ == 'bigint[]':
        # Again, temporary
        return [lookup.get(inp)]
    else:
        raise ValueError("Unrecognized type %s" % typ)

