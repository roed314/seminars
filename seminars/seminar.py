from flask import redirect, url_for
from flask_login import current_user
from seminars import db
from seminars.utils import (
    search_distinct,
    lucky_distinct,
    count_distinct,
    max_distinct,
    allowed_shortname,
    topic_dict,
    weekdays,
    adapt_weektime,
    adapt_datetime,
    toggle,
)
from lmfdb.utils import flash_error
from lmfdb.backend.utils import DelayCommit, IdentifierWrapper
from psycopg2.sql import SQL
import pytz
from collections import defaultdict
from datetime import datetime
from lmfdb.logger import critical

combine = datetime.combine


class WebSeminar(object):
    def __init__(
        self, shortname, data=None, organizer_data=None, editing=False, showing=False, saving=False
    ):
        if data is None and not editing:
            data = seminars_lookup(shortname)
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
        if self.new:
            self.shortname = shortname
            self.display = current_user.is_creator
            self.online = True  # default
            self.access = "open"  # default
            self.archived = False  # don't start out archived
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
                    critical("Need to update seminar code to account for schema change key=%s" % key)
                    setattr(self, key, None)
            if organizer_data is None:
                organizer_data = [
                    {
                        "seminar_id": self.shortname,
                        "email": current_user.email,
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
            self.__dict__.update(data)
            # start_time and end_time are datetime.datetimes's (offset from 1/1/2020)
        if organizer_data is None:
            organizer_data = list(
                db.seminar_organizers.search({"seminar_id": self.shortname}, sort=["order"])
            )
        self.organizer_data = organizer_data

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        # Note that equality ignores organizers
        return isinstance(other, WebSeminar) and all(
            getattr(self, key, None) == getattr(other, key, None) for key in db.seminars.search_cols
        )

    def __ne__(self, other):
        return not (self == other)

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
        s = self.show_day(truncate=False)
        if s:
            s += ", "
        s += self.show_start_time(adapt=adapt)
        if self.start_time and self.end_time:
            s += "-" + self.show_end_time(adapt=adapt)
        return s

    def show_topics(self):
        if self.topics:
            return " (" + ", ".join(topic_dict()[topic] for topic in self.topics) + ")"
        else:
            return ""

    def show_name(self, external=False, show_attributes=False):
        # Link to seminar
        kwargs = {"shortname": self.shortname}
        if external:
            kwargs["_external"] = True
            kwargs["_scheme"] = "https"
        link = '<a href="%s">%s</a>' % (url_for("show_seminar", **kwargs), self.name)
        if show_attributes:
            if not self.display:
                link += " (hidden)"
            elif self.archived:
                link += " (inactive)"
            elif self.online:
                link += " (online)"
        return link

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

    def show_homepage(self):
        if not self.homepage:
            return ""
        else:
            return "<a href='%s'>External homepage</a>" % (self.homepage)

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
            return "\n".join("<p>%s</p>\n" % (elt) for elt in self.comments.split("\n\n"))
        else:
            return ""

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
            cols.append(('class="day"', self.show_day()))
            cols.append(('class="time"', self.show_start_time()))
        cols.append(('class="name"', self.show_name(show_attributes=show_attributes)))
        if include_institutions:
            cols.append(('class="institution"', self.show_institutions()))
        if include_description:
            cols.append(('class="description"', self.show_description()))
        if include_subscribe:
            cols.append(('class="subscribe"', self.show_subscribe()))
        return "".join("<td %s>%s</td>" % c for c in cols)

    def editors(self):
        return [rec["email"].lower() for rec in self.organizer_data if rec["email"]] + [self.owner.lower()]

    def user_can_delete(self):
        # Check whether the current user can delete the seminar
        # See can_edit_seminar for another permission check
        # that takes a seminar's shortname as an argument
        # and returns various error messages if not editable
        return current_user.is_admin or (
            current_user.email_confirmed and current_user.email.lower() == self.owner.lower()
        )

    def user_can_edit(self):
        # Check whether the current user can edit the seminar
        # See can_edit_seminar for another permission check
        # that takes a seminar's shortname as an argument
        # and returns various error messages if not editable
        return current_user.is_admin or (
            current_user.email_confirmed and current_user.email.lower() in self.editors()
        )

    def _show_editors(self, label, curators=False):
        """ shows organizors (or curators if curators is True) """
        editors = []
        for rec in self.organizer_data:
            show = rec["curator"] if curators else not rec["curator"]
            if show and rec["display"]:
                link = rec["homepage"] if rec["homepage"] else ("mailto:%s"%(rec["email"]) if rec["email"] else "")
                name = rec["full_name"] if rec["full_name"] else link
                if name:
                    editors.append('<a href="%s">%s</a>' % (link, name) if link else name)

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

    def talks(self, projection=1):
        from seminars.talk import talks_search  # avoid import loop

        query = {"seminar_id": self.shortname, "display": True}
        if self.user_can_edit():
            query.pop("display")
        return talks_search(query, projection=projection)

    def delete(self):
        if self.user_can_delete():
            with DelayCommit(db):
                db.seminars.delete({"shortname": self.shortname})
                db.talks.delete({"seminar_id": self.shortname})
                db.seminar_organizers.delete({"seminar_id": self.shortname})
                for elt in db.users.search(
                    {"seminar_subscriptions": {"$contains": self.shortname}},
                    ["id", "seminar_subscriptions"],
                ):
                    elt["seminar_subscriptions"].remove(self.shortname)
                    db.users.update(
                        {"id": elt["id"]}, {"seminar_subscriptions": elt["seminar_subscriptions"]}
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
        cols.append(('colspan="2" class="yourtime"', "Your time"))
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
        if isinstance(rec, str):
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


def seminars_lookup(shortname, projection=3, label_col="shortname", organizer_dict={}):
    return seminars_lucky(
        {label_col: shortname}, projection=projection, organizer_dict=organizer_dict
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
        flash_error(
            "The identifier must be nonempty and can include only letters, numbers, hyphens and underscores."
        )
        return redirect(url_for(".index"), 302), None
    seminar = seminars_lookup(shortname)
    # Check if seminar exists
    if new != (seminar is None):
        flash_error("Identifier %s %s" % (shortname, "already exists" if new else "does not exist"))
        return redirect(url_for(".index"), 302), None
    # can happen via talks, which don't check for logged in in order to support tokens
    if current_user.is_anonymous:
        flash_error(
            "You do not have permission to edit seminar %s.  Please create an account and contact the seminar organizers."
            % shortname
        )
        return redirect(url_for("show_seminar", shortname=shortname), 302), None
    # Make sure user has permission to edit
    if not new and not seminar.user_can_edit():
        owner = seminar.owner
        owner_name = db.users.lucky({"email": owner}, "name")
        if owner_name:
            owner = "%s (%s)" % (owner_name, owner)

        flash_error(
            "You do not have permission to edit seminar %s.  Contact the seminar owner, %s, and ask them to grant you permission."
            % (shortname, owner)
        )
        return redirect(url_for(".index"), 302), None
    if seminar is None:
        seminar = WebSeminar(shortname, data=None, editing=True)
    return None, seminar
