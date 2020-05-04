from flask import redirect, url_for, render_template
from flask_login import current_user
from seminars import db
from seminars.utils import (
    adapt_datetime,
    adapt_weektime,
    allowed_shortname,
    count_distinct,
    format_errmsg,
    lucky_distinct,
    make_links,
    max_distinct,
    search_distinct,
    show_input_errors,
    toggle,
    topic_dict,
    weekdays,
)
from lmfdb.utils import flash_error
from lmfdb.backend.utils import DelayCommit, IdentifierWrapper
from markupsafe import Markup
from psycopg2.sql import SQL
import pytz
from collections import defaultdict
from datetime import datetime
from lmfdb.logger import critical

import urllib.parse

combine = datetime.combine


class WebSeminar(object):
    def __init__(
        self, shortname, data=None, organizer_data=None, editing=False, showing=False, saving=False, deleted=False
    ):
        if data is None and not editing:
            data = seminars_lookup(shortname, include_deleted=deleted)
            if data is None:
                raise ValueError("Seminar %s does not exist" % shortname)
            data = dict(data.__dict__)
        elif data is not None:
            data = dict(data)
            if data.get("topics") is None:
                data["topics"] = []
            if data.get("institutions") is None:
                data["institutions"] = []
            if data.get("timezone") is None:
                data["timesone"] = str(current_user.tz)
        self.new = data is None
        self.deleted = False
        if self.new:
            self.shortname = shortname
            self.display = current_user.is_creator
            self.online = True  # default
            self.access = "open"  # default
            self.visibility = 2 # public by default, once display is set to True
            self.is_conference = False  # seminar by default
            self.frequency = 7
            self.per_day = 1
            self.weekday = self.start_time = self.end_time = None
            self.timezone = str(current_user.tz)
            for key, typ in db.seminars.col_type.items():
                if key == "id" or hasattr(self, key):
                    continue
                elif typ == "text":
                    setattr(self, key, "")
                elif typ == "text[]":
                    setattr(self, key, [])
                else:
                    critical(
                        "Need to update seminar code to account for schema change key=%s" % key
                    )
                    setattr(self, key, None)
            if organizer_data is None:
                organizer_data = [
                    {
                        "seminar_id": self.shortname,
                        "email": current_user.email,
                        "homepage": current_user.homepage,
                        "full_name": current_user.name,
                        "order": 0,
                        "curator": False,
                        "display": True,
                        "contact": True,
                    }
                ]
        else:
            # The output from psycopg2 seems to always be given in the server's time zone
            if data.get("timezone"):
                tz = pytz.timezone(data["timezone"])
                if data.get("start_time"):
                    data["start_time"] = adapt_datetime(data["start_time"], tz)
                if data.get("end_time"):
                    data["end_time"] = adapt_datetime(data["end_time"], tz)
            # transition to topics including the subject
            if data.get("topics"):
                data["topics"] = [(topic if "_" in topic else "math_" + topic) for topic in data["topics"]]
            self.__dict__.update(data)
        if organizer_data is None:
            organizer_data = list(
                db.seminar_organizers.search({"seminar_id": self.shortname}, sort=["order"])
            )
        self.organizer_data = organizer_data
        self.convert_time_to_times()

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        # Note that equality ignores organizers
        return isinstance(other, WebSeminar) and all(
            getattr(self, key, None) == getattr(other, key, None) for key in db.seminars.search_cols
            if key not in ["edited_at", "edited_by"]
        )

    def __ne__(self, other):
        return not (self == other)

    def convert_time_to_times(self):
        if self.is_conference:
            self.frequency = None
        if self.frequency is None:
            self.weekdays = []
            self.time_slots = []
            return
        if self.frequency > 1 and self.frequency <= 7:
            self.frequency = 7
        elif self.frequency > 7 and self.frequency <= 14:
            self.frequency = 14
        elif self.frequency > 14 and self.frequency <= 21:
            self.frequency = 21
        else:
            self.frequency = None
            self.weekdays = []
            self.time_slots = []
            return
        if not self.weekdays or not self.time_slots:
            self.weekdays = []
            self.time_slots = []
            if self.weekday is not None and self.start_time is not None and self.end_time is not None:
                self.weekdays = [self.weekday]
                self.time_slots = [self.start_time.strftime("%H:%M") + "-" + self.end_time.strftime("%H:%M")]
        else:
            n = min(len(self.weekdays),len(self.time_slots))
            self.weekdays = self.weekdays[0:n]
            self.time_slots = self.time_slots[0:n]
        if self.frequency and (not self.weekdays or not self.time_slots):
            if not self.weekdays:
                self.weekdays = [0]
            if not self.time_slots:
                self.time_slots = ["00:00-01:00"]

    def visible(self):
        """
        Whether this seminar should be shown to the current user
        """
        return (self.owner == current_user.email or
                current_user.is_subject_admin(self) or
                # TODO: remove temporary measure of allowing visibility None
                self.display and (self.visibility is None or self.visibility > 0 or current_user.email in self.editors()))

    def searchable(self):
        """
        Whether this seminar should show up in search results (and whether its talks should show up on the browse page)
        """
        # TODO: remove temporary measure of allowing visibility None
        return self.display and (self.visibility is None or self.visibility > 1)

    def save(self):
        data = {col: getattr(self, col, None) for col in db.seminars.search_cols}
        assert data.get("shortname")
        data["edited_by"] = int(current_user.id)
        data["edited_at"] = datetime.now(tz=pytz.UTC)
        db.seminars.insert_many([data])

    def save_organizers(self):
        # Need to allow for deleting organizers, so we delete them all then add them back
        with DelayCommit(db):
            db.seminar_organizers.delete({"seminar_id": self.shortname})
            db.seminar_organizers.insert_many(self.organizer_data)

    # We use timestamps on January 1, 2020 to save start and end times
    # so that we have a well defined conversion between time zone and UTC offset (which
    # is how postgres/psycopg2 stores its time zones).

    @property
    def tz(self):
        return pytz.timezone(self.timezone)

    def show_day(self, truncate=True, adapt=True):
        if self.weekday is None:
            return ""
        elif self.start_time is None or not adapt:
            d = weekdays[self.weekday]
        else:
            d = weekdays[adapt_weektime(self.start_time, self.tz, weekday=self.weekday)[0]]
        if truncate:
            return d[:3]
        else:
            return d

    def _show_time(self, t, adapt):
        """ t is a datetime, adapt is a boolean """
        if t:
            if adapt and self.weekday is not None:
                t = adapt_weektime(t, self.tz, weekday=self.weekday)[1]
            return t.strftime("%H:%M")
        else:
            return ""

    def show_start_time(self, adapt=True):
        return self._show_time(self.start_time, adapt)

    def show_end_time(self, adapt=True):
        return self._show_time(self.end_time, adapt)

    def show_weektime_and_duration(self, adapt=True):
        s = self.show_day(truncate=False,adapt=adapt)
        if s:
            s += ", "
        s += self.show_start_time(adapt=adapt)
        if self.start_time and self.end_time:
            s += "-" + self.show_end_time(adapt=adapt)
        return s

    def show_topics(self):
        if self.topics:
            subjects = set(topic.split("_", 1)[0] for topic in self.topics)
            tdict = topic_dict(include_subj=(len(subjects) > 1))
            return " ".join('<span class="topic_label">%s</span>' % tdict[topic] for topic in self.topics)
        else:
            return ""

    def show_name(self, homepage_link=False, external=False, show_attributes=False, plain=False):
        if plain:
            return self.name + (self.show_attributes() if show_attributes else "")
        # Link to seminar
        if homepage_link:
            if self.homepage:
                link = '<a href="%s">%s</a>' % (self.homepage, self.name)
            else:
                link = self.name
        else:
            kwargs = {"shortname": self.shortname}
            if external:
                kwargs["_external"] = True
                kwargs["_scheme"] = "https"
            link = '<a href="%s">%s</a>' % (url_for("show_seminar", **kwargs), self.name)
        if show_attributes:
            link += self.show_attributes()
        return link

    def show_attributes(self):
        if not self.display:
            return " (hidden)"
        elif self.visibility == 0:
            return " (private)"
        elif self.visibility == 1:
            return " (unlisted)"
        elif self.online:
            return " (online)"
        else:
            return ""

    def show_description(self):
        if self.description:
            return self.description
        else:
            return ""

    def is_subscribed(self):
        if current_user.is_anonymous:
            return False
        return self.shortname in current_user.seminar_subscriptions

    def show_subscribe(self):
        if current_user.is_anonymous:
            return ""

        return toggle(
            tglid="tlg" + self.shortname,
            value=self.shortname,
            checked=self.is_subscribed(),
            classes="subscribe",
        )

    def show_homepage(self,newtab=False):
        if not self.homepage:
            return ""
        else:
            return "<a href='%s'%s>External homepage</a>" % (self.homepage,' target="_blank"' if newtab else '')

    def show_institutions(self):
        if self.institutions:
            links = []
            for rec in db.institutions.search(
                {"shortname": {"$in": self.institutions}},
                ["shortname", "name", "homepage"],
                sort=["name"],
            ):
                if rec["homepage"]:
                    links.append('<a href="%s">%s</a>' % (rec["homepage"], rec["name"]))
                else:
                    links.append(rec["name"])
            return " / ".join(links)
        else:
            return ""

    def show_comments(self):
        if self.comments:
            return "\n".join("<p>%s</p>\n" % (elt) for elt in make_links(self.comments).split("\n\n"))
        else:
            return ""

    def show_knowl_embed(self, daterange, uniqstr='0'):
        return r'<a knowl="dynamic_show" kwargs="{content}">Embed this schedule</a>'.format(
            content=Markup.escape(render_template("seminar-embed-code-knowl.html", seminar=self, daterange=daterange, uniqstr=uniqstr)),
        )

    def oneline(
        self,
        include_institutions=True,
        include_datetime=True,
        include_description=True,
        include_subscribe=True,
        show_attributes=False,
    ):
        cols = []
        if include_datetime:
            t = adapt_datetime(self.next_talk_time)
            if t is None:
                cols.append(('class="date"', ""))
                cols.append(('class="time"', ""))
            else:
                cols.append(('class="date"', t.strftime("%a %b %-d")))
                cols.append(('class="time"', t.strftime("%H:%M")))
        cols.append(('class="name"', self.show_name(show_attributes=show_attributes)))
        if include_institutions:
            cols.append(('class="institution"', self.show_institutions()))
        if include_description:
            cols.append(('class="description"', self.show_description()))
        if include_subscribe:
            cols.append(('class="subscribe"', self.show_subscribe()))
        return "".join("<td %s>%s</td>" % c for c in cols)

    def editors(self):
        return [rec["email"].lower() for rec in self.organizer_data if rec["email"]] + [
            self.owner.lower()
        ]

    def user_can_delete(self):
        # Check whether the current user can delete the seminar
        # See can_edit_seminar for another permission check
        # that takes a seminar's shortname as an argument
        # and returns various error messages if not editable
        return current_user.is_subject_admin(self) or (
            current_user.email_confirmed and current_user.email.lower() == self.owner.lower()
        )

    def user_can_edit(self):
        # Check whether the current user can edit the seminar
        # See can_edit_seminar for another permission check
        # that takes a seminar's shortname as an argument
        # and returns various error messages if not editable
        return current_user.is_subject_admin(self) or (
            current_user.email_confirmed and current_user.email.lower() in self.editors()
        )

    def _show_editors(self, label, curators=False):
        """ shows organizors (or curators if curators is True) """
        editors = []
        for rec in self.organizer_data:
            show = rec["curator"] if curators else not rec["curator"]
            if show and rec["display"]:
                link = (rec["homepage"] if rec["homepage"] else ("mailto:%s" % (rec["email"]) if rec["email"] else ""))
                name = rec["full_name"] if rec["full_name"] else link
                if name:
                    namelink = '<a href="%s">%s</a>' % (link, name) if link else name
                    if link and db.users.count({"email":rec["email"], "email_confirmed":True}):
                        namelink += "*"
                    editors.append(namelink)
        if editors:
            return "<tr><td>%s:</td><td>%s</td></tr>" % (label, ", ".join(editors))
        else:
            return ""

    def show_organizers(self):
        return self._show_editors("Organizers")

    def show_curators(self):
        return self._show_editors("Curators", curators=True)

    def add_talk_link(self, ptag=True):
        if current_user.email in self.editors():
            s = '<a href="%s">Add talk</a>' % url_for("create.edit_talk", seminar_id=self.shortname)
            if ptag:
                s = "<p>%s</p>" % s
            return s
        else:
            return ""

    def show_input_time(self, time):
        if not time:
            return ""
        return time.strftime("%H:%M")

    def show_input_date(self, date):
        if not date:
            return ""
        return date.strftime("%b %d, %Y")

    def show_schedule_date(self, date):
        if not date:
            return ""
        format = "%a %b %-d" if adapt_datetime(date,self.tz).year == datetime.now(self.tz).year else "%d-%b-%Y"
        return adapt_datetime(date, self.tz).strftime(format)

    def talks(self, projection=1):
        from seminars.talk import talks_search  # avoid import loop

        query = {"seminar_id": self.shortname, "display": True, "hidden": {"$or": [False, {"$exists": False}]}}
        if self.user_can_edit():
            query.pop("display")
        return talks_search(query, projection=projection)

    @property
    def ics_link(self):
        return url_for(".ics_seminar_file", shortname=self.shortname, _external=True, _scheme="https")

    @property
    def ics_gcal_link(self):
        return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(
            {"cid": url_for(".ics_seminar_file", shortname=self.shortname, _external=True, _scheme="http")}
        )

    @property
    def ics_webcal_link(self):
        return url_for(".ics_seminar_file", shortname=self.shortname, _external=True, _scheme="webcal")

    @property
    def next_talk_time(self):
        try:
            return self._next_talk_time
        except AttributeError:
            self._next_talk_time = next_talk(self.shortname)
            return self._next_talk_time

    @next_talk_time.setter
    def next_talk_time(self, t):
        self._next_talk_time = t

    def delete(self):
        # We don't actually delete from the seminars and talks tables but instead just
        # set the deleted flag.  We actually delete from seminar_organizers and subscriptions
        # since these are less important.
        if self.user_can_delete():
            with DelayCommit(db):
                db.seminars.update({"shortname": self.shortname}, {"deleted": True})
                db.talks.update({"seminar_id": self.shortname}, {"deleted": True})
                db.seminar_organizers.delete({"seminar_id": self.shortname})
                for elt in db.users.search(
                    {"seminar_subscriptions": {"$contains": self.shortname}},
                    ["id", "seminar_subscriptions"],
                ):
                    elt["seminar_subscriptions"].remove(self.shortname)
                    db.users.update(
                        {"id": elt["id"]},
                        {"seminar_subscriptions": elt["seminar_subscriptions"]}
                    )
                for i, talk_sub in db._execute(
                    SQL("SELECT {},{} FROM {} WHERE {} ? %s").format(
                        *map(
                            IdentifierWrapper,
                            ["id", "talk_subscriptions", "users", "talk_subscriptions"],
                        )
                    ),
                    [self.shortname],
                ):
                    del talk_sub[self.shortname]
                    db.users.update({"id": i}, {"talk_subscriptions": talk_sub})
            return True
        else:
            return False


