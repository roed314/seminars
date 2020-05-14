from flask import redirect, url_for, render_template
from flask_login import current_user
from seminars import db
from seminars.utils import (
    adapt_datetime,
    adapt_weektimes,
    allowed_shortname,
    count_distinct,
    format_errmsg,
    lucky_distinct,
    make_links,
    max_distinct,
    search_distinct,
    show_input_errors,
    weekdays,
    killattr,
)
from seminars.topic import topic_dag
from seminars.toggle import toggle
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
        self, shortname, data=None, organizers=None, editing=False, showing=False, saving=False, deleted=False
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
                elif typ == "smallint[]":
                    setattr(self, key, [])
                elif typ == "timestamp with time zone":
                    setattr(self, key, None)
                elif typ == "timestamp with time zone[]":
                    setattr(self, key, [])
                elif typ == "date":
                    setattr(self, key, None)
                elif typ == "bigint":
                    setattr(self, key, None)
                else:
                    critical(
                        "Need to update seminar code to account for schema change key=%s" % key
                    )
                    setattr(self, key, None)
            if organizers is None:
                organizers = [
                    {
                        "seminar_id": self.shortname,
                        "email": current_user.email,
                        "homepage": current_user.homepage,
                        "name": current_user.name,
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
        if organizers is None:
            organizers = list(
                db.seminar_organizers.search({"seminar_id": self.shortname}, sort=["order"])
            )
        self.organizers = organizers
        self.cleanse()

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

    def cleanse(self):
        """
        This function is used to ensure backward compatibility across changes to the schema and/or validation
        This is the only place where columns we plan to drop should be referenced 
        """
        from seminars.talk import talks_lucky

        if self.is_conference:
            self.frequency = None
            if not self.per_day:
                self.per_day = 4
        if self.frequency is None:
            self.weekdays = []
            self.time_slots = []
        else:
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
        if self.frequency and (not self.weekdays or not self.time_slots):
            self.weekdays = []
            self.time_slots = []
            if self.weekday is not None and self.start_time is not None and self.end_time is not None:
                self.weekdays = [self.weekday]
                self.time_slots = [self.start_time.strftime("%H:%M") + "-" + self.end_time.strftime("%H:%M")]
            else:
                now = datetime.now(tz=self.tz)
                t = talks_lucky(
                    {"seminar_id": self.shortname, "start_time": {"$gte": now}},
                    projection=["start_time", "end_time"],
                    sort=[("start_time",1)],
                    objects=False,
                )
                if not t:
                    t = talks_lucky(
                        {"seminar_id": self.shortname, "start_time": {"$lt": now}},
                        projection=["start_time", "end_time"],
                        sort=[("start_time", -1)],
                        objects=False,
                    )
                if t:
                    self.weekdays = [t["start_time"].weekday()]
                    self.time_slots = [t["start_time"].strftime("%H:%M") + "-" + t["end_time"].strftime("%H:%M")]
                else:
                    # Create a slot with an obviously bogus time in the hope that the user will notice and set it
                    self.weekdays = [0]
                    self.time_slots = ["00:00-01:00"]
        n = min(len(self.weekdays),len(self.time_slots))
        self.weekdays = self.weekdays[0:n]
        self.time_slots = self.time_slots[0:n]
        s = self.description
        self.description = s[0].upper() + s[1:] if s else ""
        # Port old subjects and topics to the new topic scheme
        if getattr(self, "subjects", []):
            def update_topic(topic):
                if topic in ["math", "physics", "bio"]:
                    return [topic]
                if topic in ["math_mp", "mp", "physics_math-ph"]:
                    return ["math", "physics", "math-ph"]
                if len(topic) == 2:
                    return ["math", "math_" + topic.upper()]
                if topic.startswith("math_"):
                    return ["math", "math_" + topic[5:].upper()]
                if topic.startswith("bio_bio_"):
                    return ["bio", "bio_" + topic[8:].upper()]
                assert topic.startswith("physics_")
                topic = topic[8:]
                if topic.startswith("nlin_"):
                    return ["physics", "nlin", topic]
                if topic.startswith("cond-mat_"):
                    return ["physics", "cond-mat", topic]
                if topic.startswith("nucl-"):
                    return ["physics", "nucl-ph", topic]
                if topic.startswith("hep-"):
                    return ["physics", "hep", topic]
                if topic.startswith("astro-ph_"):
                    return ["physics", "astro-ph", topic]
                return ["physics", topic]
            self.topics = sorted(set(sum([update_topic(topic) for topic in self.subjects + self.topics], [])))
        self.subjects = []
        # remove columns we plan to drop
        for attr in ["start_time","end_time","start_times","end_times","weekday","archived"]:
            killattr(self, attr)
        for i in range(len(self.organizers)):
            org = self.organizers[i]
            if not org.get("name") and org.get("full_name"):
                org["name"] = org["full_name"]
            if org.get("full_name"):
                org.pop("full_name")
            self.organizers[i] = org

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
            for i in range(len(self.organizers)): # FIXME: remove once this code is live
                self.organizers[i]["full_name"] = self.organizers[i]["name"] # FIXME: remove once this code is live
            db.seminar_organizers.insert_many(self.organizers)

    # We use timestamps on January 1, 2020 to save start and end times
    # so that we have a well defined conversion between time zone and UTC offset (which
    # is how postgres/psycopg2 stores its time zones).

    @property
    def tz(self):
        return pytz.timezone(self.timezone)

    @property
    def series_type(self):
        return "conference" if self.is_conference else "seminar series"

    def _show_date(self, d):
        format = "%a %b %-d" if d.year == datetime.now(self.tz).year else "%d-%b-%Y"
        return d.strftime(format)

    def show_conference_dates (self, adapt=True):
        if self.is_conference:
            if self.start_date and self.end_date:
                if self.start_date == self.end_date:
                    return self._show_date(self.start_date)
                else:
                    return self._show_date(self.start_date) + " to " + self._show_date(self.end_date)
            else:
                return "TBA"
        else:
            return ""

    def show_seminar_times(self, adapt=True):
        """ weekday is an integer in [0,6], daytimes is a string "HH:MM-HH:MM" """
        if self.is_conference or not self.frequency:
            return ""
        n = min(len(self.weekdays),len(self.time_slots))
        if n == 0 or not self.frequency:
            return "No regular schedule"
        if self.frequency == 7:
            s = ""
        elif self.frequency == 14:
            s = "Every other "
        elif self.frequency == 21:
            s = "Every third "
        prevd = -1
        for i in range(n):
            s += ", " if i else ""
            d = self.weekdays[i]
            t = self.time_slots[i]
            if adapt:
                d, t = adapt_weektimes (d, t, self.tz, current_user.tz)
            s += t if d==prevd else (weekdays[d] + " " + t)
            prevd = d
        return s

    def show_topics(self):
        if self.topics:
            return " ".join('<span class="topic_label">%s</span>' % topic for topic in topic_dag.leaves(self.topics))
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
            name=self.shortname,
            value=1 if self.is_subscribed() else -1,
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

    def show_comments(self, prefix=""):
        if self.comments:
            return "\n".join("<p>%s</p>\n" % (elt) for elt in make_links(prefix + self.comments).split("\n\n"))
        else:
            return ""

    def show_knowl_embed(self, daterange, uniqstr='0'):
        return r'<a knowl="dynamic_show" kwargs="{content}">Embed this schedule</a>'.format(
            content=Markup.escape(render_template("seminar-embed-code-knowl.html", seminar=self, daterange=daterange, uniqstr=uniqstr)),
        )

    def oneline(
        self,
        conference=False,
        include_institutions=True,
        include_datetime=True,
        include_description=True,
        include_topics=False,
        include_subscribe=True,
        show_attributes=False,
    ):
        datetime_tds = ""
        if include_datetime:
            if conference: # include start and end date instead
                if self.is_conference and self.start_date and self.end_date:
                    if self.start_date == self.end_date:
                        datetime_tds = '<td colspan="2" class="onedate">' + self._show_date(self.start_date) + '</td>'
                    else:
                        datetime_tds = '<td class="startdate">' + self._show_date(self.start_date) + '</td><td class="enddate">' + self._show_date(self.end_date) + '</td>'
                else:
                    datetime_tds = '<td class="startdate"></td><td class="enddate"></td>'
            else: # could include both conferences and seminar series
                t = adapt_datetime(self.next_talk_time)
                if t is None:
                    datetime_tds = '<td></td><td></td><td></td>'
                else:
                    datetime_tds = t.strftime('<td class="weekday">%a</td><td class="monthdate">%b %d</td><td class="time">%H:%M</td>')
        cols = []
        cols.append(('class="seriesname"', self.show_name(show_attributes=show_attributes,homepage_link=True if self.deleted else False)))
        if include_institutions:
            cols.append(('class="institutions"', self.show_institutions()))
        if include_description:
            cols.append(('class="description"', self.show_description()))
        if include_topics:
            cols.append(('class="topics"', self.show_topics()))
        if include_subscribe:
            cols.append(('class="subscribe"', self.show_subscribe()))
        return datetime_tds + "".join("<td %s>%s</td>" % c for c in cols)

    def editors(self):
        return [rec["email"].lower() for rec in self.organizers if rec["email"]] + [
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
        for rec in self.organizers:
            show = rec["curator"] if curators else not rec["curator"]
            if show and rec["display"]:
                link = (rec["homepage"] if rec["homepage"] else ("mailto:%s" % (rec["email"]) if rec["email"] else ""))
                name = rec["name"] if rec["name"] else link
                if name:
                    namelink = '<a href="%s">%s</a>' % (link, name) if link else name
                    if link and db.users.count({"email":rec["email"], "email_confirmed":True}):
                        namelink += "*"
                    editors.append(namelink)
        return ", ".join(editors)

    def show_organizers(self):
        return self._show_editors("Organizers")

    def show_curators(self):
        return self._show_editors("Curators", curators=True)

    def num_visible_organizers(self):
        return len([r for r in self.organizers if not r["curator"] and r["display"]])

    def num_visible_curators(self):
        return len([r for r in self.organizers if r["curator"] and r["display"]])

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
                db.talks.update({"seminar_id": self.shortname, "deleted": False}, {"deleted": True, "deleted_with_seminar": True})
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
            self.deleted = True
            return True
        else:
            return False


def series_header(
    conference=False, include_datetime=True, include_institutions=True, include_description=True, include_topics=False, include_subscribe=True
):
    cols = []
    if include_datetime:
        if conference:
            cols.append(('colspan="2" class="yourtime"', "Dates"))
        else:
            cols.append(('colspan="3" class="yourtime"', "Next talk"))
    cols.append(('class="seriesname"', "Name"))
    if include_institutions:
        cols.append(('class="institutions"', "Institutions"))
    if include_description:
        cols.append(('class="description"', "Description"))
    if include_topics:
        cols.append(("", "Topics"))
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


def _construct(organizer_dict, objects=True, more=False):
    def object_construct(rec):
        if not isinstance(rec, dict):
            return rec
        else:
            if more:
                moreval = rec.pop("more")
            seminar = WebSeminar(
                rec["shortname"], organizers=organizer_dict.get(rec["shortname"]), data=rec
            )
            if more:
                seminar.more = moreval
            return seminar
    def default_construct(rec):
        return rec

    return object_construct if objects else default_construct


def _iterator(organizer_dict, objects=True, more=False):
    def object_iterator(cur, search_cols, extra_cols, projection):
        for rec in db.seminars._search_iterator(cur, search_cols, extra_cols, projection):
            if isinstance(rec, dict) and "shortname" in rec and not rec["shortname"] in organizer_dict:
                continue
            yield _construct(organizer_dict, more=more)(rec)
    return object_iterator if objects else db.seminars._search_iterator


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
    objects = kwds.pop("objects", True)
    more = kwds.get("more", False)
    if more is not False: # might empty dictionary
        more, moreval = db.seminars._parse_dict(more)
        if more is None:
            more = Placeholder()
            moreval = [True]
        kwds["more"] = more = (more, moreval)
    return search_distinct(
        db.seminars, _selecter, _counter, _iterator(organizer_dict, objects=objects, more=more), *args, **kwds
    )


def seminars_lucky(*args, **kwds):
    """
    Replacement for db.seminars.lucky to account for versioning, return a WebSeminar object or None.
    """
    organizer_dict = kwds.pop("organizer_dict", {})
    objects = kwds.pop("objects", True)
    return lucky_distinct(db.seminars, _selecter, _construct(organizer_dict, objects=objects), *args, **kwds)


def seminars_lookup(shortname, projection=3, label_col="shortname", organizer_dict={}, include_deleted=False, objects=True):
    return seminars_lucky(
        {label_col: shortname},
        projection=projection,
        organizer_dict=organizer_dict,
        include_deleted=include_deleted,
        objects=objects,
    )


def all_organizers(query={}):
    """
    A dictionary with keys the seminar ids and values a list of organizer data as fed into WebSeminar.
    Usable for the organizer_dict input to seminars_search, seminars_lucky and seminars_lookup
    """
    organizers = defaultdict(list)
    for rec in db.seminar_organizers.search(query, sort=["seminar_id", "order"]):
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
        query = {"end_time": {"$gte": datetime.now(pytz.UTC)}, "hidden": False}  # ignore hidden talks by default
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
        return redirect(url_for("create.deleted_seminar", shortname=shortname), 302), None
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
