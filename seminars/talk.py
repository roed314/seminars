import pytz
import secrets
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
    make_links,
    sanitized_table,
    how_long,
    topdomain,
    comma_list,
    log_error,
    SPEAKER_DELIMITER,
)
from seminars.language import languages
from seminars.toggle import toggle
from seminars.topic import topic_dag
from seminars.seminar import WebSeminar, can_edit_seminar, audience_options
from lmfdb.utils import flash_error
from markupsafe import Markup
from psycopg2.sql import SQL
import urllib.parse
from icalendar import Event
from lmfdb.logger import critical
from datetime import datetime, timedelta
import re

blackout_dates = [ # Use %Y-%m-%d format
    "2020-06-10",
]

required_talk_columns = [
    "audience",
    "by_api",
    "display",
    "end_time",
    "online",
    "language",
    "seminar_id",
    "seminar_ctr",
    "start_time",
    "timezone",
    "topics",
]

inherited_talk_columns = [
    "access_control",
    "access_time",
    "access_hint",
    "access_registration",
    "audience",
    "chat_link",
    "display",
    "language",
    "live_link",
    "online",
    "room",
    "stream_link",
    "timezone",
    "topics",
]

optional_talk_text_columns = [
    "abstract",
    "access_hint",
    "access_registration",
    "chat_link",
    "comments",
    "live_link",
    "room",
    "paper_link",
    "slides_link",
    "speaker",
    "speaker_affiliation",
    "speaker_email",
    "speaker_homepage",
    "stream_link",
    "title",
    "video_link",
]