def seminars_header(
    include_time=True, include_institutions=True, include_description=True, include_subscribe=True
):
    cols = []
    if include_time:
        cols.append(('colspan="2" class="yourtime"', "Next talk"))
    cols.append(("", "Name"))
    if include_institutions:
        cols.append(("", "Institutions"))
    if include_description:
        cols.append(('style="min-width:280px;"', "Description"))
    if include_subscribe:
        if current_user.is_anonymous:
            cols.append(("", ""))
        else:
            cols.append(("", "Saved"))
    return "".join("<th %s>%s</th>" % pair for pair in cols)


_selecter = SQL(
    "SELECT {0} FROM (SELECT DISTINCT ON (shortname) {1} FROM {2} ORDER BY shortname, id DESC) tmp{3}"
)
_counter = SQL(
    "SELECT COUNT(*) FROM (SELECT 1 FROM (SELECT DISTINCT ON (shortname) {0} FROM {1} ORDER BY shortname, id DESC) tmp{2}) tmp2"
)
_maxer = SQL(
    "SELECT MAX({0}) FROM (SELECT DISTINCT ON (shortname) {1} FROM {2} ORDER BY shortname, id DESC) tmp{3}"
)


def _construct(organizer_dict):
    def inner_construct(rec):
        if not isinstance(rec, dict):
            return rec
        else:
            return WebSeminar(
                rec["shortname"], organizer_data=organizer_dict.get(rec["shortname"]), data=rec
            )

    return inner_construct


