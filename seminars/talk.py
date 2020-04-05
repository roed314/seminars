
import pytz, datetime, random
from urllib.parse import urlencode, quote
from flask import url_for, redirect, render_template
from flask_login import current_user
from seminars import db
from seminars.utils import search_distinct, lucky_distinct, count_distinct, max_distinct
from seminars.seminar import WebSeminar, can_edit_seminar, seminars_lookup
from lmfdb.utils import flash_error
from markupsafe import Markup
from psycopg2.sql import SQL

class WebTalk(object):
    def __init__(self, semid=None, semctr=None, data=None, seminar=None, editing=False, showing=False, saving=False):
        if data is None and not editing:
            data = talks_lookup(semid, semctr)
            if data is None:
                raise ValueError("Talk %s/%s does not exist" % (semid, semctr))
            data = dict(data.__dict__)
        if seminar is None:
            seminar = WebSeminar(semid)
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
        return "%s (%s) - %s, %s" % (title, self.speaker, self.show_date(), self.show_start_time())

    def __eq__(self, other):
        return (isinstance(other, WebTalk) and
                all(getattr(self, key, None) == getattr(other, key, None) for key in db.talks.search_cols))

    def __ne__(self, other):
        return not (self == other)

    def save(self):
        assert self.__dict__.get('seminar_id') and self.__dict__.get('seminar_ctr')
        db.talks.insert_many([{col: getattr(self, col, None) for col in db.talks.search_cols}])

    def show_start_time(self):
        return self.start_time.astimezone(current_user.tz).strftime("%-H:%M")

    def show_end_time(self):
        # This is used in show_time_and_duration, and needs to include the ending date if different (might not be the same in current user's time zone)
        t0 = self.start_time.astimezone(current_user.tz)
        t = self.end_time.astimezone(current_user.tz)
        if t0.date() == t.date():
            return t.strftime("%-H:%M")
        else:
            return t.strftime("%a %b %-d, %-H:%M")

    def show_time_link(self):
        return '<a href="%s">%s</a>' % (url_for("show_talk", semid=self.seminar_id, talkid=self.seminar_ctr), self.show_start_time())

    def show_date(self):
        return self.start_time.astimezone(current_user.tz).strftime("%a %b %-d")

    def show_date_link(self):
        return '<a href="%s">%s</a>' % (url_for("show_talk", semid=self.seminar_id, talkid=self.seminar_ctr), self.show_date())

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
                start.astimezone(current_user.tz).strftime("%a %b %-d, %-H:%M"),
                end.astimezone(current_user.tz).strftime("%-H:%M"),
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
                return ans("%s days from now" % (round(until / day)))
            elif until < 7*week:
                return ans("%s weeks from now" % (round(until / week)))
            elif until < 2*year:
                return ans("%s months from now" % (round(until / month)))
            else:
                return ans("%s years from now" % (round(until / year)))
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

    def show_title(self):
        return self.title if self.title else "TBA"

    def show_knowl_title(self):
        print(Markup(render_template('talk-knowl.html', talk=self)))
        return r'<a title="{title}" knowl="dynamic_show" kwargs="{content}">{title}</a>'.format(
            title=self.show_title(),
            content=Markup.escape(render_template('talk-knowl.html', talk=self))
        )
    def show_seminar(self):
        return self.seminar.show_name()

    def show_speaker(self):
        # As part of a list
        ans = ""
        if self.speaker:
            if self.speaker_homepage:
                ans += '<a href="%s">%s</a>' % (self.speaker_homepage, self.speaker)
            else:
                ans += self.speaker
            if self.speaker_affiliation:
                ans += " (%s)" % (self.speaker_affiliation)
        return ans

    def show_speaker_and_seminar(self):
        # On homepage
        ans = ""
        if self.speaker:
            ans += "by " + self.show_speaker()
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

    def edit_link(self):
        return '<a href="%s">Edit</a>' % url_for("create.edit_talk", seminar_id=self.seminar_id, seminar_ctr=self.seminar_ctr)

    def show_subscribe(self):
        return ""

    def oneline(self, include_seminar=True):
        cols = []
        if not include_seminar and (current_user.is_admin() or current_user.email in self.seminar.editors()):
            cols.append(self.edit_link())
        cols.append(self.show_date_link())
        cols.append(self.show_time_link())
        if include_seminar:
            cols.append(self.show_seminar())
        cols.append(self.show_speaker())
        cols.append(self.show_title())
        return "".join("<td>%s</td>" % c for c in cols)

    def split_abstract(self):
        return self.abstract.split("\n\n")

    def speaker_link(self):
        return "https://mathseminars.org/edit/talk/%s/%s/%s" % (self.seminar_id, self.seminar_ctr, self.token)

    def send_speaker_link(self):
        """
        Creates a mailto link with instructions on editing the talk.
        """
        data = {'body': "Dear %s,\nYou can edit your upcoming talk using the the following link: %s.\n\nYours,\n%s" % (self.speaker, self.speaker_link(), current_user.name),
                'subject': "%s: title and abstract" % self.seminar.name}
        email_to = self.speaker_email if self.speaker_email else ''
        return 'or <a href="mailto:%s?%s">email speaker a link</a>' % (email_to, urlencode(data, quote_via=quote))