class WebTalk(object):
    def __init__(
        self,
        seminar_id=None,
        seminar_ctr=None,
        data=None,
        seminar=None,
        editing=False,
        include_deleted=False,
        include_pending=False,
    ):
        if data is None and not editing:
            data = talks_lookup(seminar_id, seminar_ctr, include_deleted=include_deleted, include_pending=include_pending)
            if data is None:
                raise ValueError("Talk %s/%s does not exist" % (seminar_id, seminar_ctr))
            data = dict(data.__dict__)
        elif data is not None:
            data = dict(data)
            # avoid Nones
            if data.get("topics") is None:
                data["topics"] = []
        if data and data.get("deleted"):
            include_deleted = True
        if seminar is None:
            seminar = WebSeminar(seminar_id, include_deleted=include_deleted)
        self.seminar = seminar
        self.new = data is None
        if self.new:
            self.seminar_id = seminar_id
            self.seminar_ctr = None
            self.token = secrets.token_hex(8)
            self.by_api = False # reset by API code if needed
            self.timezone = seminar.timezone
            self.deleted = False
            self.deleted_with_seminar = False
            self.hidden = False
            for key, typ in db.talks.col_type.items():
                if key == "id" or hasattr(self, key):
                    continue
                if key in inherited_talk_columns:
                    setattr(self, key, getattr(seminar, key))
                elif typ == "text":
                    setattr(self, key, "")
                elif typ == "text[]":
                    setattr(self, key, [])
                else:
                    # don't complain about columns we know are going to be set later
                    if not key in ["edited_by", "edited_at", "start_time", "end_time"]:
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
            self.__dict__.update(data)
            self.cleanse()

    def __repr__(self):
        title = self.title if self.title else "TBA"
        return "%s (%s) - %s, %s" % (
            title,
            self.show_speaker(raw=True),
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

    def validate(self):
        sts = True
        for col in required_talk_columns:
            if getattr(self, col) is None:
                sts = False
                log_error("column %s is None for talk %s/%s" % (col, self.seminar_id, self.seminar_ctr))
        if not self.topics:
            sts = False
            log_error("No topics set for talk %s/%s" % (self.seminar_id, self.seminar_ctr))
        return sts

    def cleanse(self):
        """
        This function is used to ensure backward compatibility across changes to the schema and/or validation
        This is the only place where columns we plan to drop should be referenced
        """
        for col in optional_talk_text_columns:
            if getattr(self, col) is None:
                setattr(self, col, "")
        self.validate()

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

    def save(self, user=None):
        if user is None: user = current_user
        data = {col: getattr(self, col, None) for col in db.talks.search_cols}
        assert data.get("seminar_id") and data.get("seminar_ctr")
        try:
            data["edited_by"] = int(user.id)
        except (ValueError, AttributeError):
            # Talks can be edited by anonymous users with a token, with no id
            data["edited_by"] = -1
        data["edited_at"] = datetime.now(tz=pytz.UTC)
        self.validate()
        db.talks.insert_many([data])

    def save_admin(self):
        # Like save, but doesn't change edited_at
        data = {col: getattr(self, col, None) for col in db.talks.search_cols}
        assert data.get("seminar_id") and data.get("seminar_ctr")
        data["edited_by"] = 0
        db.talks.insert_many([data])

    def user_is_registered(self, user=None):
        if user is None: user = current_user
        if user.is_anonymous:
            return False
        rec = {'seminar_id': self.seminar_id, 'seminar_ctr': self.seminar_ctr, 'user_id': int(user.id)}
        return True if db.talk_registrations.count(rec) else False

    def register_user(self, user=None):
        if user is None: user = current_user
        rec = {'seminar_id': self.seminar_id, 'seminar_ctr': self.seminar_ctr, 'user_id': int(user.id)}
        if db.talk_registrations.count(rec):
            return False
        reg = rec
        reg["registration_time"] = datetime.now(tz=pytz.UTC)
        return db.talk_registrations.upsert(rec,reg)

    def registered_users(self):
        """ returns a list of tuples (name, affiliation, homepage, email, registration_time) in reverse order by registration time """
        # FIXME: Should we use IdentifierWrapper here?
        query = """
            SELECT users.name, users.homepage, users.affiliation, talk_registrations.registration_time
            FROM talk_registrations INNER JOIN users ON users.id = talk_registrations.user_id
            WHERE talk_registrations.seminar_id = '%s' AND talk_registrations.seminar_ctr = %d
            ORDER BY talk_registrations.registration_time DESC
        """
        return list(db._execute(SQL(query % (self.seminar_id, self.seminar_ctr))))

    def show_audience(self):
        return audience_options[self.audience][1]

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

    def show_daytimes(self, tz=None):
        return adapt_datetime(self.start_time, tz).strftime("%H:%M") + "-" + adapt_datetime(self.end_time, tz).strftime("%H:%M")

    def show_date(self, tz=None):
        format = "%a %b %-d" if adapt_datetime(self.start_time, newtz=tz).year == datetime.now(tz).year else "%d-%b-%Y"
        return adapt_datetime(self.start_time, newtz=tz).strftime(format)

    def blackout_date(self):
        return adapt_datetime(self.start_time, newtz=self.tz).strftime("%Y-%m-%d") in blackout_dates

    def show_time_and_duration(self, adapt=True, tz=None):
        start = self.start_time
        end = self.end_time
        now = datetime.now(pytz.utc)
        newtz = tz if adapt else self.tz

        def ans(rmk):
            format = "%a %b %-d, %H:%M" if adapt_datetime(self.start_time, newtz=tz).year == datetime.now(tz).year else "%d-%b-%Y, %H:%M"
            return "%s-%s (%s)" % (
                adapt_datetime(start, newtz=newtz).strftime(format),
                adapt_datetime(end, newtz=newtz).strftime("%H:%M"),
                rmk,
            )

        # Add remark on when this is
        if start <= now <= end:
            return ans("ongoing")
        elif now < start:
            delta = start - now
            return ans("starts in " + how_long(delta)) if delta < timedelta(hours=36) else ans(how_long(delta) + " from now")
        else:
            delta = now - end
            return ans("ended " + how_long(delta) + " ago") if delta < timedelta(hours=36) else ans(how_long(delta) + " ago")

    def show_title(self, visibility_info=False):
        title = self.title if self.title else "TBA"
        if visibility_info:
            if not self.display:
                title += " (hidden)"
            elif self.hidden:
                title += " (private)"
            elif self.seminar.visibility == 0:
                title += " (series private)"
            elif self.seminar.visibility == 1:
                title += " (series unlisted)"
            #elif self.online:
            #    title += " (online)"
        return title

    def show_link_title(self):
        return "<a href={url}>{title}</a>".format(
            url=url_for("show_talk", seminar_id=self.seminar_id, talkid=self.seminar_ctr),
            title=self.show_title(),
        )

    def show_knowl_title(self, _external=False, rescheduled=False, blackout=False, preload=False, tz=None):
        if self.deleted or _external or preload:
            return r'<a title="{title}" knowl="dynamic_show" kwargs="{content}">{title}</a>'.format(
                title=self.show_title(),
                content=Markup.escape(render_template("talk-knowl.html", talk=self, _external=_external, tz=tz)),
            )
        else:
            return r'<a title="{title}" knowl="talk/{seminar_id}/{talkid}" {style}>{title}</a>{rescheduled}'.format(
                title=self.show_title(),
                style='style="text-decoration: line-through;font-style: italic;"' if rescheduled else '',
                seminar_id=self.seminar_id,
                talkid=self.seminar_ctr,
                rescheduled=' (rescheduled)' if rescheduled else '',
            )

    def show_lang_topics(self):
        if self.language and self.language != "en":
            language = '<span class="language_label">%s</span>' % languages.show(self.language)
        else:
            language = ""
        if self.topics:
            try:
                return language + "".join('<span class="topic_label">%s</span>' % topic for topic in topic_dag.leaves(self.topics))
            except Exception as err:
                log_error("Hit exception %s in show_lang_topics for talk %s/%d" % (err, self.seminar_id, self.seminar_ctr))
                return language
        else:
            return language

    def show_seminar(self, external=False):
        return self.seminar.show_name(external=external)

    # speaker fields may be SPEAKER_DELIMITER delimited lists (we cannot use commas or semicolons!)
    def show_speaker(self, raw=False, affiliation=True):
        # As part of a list
        speakers = [s.strip() for s in self.speaker.split(SPEAKER_DELIMITER)]
        if not speakers:
            return ''
        homepages = [s.strip() for s in self.speaker_homepage.split(SPEAKER_DELIMITER)]
        for i in range(len(speakers)-len(homepages)):
            homepages.append('')
        affiliations = [s.strip() for s in self.speaker_affiliation.split(SPEAKER_DELIMITER)] if affiliation else []
        for i in range(len(speakers)-len(affiliations)):
            affiliations.append('')
        items = []
        for i in range(len(speakers)):
            item = '<a href="%s">%s</a>' % (homepages[i],speakers[i]) if homepages[i] and not raw else speakers[i]
            item += (" (%s)" % affiliations[i]) if affiliations[i] else ''
            items.append(item)
        return comma_list(items)

    def show_speaker_and_seminar(self, external=False):
        # On homepage
        ans = ""
        if self.speaker:
            ans += "by " + self.show_speaker()
        if self.seminar.name:
            ans += " as part of %s" % (self.show_seminar(external=external))
        return ans

    def show_password_hint(self):
        if all([not self.deleted, self.online, self.access_control==2, self.live_link, self.access_hint]):
            return '<div class="access_button_hint">(Password: %s)</div>' % self.access_hint
        else:
            return ""

    def show_stream_link(self, user=None, raw=False):
        if any([self.deleted, not self.online, not self.stream_link, self.is_past()]):
            return ""
        link = self.stream_link
        if raw:
            return link
        if self.is_starting_soon():
            return '<div class="access_button is_link view_only"><b> <a href="%s">Watch livestream <i class="play filter-white"></i></a></b></div>' % link
        else:
            return '<div class="access_button is_link">View-only livestream access <a href="%s">available</a></div>' % link

    def show_live_link(self, user=None, raw=False):
        if user is None: user = current_user
        now = datetime.now(pytz.utc)
        if any([self.deleted, not self.online, self.is_past()]):
            return ""
        link = self.live_link

        def show_link(self, user=None, raw=False):
            if user is None: user = current_user
            link = self.live_link
            if raw:
                return link if link else ''
            if not link:
                return '<div class=access_button no_link">Livestream link not yet posted by organizers</div>'
            if self.access_control == 4 and not self.user_is_registered(user):
                link = url_for("register_for_talk", seminar_id=self.seminar_id, talkid=self.seminar_ctr)
                if self.is_starting_soon():
                    return '<div class="access_button is_link starting_soon"><b> <a href="%s">Instantly register and join livestream <i class="play filter-white"></i> </a></b></div>' % link
                else:
                    return '<div class="access_button is_link"> <a href="%s">Instantly register</a> for livestream access</div>' % link
            if self.is_starting_soon():
                return '<div class="access_button is_link starting_soon"><b> <a href="%s">Join livestream <i class="play filter-white"></i> </a></b></div>' % link
            else:
                return '<div class="access_button is_link"> Livestream access <a href="%s">available</a></div>' % link

        if self.access_control in [0,2]: # password hint will be shown nearby, not our problem
            return show_link(self, user=user, raw=raw)
        elif self.access_control == 1:
            show_link_time = self.start_time - timedelta(minutes=self.access_time)
            if show_link_time <= now:
                return show_link(self, user=user, raw=raw)
            else:
                return "" if raw else '<div class="access_button no_link">Livestream access available in %s</div>' % how_long(show_link_time-now)
        elif self.access_control == 2:
            return show_link(self, user=user, raw=raw)
        elif self.access_control in [3,4]:
            if raw:
                return url_for("show_talk", seminar_id=self.seminar_id, talkid=self.seminar_ctr)
            if user.is_anonymous:
                link = url_for("user.info", next=url_for("register_for_talk", seminar_id=self.seminar_id, talkid=self.seminar_ctr))
                return '<div class="access_button no_link"><a href="%s">Login required</a> for livestream access</b></div>' % link
            elif not user.email_confirmed:
                return '<div class="access_button no_link">Please confirm your email address for livestream access</div>'
            else:
                return show_link(self, user=user, raw=raw)
        elif self.access_control == 5:
            if not user.is_anonymous and db.seminar_registrations.lucky({'seminar_id':self.seminar_id,'email':user.email}):
                if not user.email_confirmed:
                    return '<div class="access_button no_link">Please confirm your email address for livestream access</div>'
                else:
                    return show_link(self, user=user, raw=raw)
            # If there is a view-only link, show that rather than an external registration link
            if raw:
                return url_for("show_talk", seminar_id=self.seminar_id, talkid=self.seminar_ctr)
            if not self.access_registration:
                # This should never happen, registration link is required, but just in case...
                return "" if raw else '<div class="access_button no_link">Registration required, see comments or external site.</a></div>' % link
            if "@" in self.access_registration:
                body = """Dear organizers,

I am interested in attending the talk

    {talk}

by {speaker}, in the series

    {series}

listed at https://{domain}{url}.

Thank you,

{user}
""".format(
                    talk = self.title,
                    speaker = self.show_speaker(raw=True),
                    series = self.seminar.name,
                    domain = topdomain(),
                    url = url_for('show_talk', seminar_id=self.seminar.shortname, talkid=self.seminar_ctr),
                    user = user.name)
                msg = { "body": body, "subject": "Request to attend %s" % self.seminar.shortname }
                link = "mailto:%s?%s" % (self.access_registration, urlencode(msg, quote_via=quote))
            else:
                link = self.access_registration
            return '<div class="access_button no_link"><a href="%s">Register</a> for livestream access</div>' % link
        else:  # should never happen
            log_error("invalid or unknown access control value %s for talk %s/%s" % (self.access_control, self.seminar_id, self.seminar_ctr))
            return ""

    def show_paper_link(self):
        return '<a href="%s">paper</a>'%(self.paper_link) if self.paper_link else ""

    def show_slides_link(self):
        return '<a href="%s">slides</a>'%(self.slides_link) if self.slides_link else ""

    def show_video_link(self):
        return '<a href="%s">video</a>'%(self.video_link) if self.video_link else ""

    def show_chat_link(self):
        return '<a href="%s">chat</a>'%(self.chat_link) if self.chat_link else ""

    def show_content_links(self):
        s = ' | '.join(filter(None, [self.show_chat_link(), self.show_paper_link(), self.show_slides_link(), self.show_video_link()])) 
        return '( ' + s + ' )' if s else ''

    @property
    def ics_link(self):
        return url_for("ics_talk_file", seminar_id=self.seminar_id, talkid=self.seminar_ctr,
                       _external=True, _scheme="https")

    @property
    def ics_gcal_link(self):
        return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(
            {"cid": url_for("ics_talk_file", seminar_id=self.seminar_id, talkid=self.seminar_ctr,
                            _external=True, _scheme="http")}
        )

    @property
    def ics_webcal_link(self):
        return url_for("ics_talk_file", seminar_id=self.seminar_id, talkid=self.seminar_ctr,
                       _external=True, _scheme="webcal")

    def is_past(self):
        now = datetime.now(pytz.utc)
        return (now - timedelta(minutes=60) > self.end_time)

    def is_starting_soon(self):
        now = datetime.now(pytz.utc)
        return (self.start_time - timedelta(minutes=15) <= now < self.end_time)

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
                    current_user.email.lower() in self.speaker_email.lower())
            )
        )

    def delete(self):
        if self.user_can_delete():
            with DelayCommit(db):
                db.talks.delete({"seminar_id": self.seminar_id, "seminar_ctr": -self.seminar_ctr})
                db.talks.update({"seminar_id": self.seminar_id, "seminar_ctr": self.seminar_ctr},
                                {"deleted": True, "deleted_with_seminar": False})
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
            self.deleted = True
            return True
        else:
            return False

    def show_subscribe(self):
        if current_user.is_anonymous:
            return ""

        name = "{sem}/{ctr}".format(sem=self.seminar_id, ctr=self.seminar_ctr)
        return toggle(
            tglid="tlg" + name.replace('/','--'),
            name=name,
            value=1 if self.is_subscribed() else -1,
            classes="subscribe"
        )

    def rescheduled(self):
        """
        Return True if this talk has been rescheduled to another time.
        """
        # We currently indicate that a talk has been rescheduled by giving it a negative seminar_ctr; the version with the new time will have id equal to the absolute value.
        return self.seminar_ctr < 0

    def oneline(self, include_seminar=True, include_content=False, include_subscribe=True, tz=None, _external=False):
        rescheduled = self.rescheduled()
        t, now, e = adapt_datetime(self.start_time, newtz=tz), adapt_datetime(datetime.now(), newtz=tz), adapt_datetime(self.end_time, newtz=tz)
        if rescheduled:
            datetime_tds = t.strftime('<td class="weekday rescheduled">%a</i></td><td class="monthdate rescheduled">%b %d</td><td class="time rescheduled"><i>%H:%M</i></td>')
        else:
            if t < now < e:
                datetime_tds = t.strftime('<td class="weekday">%a</td><td class="monthdate">%b %d</td><td class="time"><b>%H:%M</b></td>')
            else:
                datetime_tds = t.strftime('<td class="weekday">%a</td><td class="monthdate">%b %d</td><td class="time">%H:%M</td>')
        cols = []
        rclass = " rescheduled" if rescheduled else ""
        if include_seminar:
            cols.append(('class="seriesname%s"'%rclass, self.show_seminar()))
        cols.append(('class="speaker%s"'%rclass, self.show_speaker(affiliation=False)))
        new_talk = talks_lookup(self.seminar_id, -self.seminar_ctr) if rescheduled else self
        cols.append(('class="talktitle"', new_talk.show_knowl_title(_external=_external, rescheduled=rescheduled, blackout=self.blackout_date(), tz=tz)))
        if include_content:
            cols.append(('', self.show_slides_link()))
            cols.append(('', self.show_video_link()))
            cols.append(('', self.show_paper_link()))
        if include_subscribe:
            if rescheduled:
                cols.append(("", ""))
            else:
                cols.append(('class="subscribe"', self.show_subscribe()))
        return datetime_tds + ''.join('<td %s>%s</td>' % c for c in cols)

    def show_comments(self, prefix=""):
        if self.comments:
            return "\n".join("<p>%s</p>\n" % (elt) for elt in make_links(prefix + self.comments).split("\n\n"))
        else:
            return ""

    def show_abstract(self):
        return "\n".join("<p>%s</p>\n" % (elt) for elt in make_links("<b>Abstract: </b>" + self.abstract).split("\n\n")) if self.abstract else ""

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
            % (self.show_speaker(raw=True), self.speaker_link(), current_user.name),
            "subject": "%s: title and abstract" % self.seminar.name,
        }
        email_to = ';'.join(self.speaker_email.split(SPEAKER_DELIMITER)) if self.speaker_email else ""
        return """
<p>
 To let someone edit this page, send them this link:
<input type="text" id="speaker-link" value="{link}" class="noclick" readonly onclick="this.focus();this.select()"></input>
<a><i class="clippy" onclick="copySourceOfId('speaker-link')"></i></a>
<button onClick="window.open('mailto:{email_to}?{msg}')" style="margin-left:20px;">
Email link to speaker
</button>
</p>""".format(
            link=self.speaker_link(), email_to=email_to, msg=urlencode(data, quote_via=quote),
        )

    def event(self, user):
        event = Event()
        #FIXME: code to remove hrefs from speaker name is a temporary hack to be
        # removed once we support multiple speakers
        if "href=" in self.speaker:
            tokens = re.split(r'>([a-zA-Z ]*)', self.speaker)
            speaker = ', '.join([tokens[i] for i in range(1,len(tokens),2) if tokens[i].strip()])
        else:
            speaker = self.show_speaker(raw=True)
        event.add("summary", speaker)
        event.add("dtstart", adapt_datetime(self.start_time, pytz.UTC))
        event.add("dtend", adapt_datetime(self.end_time, pytz.UTC))
        desc = ""
        # Title
        if self.title:
            desc += "Title: %s\n" % (self.title)
        # Speaker and seminar
        desc += "by %s" % (speaker)
        if self.seminar.name:
            desc += " as part of %s" % (self.seminar.name)
        desc += "\n\n"
        if self.live_link:
            link = self.show_live_link(user=user, raw=True)
            if link.startswith("http"):
                desc += "Interactive livestream: %s\n" % link
                if self.access_control == 2 and self.access_hint:
                    desc += "Password hint: %s\n" % self.access_hint
                event.add("url", link)
        if self.stream_link:
            link = self.show_stream_link(user=user, raw=True)
            if link.startswith("http"):
                desc += "View-only livestream: %s\n" % link
                event.add("url", link)
        if self.room:
            desc += "Lecture held in %s.\n" % self.room
        if self.abstract:
            desc += "\nAbstract\n%s\n" % self.abstract
        else:
            desc += "Abstract: TBA\n"
        if self.comments:
            desc += "\n%s\n" % self.comments

        event.add("description", desc)
        if self.room:
            event.add("location", "Lecture held in {}".format(self.room))
        event.add("DTSTAMP", datetime.now(tz=pytz.UTC))
        event.add("UID", "%s/%s" % (self.seminar_id, self.seminar_ctr))
        return event