def _iterator(organizer_dict):
    def inner_iterator(cur, search_cols, extra_cols, projection):
        for rec in db.seminars._search_iterator(cur, search_cols, extra_cols, projection):
            yield _construct(organizer_dict)(rec)

    return inner_iterator


def seminars_count(query={}, include_deleted=False):
    """
    Replacement for db.seminars.count to account for versioning.
    """
    return count_distinct(db.seminars, _counter, query, include_deleted)


def seminars_max(col, constraint={}, include_deleted=False):
    return max_distinct(db.seminars, _maxer, col, constraint, include_deleted)


def seminars_search(*args, **kwds):
    """
    Replacement for db.seminars.search to account for versioning, return WebSeminar objects.

    Doesn't support split_ors or raw.  Always computes count.
    """
    organizer_dict = kwds.pop("organizer_dict", {})
    return search_distinct(
        db.seminars, _selecter, _counter, _iterator(organizer_dict), *args, **kwds
    )


def seminars_lucky(*args, **kwds):
    """
    Replacement for db.seminars.lucky to account for versioning, return a WebSeminar object or None.
    """
    organizer_dict = kwds.pop("organizer_dict", {})
    return lucky_distinct(db.seminars, _selecter, _construct(organizer_dict), *args, **kwds)


def seminars_lookup(shortname, projection=3, label_col="shortname", organizer_dict={}, include_deleted=False):
    return seminars_lucky(
        {label_col: shortname}, projection=projection, organizer_dict=organizer_dict, include_deleted=include_deleted
    )


