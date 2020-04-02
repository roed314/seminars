
import pytz, datetime, random
from flask import url_for
from flask_login import current_user
from seminars import db
from seminars.utils import search_distinct, lucky_distinct, count_distinct
from seminars.seminar import WebSeminar
from psycopg2.sql import SQL

class WebTalk(object):
    def __init__(self, semid=None, semctr=None, data=None, seminar=None, editing=False, showing=False, saving=False):
        if data is None and not editing:
            data = talks_lookup(semid, semctr)
            if data is None:
                raise ValueError("Talk %s/%s does not exist" % (semid, semctr))
            data = dict(data.__dict__)
        if seminar is None:
            seminar = WebSeminar(semid, organizer_data=[]) # don't need organizers
        self.seminar = seminar
        self.new = (data is None)
        if self.new:
            self.seminar_id = semid
            self.seminar_ctr = None
            self.token = '%016x' % random.randrange(16**16)
            self.display = current_user.is_creator()
            self.online = getattr(seminar, 'online', bool(getattr(seminar, 'live_link')))
            self.deleted=False
            for key, typ in db.talks.col_type.items():
                if key == 'id' or hasattr(self, key):
                    continue
                elif db.seminars.col_type.get(key) == typ and getattr(seminar, key, None) and key != "description":
                    # carry over from seminar
                    setattr(self, key, getattr(seminar, key))
                elif typ == 'text':
                    setattr(self, key, '')
                elif typ == 'text[]':
                    setattr(self, key, [])
                elif typ == 'timestamp with time zone':
                    setattr(self, key, None)
                else:
                    raise ValueError("Need to update talk code to account for schema change")
        else:
            self.__dict__.update(data)

    def __repr__(self):
        title = self.title if self.title else "TBA"
        return "%s (%s) - %s" % (title, self.speaker, self.show_time())

    def show_time(self):
        return self.start_time.strftime("%a %b %-d, %-H:%M")

    def show_time_and_duration(self):
        start = self.start_time
        end = self.end_time
        now = datetime.datetime.now(pytz.utc)
        delta = datetime.timedelta
        minute = delta(minutes=1)
        hour = delta(hours=1)
        day = delta(days=1)
        week = delta(weeks=1)
        month = delta(days=30.4)
        year = delta(days=365)
        def ans(rmk):
            return '<span class="localtime" data-utcoffset="%s">%s-%s</span> (%s)' % (
                int(start.utcoffset().total_seconds() / 60),
                start.strftime("%a %b %-d, %-H:%M"),
                end.strftime("%-H:%M"),
                rmk)
        # Add remark on when this is
        if start <= now <= end:
            return ans("ongoing")
        elif now < start:
            until = start - now
            if until < minute:
                return ans("starts in less than a minute")
            elif until < 90*minute:
                return ans("starts in %s minutes" % (round(until / minute)))
            elif until < 36*hour:
                return ans("starts in %s hours" % (round(until / hour)))
            elif until < 11*day:
                return ans("starts in %s days" % (round(until / day)))
            elif until < 7*week:
                return ans("starts in %s weeks" % (round(until / week)))
            elif until < 2*year:
                return ans("starts in %s months" % (round(until / month)))
            else:
                return ans("starts in %s years" % (round(until / year)))
        else:
            ago = now - end
            if ago < minute:
                return ans("ended less than a minute ago")
            elif ago < 90*minute:
                return ans("ended %s minutes ago" % (round(ago / minute)))
            elif ago < 36*hour:
                return ans("ended %s hours ago" % (round(ago / hour)))
            elif ago < 11*day:
                return ans("%s days ago" % (round(ago / day)))
            elif ago < 7*week:
                return ans("%s weeks ago" % (round(ago / week)))
            elif ago < 2*year:
                return ans("%s months ago" % (round(ago / month)))
            else:
                return ans("%s years ago" % (round(ago / year)))

    def show_seminar(self):
        # Link to seminar
        return '<a href="%s">%s</a>' % (url_for("show_seminar", shortname=self.seminar_id), self.seminar.name)

    def show_speaker(self):
        # As part of a list
        return '<a href="%s">%s</a>' % (url_for("show_talk", semid=self.seminar_id, talkid=self.seminar_ctr), self.speaker)

    def show_speaker_and_seminar(self):
        # On homepage
        ans = ""
        print(self.speaker_affiliation, self.seminar_id, self.seminar.name)
        if self.speaker:
            ans += "by " + self.speaker
            if self.speaker_affiliation:
                ans += " (%s)" % (self.speaker_affiliation)
        if self.seminar.name:
            ans += " as part of %s" % (self.show_seminar())
        return ans

    def show_live_link(self):
        if not self.live_link:
            return ""
        success = 'Access <a href="%s">online</a>.' % self.live_link
        if self.access == "open":
            return success
        elif self.access == "users":
            if current_user.is_authenticated:
                return success
            else:
                return 'To see access link, please <a href="%s">log in</a> (anti-spam measure).' % (url_for('user.info'))
        elif self.access == "endorsed":
            if current_user.is_creator():
                return success
            else:
                # TODO: add link to an explanation of endorsement
                return 'To see access link, you must be endorsed by another user.'
        else: # should never happen
            return ""

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

def talks_lookup(seminar_id, seminar_ctr, projection=3):
    return talks_lucky({'seminar_id': seminar_id, 'seminar_ctr': seminar_ctr}, projection=projection)
