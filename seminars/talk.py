import pytz, datetime, random
from urllib.parse import urlencode, quote
from flask import url_for, redirect, render_template
from flask_login import current_user
from lmfdb.backend.utils import DelayCommit, IdentifierWrapper
from seminars import db
from seminars.utils import (
    search_distinct,
    lucky_distinct,
    count_distinct,
    max_distinct,
    adapt_datetime,
    toggle,
    make_links,
    topic_dict,
    languages_dict,
    topdomain,
)
from seminars.seminar import WebSeminar, can_edit_seminar
from lmfdb.utils import flash_error
from markupsafe import Markup
from psycopg2.sql import SQL
from icalendar import Event
from lmfdb.logger import critical


class WebTalk(object):
    def __init__(
        self,
        semid=None,
        semctr=None,
        data=None,
        seminar=None,
        editing=False,
        showing=False,
        saving=False,
        deleted=False,
    ):
        if data is None and not editing:
            data = talks_lookup(semid, semctr, include_deleted=deleted)
            if data is None:
                raise ValueError("Talk %s/%s does not exist" % (semid, semctr))
            data = dict(data.__dict__)
        elif data is not None:
            data = dict(data)
            # avoid Nones
            if data.get("topics") is None:
                data["topics"] = []
        if seminar is None:
            seminar = WebSeminar(semid, deleted=deleted)
        self.seminar = seminar
        self.new = data is None
        self.deleted=False
        if self.new:
            self.seminar_id = semid
            self.seminar_ctr = None
            self.token = "%016x" % random.randrange(16 ** 16)
            self.display = seminar.display
            self.online = getattr(seminar, "online", bool(seminar.live_link))
            self.timezone = seminar.timezone
            for key, typ in db.talks.col_type.items():
                if key == "id" or hasattr(self, key):
                    continue
                elif db.seminars.col_type.get(key) == typ and getattr(seminar, key, None):
                    # carry over from seminar, but not comments
                    setattr(self, key, getattr(seminar, key) if key != "comments" else "")
                elif typ == "text":
                    setattr(self, key, "")
                elif typ == "text[]":
                    setattr(self, key, [])
                else:
                    critical("Need to update talk code to account for schema change key=%s" % key)
                    setattr(self, key, None)
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

    def __repr__(self):
        title = self.title if self.title else "TBA"
        return "%s (%s) - %s, %s" % (
            title,
            self.speaker,
            self.show_date(),
            self.show_start_time(self.timezone),
        )

    def __eq__(self, other):
        return isinstance(other, WebTalk) and all(
            getattr(self, key, None) == getattr(other, key, None) for key in db.talks.search_cols
            if key not in ["edited_at", "edited_by"]
        )

    def __ne__(self, other):
        return not (self == other)

    def visible(self):
        """
        Whether this talk should be shown to the current user

        The visibility of a talk is at most the visibility of the seminar,
        but it can also be hidden even if the seminar is public.
        """
        return (self.seminar.owner == current_user.email or
                current_user.is_subject_admin(self) or
                self.display and ((self.seminar.visibility is None or self.seminar.visibility > 0) and not self.hidden or
                                  current_user.email in self.seminar.editors()))

    def searchable(self):
        """
        Whether this talk should show up on browse and search results.
        """
        return self.display and not self.hidden and self.seminar.searchable()

    def save(self):
        data = {col: getattr(self, col, None) for col in db.talks.search_cols}
        assert data.get("seminar_id") and data.get("seminar_ctr")
        topics = self.topics if self.topics else []
        try:
            data["edited_by"] = int(current_user.id)
        except (ValueError, AttributeError):
            # Talks can be edited by anonymous users with a token, with no id
            data["edited_by"] = -1
        data["edited_at"] = datetime.datetime.now(tz=pytz.UTC)
        db.talks.insert_many([data])

    @classmethod
    def _editable_time(cls, t):
        if not t:
            return ""
        return t.strftime("%Y-%m-%d %H:%M")

    def editable_start_time(self):
        """
        A version of the start time for editing
        """
        return self._editable_time(self.start_time)

    def editable_end_time(self):
        """
        A version of the start time for editing
        """
        return self._editable_time(self.end_time)

    @property
    def tz(self):
        return pytz.timezone(self.timezone)

    def show_start_time(self, tz=None):
        return adapt_datetime(self.start_time, tz).strftime("%H:%M")

    def show_end_time(self, tz=None):
        """
        INPUT:

        - ``tz`` -- a timezone object or None (use the current user's time zone)

        OUTPUT:

        If ``tz`` is given, the time in that time zone (no date).
        Otherwise, show the date only if different from the date of the start time in that time zone.
        """
        # This is used in show_time_and_duration, and needs to include the ending date if different (might not be the same in current user's time zone)
        t = adapt_datetime(self.end_time, newtz=tz)
        if tz is not None:
            return t.strftime("%H:%M")
        t0 = adapt_datetime(self.start_time, newtz=tz)
        if t0.date() == t.date():
            return t.strftime("%H:%M")
        else:
            return t.strftime("%a %b %-d, %H:%M")

    def show_date(self, tz=None):
        if self.start_time is None:
            return ""
        else:
            return adapt_datetime(self.start_time, newtz=tz).strftime("%a %b %-d")

    def show_time_and_duration(self, adapt=True):
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
        newtz = None if adapt else self.tz

        def ans(rmk):
            return "%s-%s (%s)" % (
                adapt_datetime(start, newtz=newtz).strftime("%a %b %-d, %H:%M"),
                adapt_datetime(end, newtz=newtz).strftime("%H:%M"),
                rmk,
            )

        # Add remark on when this is
        if start <= now <= end:
            return ans("ongoing")
        elif now < start:
            until = start - now
            if until < minute:
                return ans("starts in less than a minute")
            elif until < 90 * minute:
                return ans("starts in %s minutes" % (round(until / minute)))
            elif until < 36 * hour:
                return ans("starts in %s hours" % (round(until / hour)))
            elif until < 11 * day:
                return ans("%s days from now" % (round(until / day)))
            elif until < 7 * week:
                return ans("%s weeks from now" % (round(until / week)))
            elif until < 2 * year:
                return ans("%s months from now" % (round(until / month)))
            else:
                return ans("%s years from now" % (round(until / year)))
        else:
            ago = now - end
            if ago < minute:
                return ans("ended less than a minute ago")
            elif ago < 90 * minute:
                return ans("ended %s minutes ago" % (round(ago / minute)))
            elif ago < 36 * hour:
                return ans("ended %s hours ago" % (round(ago / hour)))
            elif ago < 11 * day:
                return ans("%s days ago" % (round(ago / day)))
            elif ago < 7 * week:
                return ans("%s weeks ago" % (round(ago / week)))
            elif ago < 2 * year:
                return ans("%s months ago" % (round(ago / month)))
            else:
                return ans("%s years ago" % (round(ago / year)))

    def show_title(self, visibility_info=False):
        title = self.title if self.title else "TBA"
        if visibility_info:
            if not self.display:
                title += " (hidden)"
            elif self.hidden:
                title += " (private)"
            elif self.seminar.visibility == 0:
                title += " (seminar private)"
            elif self.seminar.visibility == 1:
                title += " (seminar unlisted)"
            elif self.online:
                title += " (online)"
        return title

    def show_link_title(self):
        return "<a href={url}>{title}</a>".format(
            url=url_for("show_talk", semid=self.seminar_id, talkid=self.seminar_ctr),
            title=self.show_title(),
        )

    def show_knowl_title(self):
        return r'<a title="{title}" knowl="dynamic_show" kwargs="{content}">{title}</a>'.format(
            title=self.show_title(),
            content=Markup.escape(render_template("talk-knowl.html", talk=self)),
        )

    def show_lang_topics(self):
        if self.language and self.language != "en":
            ldict = languages_dict()
            language = '<span class="language_label">%s</span>' % ldict.get(self.language, "Unknown language")
        else:
            language = ""
        if self.topics:
            subjects = set(topic.split("_", 1)[0] for topic in self.topics)
            tdict = topic_dict(include_subj=(len(subjects) > 1))
            return language + "".join('<span class="topic_label">%s</span>' % tdict[topic] for topic in self.topics)
        else:
            return language

    def show_seminar(self, external=False):
        return self.seminar.show_name(external=external)

    def show_speaker(self, affiliation=True):
        # As part of a list
        ans = ""
        if self.speaker:
            if self.speaker_homepage:
                ans += '<a href="%s">%s</a>' % (self.speaker_homepage, self.speaker)
            else:
                ans += self.speaker
            if affiliation and self.speaker_affiliation:
                ans += " (%s)" % (self.speaker_affiliation)
        return ans

    def show_speaker_and_seminar(self, external=False):
        # On homepage
        ans = ""
        if self.speaker:
            ans += "by " + self.show_speaker()
        if self.seminar.name:
            ans += " as part of %s" % (self.show_seminar(external=external))
        return ans

    def show_live_link(self, user=current_user, raw=False):
        if not self.live_link:
            return ""
        if raw:
            success = self.live_link
        else:
            if self.live_link.startswith("http"):
                if self.is_starting_soon():
                    success = '<div class="access_button is_link starting_soon"><b> <a href="%s"> Livestream access <i class="play filter-white"></i> </a></b></div>' % self.live_link
                else:
                    success = '<div class="access_button is_link">Livestream access <a href="%s">available</a></div>' % self.live_link
            else:
                if self.is_starting_soon():
                    success = '<div class="access_button no_link starting_soon"><b>Livestream access: %s </b></div>' % self.live_link
                else:
                    success = '<div class="access_button no_link">Livestream access: %s</div>' % self.live_link
        if self.access == "open":
            return success
        elif self.access == "users":
            if user.is_anonymous:
                return '<div class="access_button no_link">To see access link, please <a href="%s">log in</a> (anti-spam measure).</b></div>' % (
                    url_for("user.info")
                )
            elif not user.email_confirmed:
                return '<div class="access_button no_link">To see access link, please confirm your email.</div>'
            else:
                return success
        elif self.access == "endorsed":
            if user.is_creator:
                return success
            else:
                # TODO: add link to an explanation of endorsement
                return '<div class="access_button no_link">To see access link, you must be endorsed by another user.</div>'
        else:  # should never happen
            return ""

    def show_paper_link(self):
        return '<a href="%s">paper</a>'%(self.paper_link) if self.paper_link else ""

    def show_slides_link(self):
        return '<a href="%s">slides</a>'%(self.slides_link) if self.slides_link else ""

    def show_video_link(self):
        return '<a href="%s">video</a>'%(self.video_link) if self.video_link else ""

    def is_past(self):
        return self.end_time < datetime.datetime.now(pytz.utc)

    def is_starting_soon(self):
        now = datetime.datetime.now(pytz.utc)
        return (self.start_time - datetime.timedelta(minutes=15) <= now < self.end_time)

    def is_subscribed(self):
        if current_user.is_anonymous:
            return False
        if self.seminar_id in current_user.seminar_subscriptions:
            return True
        return self.seminar_ctr in current_user.talk_subscriptions.get(self.seminar_id, [])

    def details_link(self):
        # Submits the form and redirects to create.edit_talk
        return (
            '<button type="submit" class="aslink" name="detailctr" value="%s">Details</button>'
            % self.seminar_ctr
        )

    def user_can_delete(self):
        # Check whether the current user can delete the talk
        return self.user_can_edit()

    def user_can_edit(self):
        # Check whether the current user can edit the talk
        # See can_edit_seminar for another permission check
        # that takes a seminar's shortname as an argument
        # and returns various error messages if not editable
        return (
            current_user.is_subject_admin(self)
            or current_user.email_confirmed
            and (
                current_user.email.lower() in self.seminar.editors()
                or (self.speaker_email and current_user.email and
                    current_user.email.lower() == self.speaker_email.lower())
            )
        )

    def delete(self):
        if self.user_can_delete():
            with DelayCommit(db):
                db.talks.update({"seminar_id": self.seminar_id, "seminar_ctr": self.seminar_ctr},
                                {"deleted": True})
                for i, talk_sub in db._execute(
                    SQL("SELECT {},{} FROM {} WHERE {} ? %s").format(
                        *map(
                            IdentifierWrapper,
                            ["id", "talk_subscriptions", "users", "talk_subscriptions"],
                        )
                    ),
                    [self.seminar.shortname],
                ):
                    if self.seminar_ctr in talk_sub[self.seminar.shortname]:
                        talk_sub[self.seminar.shortname].remove(self.seminar_ctr)
                        db.users.update({"id": i}, {"talk_subscriptions": talk_sub})
            return True
        else:
            return False

    def show_subscribe(self):
        if current_user.is_anonymous:
            return ""

        value = "{sem}/{ctr}".format(sem=self.seminar_id, ctr=self.seminar_ctr)
        return toggle(
            tglid="tlg" + value, value=value, checked=self.is_subscribed(), classes="subscribe"
        )

    def oneline(self, include_seminar=True, include_subscribe=True, tz=None):
        cols = []
        cols.append(('class="date"', self.show_date(tz=tz)))
        cols.append(('class="time"', self.show_start_time(tz=tz)))
        if include_seminar:
            cols.append(('class="seminar"', self.show_seminar()))
        cols.append(('class="speaker"', self.show_speaker(affiliation=False)))
        cols.append(('class="talktitle"', self.show_knowl_title()))
        if include_subscribe:
            cols.append(('class="subscribe"', self.show_subscribe()))
        cols.append(('style="display: none;"', self.show_link_title()))
        return "".join("<td %s>%s</td>" % c for c in cols)

    def show_comments(self):
        if self.comments:
            return "\n".join("<p>%s</p>\n" % (elt) for elt in make_links(self.comments).split("\n\n"))
        else:
            return ""

    def show_abstract(self):
        if self.abstract:
            return "<p><b>Abstract</b></p>\n" + "\n".join("<p>%s</p>\n" % (elt) for elt in make_links(self.abstract).split("\n\n"))
        else:
            return "<p>Abstract TBA</p>"

    def speaker_link(self):
        return url_for("create.edit_talk_with_token",
                       seminar_id=self.seminar_id,
                       seminar_ctr=self.seminar_ctr,
                       token=self.token,
                       _external=True, _scheme='https')

    def send_speaker_link(self):
        """
        Creates a mailto link with instructions on editing the talk.
        """
        data = {
            "body": "Dear %s,\n\nYou can edit your upcoming talk using the following link:\n%s\n\nBest,\n%s"
            % (self.speaker, self.speaker_link(), current_user.name),
            "subject": "%s: title and abstract" % self.seminar.name,
        }
        email_to = self.speaker_email if self.speaker_email else ""
        return """
<p style="margin-bottom: 0px;">
 To let someone edit this page, send them this link:
</p>
<p style="margin-left: 20px; margin-top: 0px;">
<span class="noclick">{link}</span>
<button onClick="window.open('mailto:{email_to}?{msg}')" style="margin-left:20px;">
Email link to speaker
</button></p>""".format(
            link=self.speaker_link(), email_to=email_to, msg=urlencode(data, quote_via=quote),
        )

    def event(self, user):
        event = Event()
        event.add("summary", self.speaker)
        event.add("dtstart", adapt_datetime(self.start_time, pytz.UTC))
        event.add("dtend", adapt_datetime(self.end_time, pytz.UTC))
        desc = ""
        # Title
        if self.title:
            desc += "Title: %s\n" % (self.title)
        # Speaker and seminar
        desc += "by %s" % (self.speaker)
        if self.speaker_affiliation:
            desc += " (%s)" % (self.speaker_affiliation)
        if self.seminar.name:
            desc += " as part of %s" % (self.seminar.name)
        desc += "\n\n"
        if self.live_link:
            link = self.show_live_link(user=user, raw=True)
            if link.startswith("http"):
                desc += "Access: %s\n" % (link)
                event.add("url", link)
        if self.room:
            desc += "Lecture held in %s.\n" % self.room
        if self.abstract:
            desc += "\nAbstract\n%s\n" % self.abstract
        else:
            desc += "Abstract: TBA\n"
        if self.comments:
            desc += "\n%s\n" % (self.comments)

        event.add("description", desc)
        if self.room:
            event.add("location", "Lecture held in {}".format(self.room))
        event.add("DTSTAMP", datetime.datetime.now(tz=pytz.UTC))
        event.add("UID", "%s/%s" % (self.seminar_id, self.seminar_ctr))
        return event

