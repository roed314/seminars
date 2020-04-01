
from flask import url_for
from seminars import db
from seminars.utils import search_distinct, lucky_distinct, count_distinct
from psycopg2.sql import SQL

class WebTalk(object):
    def __init__(self, semid=None, semctr=None, data=None, editing=False, showing=False, saving=False):
        if data is None:
            data = db.talks.lucky({'seminar_id': semid, 'seminar_ctr': semctr})
            if data is None:
                raise ValueError("Seminar %s/%s does not exist" % (semid, semctr))
        self.__dict__.update(data)

    def __repr__(self):
        title = self.title if self.title else "TBA"
        return "%s (%s) - %s" % (title, self.speaker, self.show_time())

    def show_time(self):
        return self.start_time.strftime("%a %b %-d, %-H:%M")

    def show_seminar(self):
        return '<a href="%s">%s</a>' % (url_for("show_seminar", shortname=self.seminar_id), self.seminar_name)

    def show_speaker(self):
        return '<a href="%s">%s</a>' % (url_for("show_talk", semid=self.seminar_id, talkid=self.seminar_ctr), self.speaker)

    def oneline(self, include_seminar=True):
        cols = [self.show_time()]
        if include_seminar:
            cols.append(self.show_seminar())
        cols.append(self.show_speaker())
        cols.append(self.title)
        return "".join("<td>%s</td>" % c for c in cols)

    def split_abstract(self):
        return self.abstract.split("\n\n")


_selecter = SQL("SELECT {0} FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {0} FROM {1} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{2}")
_counter = SQL("SELECT COUNT(*) FROM (SELECT 1 FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {0} FROM {1} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{2}) tmp2")
def _construct(rec):
    if isinstance(rec, str):
        return rec
    else:
        return WebTalk(rec['seminar_id'], rec['seminar_ctr'], data=rec)
def _iterator(cur, search_cols, extra_cols, projection):
    for rec in db.talks._search_iterator(cur, search_cols, extra_cols, projection):
        yield _construct(rec)

def talks_count(query={}):
    """
    Replacement for db.talks.count to account for versioning.
    """
    return count_distinct(db.talks, _counter, query)

def talks_search(*args, **kwds):
    """
    Replacement for db.talks.search to account for versioning, return WebTalk objects.

    Doesn't support split_ors or raw.  Always computes count.
    """
    return search_distinct(db.talks, _selecter, _counter, _iterator, *args, **kwds)

def talks_lucky(*args, **kwds):
    """
    Replacement for db.talks.lucky to account for versioning, return a WebTalk object or None.
    """
    return lucky_distinct(db.talks, _selecter, _construct, *args, **kwds)
