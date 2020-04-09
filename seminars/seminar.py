
from flask import redirect, url_for
from flask_login import current_user
from seminars import db
from seminars.utils import search_distinct, lucky_distinct, count_distinct, max_distinct, allowed_shortname, topic_dict, weekdays, adapt_weektime, toggle
from lmfdb.utils import flash_error
from lmfdb.backend.utils import DelayCommit
from psycopg2.sql import SQL
import pytz


class WebSeminar(object):
    def __init__(self, shortname, data=None, organizer_data=None, editing=False, showing=False, saving=False):
        if data is None and not editing:
            data = seminars_lookup(shortname)
            if data is None:
                raise ValueError("Seminar %s does not exist" % shortname)
            data = dict(data.__dict__)
        self.new = (data is None)
        if self.new:
            self.shortname = shortname
            self.display = current_user.is_creator()
            self.online = True # default
            self.access = "open" # default
            self.archived = False # don't start out archived
            self.is_conference = False # seminar by default
            self.frequency = 7
            self.weekday = self.start_time = self.end_time = None
            self.timezone = str(current_user.tz)
            for key, typ in db.seminars.col_type.items():
                if key == 'id' or hasattr(self, key):
                    continue
                elif typ == 'text':
                    setattr(self, key, '')
                elif typ == 'text[]':
                    setattr(self, key, [])
                else:
                    raise ValueError("Need to update seminar code to account for schema change")
            if organizer_data is None:
                organizer_data = [{'seminar_id': self.shortname,
                                   'email': current_user.email,
                                   'full_name': current_user.name,
                                   'order': 0,
                                   'curator': True,
                                   'display': False,
                                   'contact': False}]
        else:
            self.__dict__.update(data)
        if organizer_data is None:
            organizer_data = list(db.seminar_organizers.search({'seminar_id': self.shortname}, sort=['order']))
        self.organizer_data = organizer_data

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        # Note that equality ignores organizers
        return (isinstance(other, WebSeminar) and
                all(getattr(self, key, None) == getattr(other, key, None) for key in db.seminars.search_cols))

    def __ne__(self, other):
        return not (self == other)

    def save(self):
        assert self.__dict__.get('shortname')
        db.seminars.insert_many([{col: getattr(self, col, None) for col in db.seminars.search_cols}])

    def save_organizers(self):
        # Need to allow for deleting organizers, so we delete them all then add them back
        with DelayCommit(db):
            db.seminar_organizers.delete({'seminar_id': self.shortname})
            db.seminar_organizers.insert_many(self.organizer_data)

    def show_topics(self):
        if self.topics:
            return " (" + ", ".join(topic_dict()[topic] for topic in self.topics) + ")"
        else:
            return ""

    def show_name(self, external=False):
        # Link to seminar
        kwargs = {'shortname': self.shortname}
        if external:
            kwargs['_external'] = True
            kwargs['_scheme'] = 'https'
        return '<a href="%s">%s</a>' % (url_for("show_seminar", **kwargs), self.name)

    def show_description(self):
        return self.description

    def is_subscribed(self):
        if current_user.is_anonymous():
            return False
        return self.shortname in current_user.seminar_subscriptions

    def show_subscribe(self):
        if current_user.is_anonymous():
            return ""

        return toggle(tglid="tlg" + self.shortname,
                      value=self.shortname,
                      checked=self.is_subscribed(),
                      classes="subscribe")

    def show_institutions(self):
        if self.institutions:
            links = []
            for rec in db.institutions.search({'shortname': {'$in': self.institutions}},
                                              ['shortname', 'name', 'homepage'], sort=['name']):
                if rec['homepage']:
                    links.append('<a href="%s">%s</a>' % (rec['homepage'], rec['name']))
                else:
                    links.append(rec['name'])
            return "/".join(links)
        else:
            return ""

    @property
    def tz(self):
        return pytz.timezone(self.timezone)

    def show_day(self, truncate=True):
        if self.weekday is None:
            return ""
        elif self.start_time is None:
            d = weekdays[self.weekday]
        else:
            d = weekdays[adapt_weektime(self.start_time, self.tz, weekday=self.weekday)[0]]
        if truncate:
            return d[:3]
        else:
            return d

    def _show_time(self, t, adapt):
        if t:
            if adapt and self.weekday:
                t = adapt_weektime(t, self.tz, weekday=self.weekday)[1]
            return t.strftime("%-H:%M")
        else:
            return ""

    def show_start_time(self, adapt=True):
        return self._show_time(self.start_time, adapt)

    def show_end_time(self, adapt=True):
        return self._show_time(self.end_time, adapt)

    def show_weektime_and_duration(self, adapt=True):
        s = self.show_day(truncate=False)
        if s:
            s += ", "
        s += self.show_start_time(adapt=adapt)
        if self.start_time and self.end_time:
            s += "-" + self.show_end_time(adapt=adapt)
        return s

    def oneline(self, include_institutions=True, include_datetime=True, include_description=True, include_subscribe=True):
        cols = []
        if include_datetime:
            cols.append(('class="day"', self.show_day()))
            cols.append(('class="time"', self.show_start_time()))
        if include_institutions:
            cols.append(('class="institution"', self.show_institutions()))
        cols.append(('class="name"', self.show_name()))
        if include_description:
            cols.append(('class="description"', self.show_description()))
        if include_subscribe:
            cols.append(('class="subscribe"', self.show_subscribe()))
        return "".join("<td %s>%s</td>" % c for c in cols)

    def editors(self):
        return [rec['email'] for rec in self.organizer_data]

    def user_can_edit(self):
        # Check whether the current user can edit the seminar
        # See can_edit_seminar for another permission check
        # that takes a seminar's shortname as an argument
        # and returns various error messages if not editable
        return (current_user.is_admin() or
                current_user.email_confirmed and
                current_user.email in self.editors())

    def _show_editors(self, label, negate=False):
        editors = []
        for rec in self.organizer_data:
            show = rec['curator']
            if negate:
                show = not show
            if show and rec['display']:
                name = rec['full_name']
                if not name:
                    if not rec['contact']: continue
                    name = rec['email']
                if rec['contact']:
                    editors.append('<a href="mailto:%s">%s</a>' % (rec['email'], name))
                else:
                    editors.append(name)
        if editors:
            return "<tr><td>%s:</td><td>%s</td></tr>" % (label, ", ".join(editors))
        else:
            return ""

    def show_organizers(self):
        return self._show_editors("Organizers", negate=True)

    def show_curators(self):
        return self._show_editors("Curators")

    def add_talk_link(self, ptag=True):
        if current_user.email in self.editors():
            s ='<a href="%s">Add talk</a>' % url_for("create.edit_talk", seminar_id=self.shortname)
            if ptag:
                s = '<p>%s</p>' % s
            return s
        else:
            return ''

    def show_input_time(self, time):
        if not time:
            return ""
        return time.strftime("%-H:%M")

    def talks(self):
        from seminars.talk import talks_search # avoid import loop
        return talks_search({'seminar_id': self.shortname})