def talks_header(include_seminar=True, include_subscribe=True, datetime_header="Your time"):
    cols = []
    cols.append((' colspan="2" class="yourtime"', datetime_header))
    if include_seminar:
        cols.append((' class="seminar"', "Series"))
    cols.append((' class="speaker"', "Speaker"))
    cols.append((' class="title"', "Title"))
    if include_subscribe:
        if current_user.is_anonymous:
            cols.append(("", ""))
        else:
            cols.append((' class="saved"', "Saved"))
    return "".join("<th%s>%s</th>" % c for c in cols)


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
            return redirect(url_for("show_seminar", shortname=seminar_id), 302), None
    if seminar_ctr != "":
        talk = talks_lookup(seminar_id, seminar_ctr)
        if talk is None:
            flash_error("Talk does not exist")
            return redirect(url_for("show_seminar", shortname=seminar_id), 302), None
        if token:
            if token != talk.token:
                flash_error("Invalid token for editing talk")
                return (
                    redirect(url_for("show_talk", semid=seminar_id, talkid=seminar_ctr), 302),
                    None,
                )
        else:
            if not talk.user_can_edit():
                flash_error(
                    "You do not have permission to edit talk %s/%s." % (seminar_id, seminar_ctr)
                )
                return (
                    redirect(url_for("show_talk", semid=seminar_id, talkid=seminar_ctr), 302),
                    None,
                )
    else:
        resp, seminar = can_edit_seminar(seminar_id, new=False)
        if resp is not None:
            return resp, None
        if seminar.new:
            # TODO: This is where you might insert the ability to create a talk without first making a seminar
            flash_error("You must first create the seminar %s" % seminar_id)
            return redirect(url_for(".edit_seminar", shortname=seminar_id), 302)
        if new:
            talk = WebTalk(seminar_id, seminar=seminar, editing=True)
        else:
            talk = WebTalk(seminar_id, seminar_ctr, seminar=seminar)
    return None, talk