def all_organizers():
    """
    A dictionary with keys the seminar ids and values a list of organizer data as fed into WebSeminar.
    Usable for the organizer_dict input to seminars_search, seminars_lucky and seminars_lookup
    """
    organizers = defaultdict(list)
    for rec in db.seminar_organizers.search({}, sort=["seminar_id", "order"]):
        organizers[rec["seminar_id"]].append(rec)
    return organizers


def all_seminars():
    """
    A dictionary with keys the seminar ids and values a WebSeminar object.
    """
    return {
        seminar.shortname: seminar
        for seminar in seminars_search({}, organizer_dict=all_organizers())
    }

def next_talks(query=None):
    """
    A dictionary with keys the seminar_ids and values datetimes (either the next talk in that seminar, or datetime.max if no talk scheduled so that they sort at the end.
    """
    if query is None:
        query = {"end_time": {"$gte": datetime.now(pytz.UTC)}}
    ans = defaultdict(lambda: pytz.UTC.localize(datetime.max))
    from seminars.talk import _counter as talks_counter
    _selecter = SQL("""
SELECT DISTINCT ON (seminar_id) {0} FROM
(SELECT DISTINCT ON (seminar_id, seminar_ctr) {1} FROM {2} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{3}
""")
    for rec in search_distinct(
            db.talks,
            _selecter,
            talks_counter,
            db.talks._search_iterator,
            query,
            projection=["seminar_id", "start_time"],
            sort=["seminar_id", "start_time"]):
        ans[rec["seminar_id"]] = rec["start_time"]
    return ans