def talks_header(include_seminar=True, include_content=False, include_subscribe=True, datetime_header="Your time"):
    cols = []
    cols.append((' colspan="3" class="yourtime"', datetime_header))
    if include_seminar:
        cols.append((' class="seminar"', "Series"))
    cols.append((' class="speaker"', "Speaker"))
    cols.append((' class="title"', "Title"))
    if include_content:
        cols.append((' colspan="3"', "Content"))
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
        talk = talks_lookup(seminar_id, seminar_ctr, include_deleted=True)
        if talk is None:
            flash_error("Talk does not exist")
            return redirect(url_for("show_seminar", shortname=seminar_id), 302), None
        if talk.deleted:
            flash_error("Talk has been deleted, but you can revive it (use Show deleted items below)")
            return redirect(url_for("create.index", shortname=seminar_id), 302), None
        if token:
            if token != talk.token:
                flash_error("Invalid token for editing talk")
                return redirect(url_for("show_talk", seminar_id=seminar_id, talkid=seminar_ctr), 302), None
        else:
            if not talk.user_can_edit():
                flash_error("You do not have permission to edit talk %s/%s." % (seminar_id, seminar_ctr))
                return redirect(url_for("show_talk", seminar_id=seminar_id, talkid=seminar_ctr), 302), None
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