_selecter = SQL(
    "SELECT {0} FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {1} FROM {2} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{3}"
)
_counter = SQL(
    "SELECT COUNT(*) FROM (SELECT 1 FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {0} FROM {1} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{2}) tmp2"
)
_maxer = SQL(
    "SELECT MAX({0}) FROM (SELECT DISTINCT ON (seminar_id, seminar_ctr) {1} FROM {2} ORDER BY seminar_id, seminar_ctr, id DESC) tmp{3}"
)


def _construct(seminar_dict):
    def inner_construct(rec):
        # The following would break if we had jsonb columns holding dictionaries in the talks table,
        # but that's not currently true.
        if not isinstance(rec, dict):
            return rec
        else:
            return WebTalk(
                rec["seminar_id"],
                rec["seminar_ctr"],
                seminar=seminar_dict.get(rec["seminar_id"]),
                data=rec,
            )

    return inner_construct


def _iterator(seminar_dict):
    def inner_iterator(cur, search_cols, extra_cols, projection):
        for rec in db.talks._search_iterator(cur, search_cols, extra_cols, projection):
            yield _construct(seminar_dict)(rec)

    return inner_iterator


def talks_count(query={}, include_deleted=False):
    """
    Replacement for db.talks.count to account for versioning and so that we don't cache results.
    """
    return count_distinct(db.talks, _counter, query, include_deleted)


def talks_max(col, constraint={}, include_deleted=False):
    """
    Replacement for db.talks.max to account for versioning and so that we don't cache results.
    """
    return max_distinct(db.talks, _maxer, col, constraint, include_deleted)


def talks_search(*args, **kwds):
    """
    Replacement for db.talks.search to account for versioning, return WebTalk objects.

    Doesn't support split_ors or raw.  Always computes count.
    """
    seminar_dict = kwds.pop("seminar_dict", {})
    return search_distinct(db.talks, _selecter, _counter, _iterator(seminar_dict), *args, **kwds)


def talks_lucky(*args, **kwds):
    """
    Replacement for db.talks.lucky to account for versioning, return a WebTalk object or None.
    """
    seminar_dict = kwds.pop("seminar_dict", {})
    return lucky_distinct(db.talks, _selecter, _construct(seminar_dict), *args, **kwds)


def talks_lookup(seminar_id, seminar_ctr, projection=3, seminar_dict={}, include_deleted=False):
    return talks_lucky(
        {"seminar_id": seminar_id, "seminar_ctr": seminar_ctr},
        projection=projection,
        seminar_dict=seminar_dict,
        include_deleted=include_deleted,
    )
