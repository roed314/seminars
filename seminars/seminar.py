
import re
from flask_login import current_user
from seminars import db
from seminars.utils import search_distinct, lucky_distinct, count_distinct
from psycopg2.sql import SQL

shortname_re = re.compile("^[A-Za-z0-9_-]+$")
def allowed_shortname(shortname):
    return bool(shortname_re.match(shortname))

def is_locked(shortname):
    pass

def set_locked(shortname):
    pass

class WebSeminar(object):
    def __init__(self, shortname, data=None, editing=False, showing=False, saving=False):
        if data is None and not editing:
            data = seminars_lucky({'shortname': shortname}, projection=3)
            if data is None:
                raise ValueError("Seminar %s does not exist" % shortname)
            data = dict(data.__dict__)
        if data is None:
            self.shortname = shortname
            self.display = current_user.is_creator()
            self.online = True # default
            self.archived = False # don't start out archived
            self.is_conference = False # seminar by default
            for key, typ in db.seminars.col_type.items():
                if key in ['id', 'shortname', 'display', 'online', 'archived', 'is_conference']:
                    continue
                elif typ == 'text':
                    setattr(self, key, '')
                elif typ == 'text[]':
                    setattr(self, key, [])
                else:
                    raise ValueError("Need to update seminar code to account for schema change")
        else:
            self.__dict__.update(data)

    def __repr__(self):
        return self.name

    def save(self):
        db.seminars.insert_many([{col: getattr(self, col, None) for col in db.seminars.search_columns}])

_selecter = SQL("SELECT {0} FROM (SELECT DISTINCT ON (shortname) {0} FROM {1} ORDER BY shortname, id DESC) tmp{2}")
_counter = SQL("SELECT COUNT(*) FROM (SELECT 1 FROM (SELECT DISTINCT ON (shortname) {0} FROM {1} ORDER BY shortname, id DESC) tmp{2}) tmp2")
def _construct(rec):
    if isinstance(rec, str):
        return rec
    else:
        return WebSeminar(rec['shortname'], data=rec)
def _iterator(cur, search_cols, extra_cols, projection):
    for rec in db.seminars._search_iterator(cur, search_cols, extra_cols, projection):
        yield _construct(rec)

def seminars_count(query={}):
    """
    Replacement for db.seminars.count to account for versioning.
    """
    return count_distinct(db.seminars, _counter, query)

def seminars_search(*args, **kwds):
    """
    Replacement for db.seminars.search to account for versioning, return WebSeminar objects.

    Doesn't support split_ors or raw.  Always computes count.
    """
    return search_distinct(db.seminars, _selecter, _counter, _iterator, *args, **kwds)

def seminars_lucky(*args, **kwds):
    """
    Replacement for db.seminars.lucky to account for versioning, return a WebSeminar object or None.
    """
    return lucky_distinct(db.seminars, _selecter, _construct, *args, **kwds)