def next_talk_sorted(results):
    """
    Sort a list of WebSeminars by when their next talk is (and add the next_talk_time attribute to each seminar).

    Returns the sorted list.
    """
    results = list(results)
    ntdict = next_talks()
    for R in results:
        R.next_talk_time = ntdict[R.shortname]
    results.sort(key=lambda R: (R.next_talk_time, R.name))
    for R in results:
        if R.next_talk_time.replace(tzinfo=None) == datetime.max:
            R.next_talk_time = None
    return results

def next_talk(shortname):
    """
    Gets the next talk time in a single seminar.  Note that if you need this information for many seminars, the `next_talks` function will be faster.
    """
    from seminars.talk import talks_lucky
    return talks_lucky({"seminar_id": shortname, "start_time": {"$gte": datetime.now(pytz.UTC)}}, projection="start_time", sort=["start_time"])

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
    errmsgs = []
    if not allowed_shortname(shortname) or len(shortname) < 3 or len(shortname) > 32:
        errmsgs.append(
            format_errmsg(
                "The identifier '%s' must be 3 to 32 characters in length and can include only letters, numbers, hyphens and underscores.", shortname
            )
        )
        return show_input_errors(errmsgs), None
    seminar = seminars_lookup(shortname, include_deleted=True)
    # Check if seminar exists
    if new != (seminar is None):
        if seminar is not None and seminar.deleted:
            errmsgs.append(
                format_errmsg(
                    "Identifier %s is reserved by a seminar that has been deleted",
                    shortname)
            )
        else:
            errmsgs.append(
                format_errmsg(
                    "Identifier %s " + ("already exists" if new else "does not exist"),
                    shortname
                )
            )
        return show_input_errors(errmsgs), None
    if seminar is not None and seminar.deleted:
        return redirect(url_for("create.deleted_seminar", shortname=shortname), 302)
    # can happen via talks, which don't check for logged in in order to support tokens
    if current_user.is_anonymous:
        flash_error(
            "You do not have permission to edit seminar %s. Please create an account and contact the seminar organizers.",
            shortname
        )
        return redirect(url_for("show_seminar", shortname=shortname), 302), None
    # Make sure user has permission to edit
    if not new and not seminar.user_can_edit():
        flash_error(
            "You do not have permission to edit seminar %s. Please contact the seminar organizers.",
            shortname
        )
        return redirect(url_for("show_seminar", shortname=shortname), 302), None
    if seminar is None:
        seminar = WebSeminar(shortname, data=None, editing=True)
    return None, seminar