def can_edit_talk(seminar_id, seminar_ctr, token):
    """
    INPUT:

    - ``seminar_id`` -- the identifier of the seminar
    - ``seminar_ctr`` -- an integer as a string, or the empty string (for new talk)
    - ``token`` -- a string (allows editing by speaker who might not have account)

    OUTPUT:

    - ``resp`` -- a response to return to the user (indicating an error) or None (editing allowed)
    - ``seminar`` -- a WebSeminar object, as returned by ``seminars_lookup(seminar_id)``
    - ``talk`` -- a WebTalk object, as returned by ``talks_lookup(seminar_id, seminar_ctr)``,
                  or ``None`` (if error or talk does not exist)
    """
    new = not seminar_ctr
    if seminar_ctr:
        try:
            seminar_ctr = int(seminar_ctr)
        except ValueError:
            flash_error("Invalid talk id")
            return redirect(url_for("show_seminar", shortname=seminar_id), 301), None, None
    if token and seminar_ctr != "":
        talk = talks_lookup(seminar_id, seminar_ctr)
        if talk is None:
            flash_error("Talk does not exist")
            return redirect(url_for("show_seminar", shortname=seminar_id), 301), None, None
        elif token != talk.token:
            flash_error("Invalid token for editing talk")
            return redirect(url_for("show_talk", semid=seminar_id, talkid=seminar_ctr), 301), None, None
        seminar = seminars_lookup(seminar_id)
    else:
        resp, seminar = can_edit_seminar(seminar_id, new=False)
        if resp is not None:
            return resp, None, None
        if seminar.new:
            # TODO: This is where you might insert the ability to create a talk without first making a seminar
            flash_error("You must first create the seminar %s" % seminar_id)
            return redirect(url_for("edit_seminar", shortname=seminar_id), 301)
        if new:
            talk = WebTalk(seminar_id, seminar=seminar, editing=True)
        else:
            talk = WebTalk(seminar_id, seminar_ctr, seminar=seminar)
    return None, seminar, talk

_selecter = SQL("SELECT {0} FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {0} FROM {1} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{2}")
_counter = SQL("SELECT COUNT(*) FROM (SELECT 1 FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {0} FROM {1} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{2}) tmp2")
_maxer = SQL("SELECT MAX({0}) FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {1} FROM {2} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{3}")
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
    Replacement for db.talks.count to account for versioning and so that we don't cache results.
    """
    return count_distinct(db.talks, _counter, query)

def talks_max(col, constraint={}):
    """
    Replacement for db.talks.max to account for versioning and so that we don't cache results.
    """
    return max_distinct(db.talks, _maxer, col, constraint)

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