def seminars_header(include_time=True, include_institutions=True, include_description=True, include_subscribe=True):
    cols = []
    if include_time:
        cols.append((2, "Time"))
    if include_institutions:
        cols.append((1, "Institutions"))
    cols.append((1, "Name"))
    if include_description:
        cols.append((1, "Description"))
    if include_subscribe:
        if current_user.is_anonymous():
            cols.append((1, ""))
        else:
            cols.append((1, "Saved"))
    return "".join('<th colspan="%s">%s</th>' % pair for pair in cols)

_selecter = SQL("SELECT {0} FROM (SELECT DISTINCT ON (shortname) {0} FROM {1} ORDER BY shortname, id DESC) tmp{2}")
_counter = SQL("SELECT COUNT(*) FROM (SELECT 1 FROM (SELECT DISTINCT ON (shortname) {0} FROM {1} ORDER BY shortname, id DESC) tmp{2}) tmp2")
_maxer = SQL("SELECT MAX({0}) FROM (SELECT DISTINCT ON (shortname) {1} FROM {2} ORDER BY shortname, id DESC) tmp{3}")
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

def seminars_max(col, constraint={}):
    return max_distinct(db.seminars, _maxer, col, constraint)

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

def seminars_lookup(shortname, projection=3, label_col='shortname'):
    return seminars_lucky({label_col: shortname}, projection=projection)

def can_edit_seminar(shortname, new):
    """
    INPUT:

    - ``shortname`` -- the identifier of the seminar
    - ``new`` -- a boolean, whether the seminar is supposedly newly created

    OUTPUT:

    - ``resp`` -- a response to return to the user (indicating an error) or None (editing allowed)
    - ``seminar`` -- a WebSeminar object, as returned by ``seminars_lookup(shortname)``,
                     or ``None`` (if error or seminar does not exist)
    """
    if not allowed_shortname(shortname):
        flash_error("The identifier must be nonempty and can include only letters, numbers, hyphens and underscores.")
        return redirect(url_for(".index"), 301), None
    seminar = seminars_lookup(shortname)
    # Check if seminar exists
    if new != (seminar is None):
        flash_error("Identifier %s %s" % (shortname, "already exists" if new else "does not exist"))
        return redirect(url_for(".index"), 301), None
    if current_user.is_anonymous(): # can happen via talks, which don't check for logged in in order to support tokens
        flash_error("You do not have permission to edit seminar %s.  Please create an account and contact the seminar organizers." % shortname)
        return redirect(url_for("show_seminar", shortname=shortname), 301), None
    if not new and not current_user.is_admin():
        # Make sure user has permission to edit
        organizer_data = db.seminar_organizers.lucky({'seminar_id': shortname, 'email':current_user.email})
        if organizer_data is None:
            owner_name = db.users.lucky({'email': seminar.owner}, 'full_name')
            owner = "<%s>" % (owner_name, seminar.owner)
            if owner_name:
                owner = owner_name + " " + owner
            flash_error("You do not have permssion to edit seminar %s.  Contact the seminar owner, %s, and ask them to grant you permission." % (shortname, owner))
            return redirect(url_for(".index"), 301), None
    if seminar is None:
        seminar = WebSeminar(shortname, data=None, editing=True)
    return None, seminar