def _construct(seminar_dict, objects=True, more=False):
    def object_construct(rec):
        if not isinstance(rec, dict):
            return rec
        else:
            if more is not False:
                moreval = rec.pop("more")
            talk = WebTalk(
                rec["seminar_id"],
                rec["seminar_ctr"],
                seminar=seminar_dict.get(rec["seminar_id"]),
                data=rec,
            )
            if more is not False:
                talk.more = moreval
            return talk
    def default_construct(rec):
        return rec

    return object_construct if objects else default_construct


def _iterator(seminar_dict, objects=True, more=False):
    def object_iterator(cur, search_cols, extra_cols, projection):
        for rec in db.talks._search_iterator(cur, search_cols, extra_cols, projection):
            yield _construct(seminar_dict, more=more)(rec)

    return object_iterator if objects else db.talks._search_iterator


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
    objects = kwds.pop("objects", True)
    sanitized = kwds.pop("sanitized", False)
    if sanitized:
        table = sanitized_table("talks")
    else:
        table = db.talks
    more = kwds.get("more", False)
    return search_distinct(table, _selecter, _counter, _iterator(seminar_dict, objects=objects, more=more), *args, **kwds)


def talks_lucky(*args, **kwds):
    """
    Replacement for db.talks.lucky to account for versioning, return a WebTalk object or None.
    """
    seminar_dict = kwds.pop("seminar_dict", {})
    objects = kwds.pop("objects", True)
    sanitized = kwds.pop("sanitized", False)
    if sanitized:
        table = sanitized_table("talks")
    else:
        table = db.talks
    return lucky_distinct(table, _selecter, _construct(seminar_dict, objects=objects), *args, **kwds)


def talks_lookup(seminar_id, seminar_ctr, projection=3, seminar_dict={}, include_deleted=False, include_pending=False, sanitized=False, objects=True):
    return talks_lucky(
        {"seminar_id": seminar_id, "seminar_ctr": seminar_ctr},
        projection=projection,
        seminar_dict=seminar_dict,
        include_deleted=include_deleted,
        include_pending=include_pending,
        sanitized=sanitized,
        objects=objects,
    )
