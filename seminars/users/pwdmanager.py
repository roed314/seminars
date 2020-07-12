#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import print_function
from __future__ import absolute_import
import bcrypt
import urllib.parse
from seminars import db
from seminars.tokens import generate_token
from seminars.seminar import WebSeminar, seminars_search, seminars_lucky, next_talk_sorted
from seminars.talk import WebTalk
from seminars.utils import pretty_timezone, log_error
from lmfdb.backend.searchtable import PostgresSearchTable
from lmfdb.utils import flash_error
from flask import flash
from lmfdb.backend.utils import DelayCommit
from lmfdb.logger import critical
from datetime import datetime
from pytz import UTC, all_timezones, timezone, UnknownTimeZoneError
import bisect
import secrets
from .main import logger

# Read about flask-login if you are unfamiliar with this UserMixin/Login
from flask_login import UserMixin, AnonymousUserMixin
from flask import request, url_for
from email_validator import validate_email, EmailNotValidError


def ilike_escape(email):
    # only do this after validation
    assert "\\" not in email
    return email.replace("%", r"\%").replace("_", r"\_")


def ilike_query(email):
    if isinstance(email, str):
        return {"$ilike": ilike_escape(email)}
    else:
        # no email, no query
        return None


class PostgresUserTable(PostgresSearchTable):
    def __init__(self):
        PostgresSearchTable.__init__(
            self, db=db, search_table="users", label_col="email", include_nones=True
        )
        # FIXME
        self._rw_userdb = db.can_read_write_userdb()

    def log_db_change(self, what, **kwargs):
        " no need to log the changes "
        # FIXME: also the logger can't handle bytes
        pass

    def can_read_write_userdb(self):
        return self._rw_userdb

    def bchash(self, pwd, existing_hash=None):
        """
        Generate a bcrypt based password hash.
        """
        if not existing_hash:
            existing_hash = bcrypt.gensalt().decode("utf-8")
        return bcrypt.hashpw(pwd.encode("utf-8"), existing_hash.encode("utf-8")).decode("utf-8")

    def new_user(self, **kwargs):
        """
        Creates a new user.
        Required keyword arguments:
            - email
            - password
            - name
            - affiliation
        """
        for col in ["email", "password"]:
            assert col in kwargs
        email = kwargs["email"] = validate_email(kwargs["email"])["email"]
        kwargs["password"] = self.bchash(kwargs["password"])
        if "endorser" not in kwargs:
            kwargs["endorser"] = None
            kwargs["admin"] = kwargs["creator"] = False
        if "subject_admin" not in kwargs:
            kwargs["subject_admin"] = None
        for col in ["email_confirmed", "admin", "creator"]:
            kwargs[col] = kwargs.get(col, False)
        kwargs["talk_subscriptions"] = kwargs.get("talk_subscriptions", {})
        kwargs["seminar_subscriptions"] = kwargs.get("seminar_subscriptions", [])
        for col in ["name", "affiliation", "homepage", "timezone"]:
            kwargs[col] = kwargs.get(col, "")
        tz = kwargs.get("timezone", "")
        assert tz == "" or tz in all_timezones
        kwargs["api_access"] = kwargs.get("api_access", 0)
        kwargs["api_token"] = kwargs.get("api_token", secrets.token_urlsafe(32))
        kwargs["created"] = datetime.now(UTC)
        if "external_ids" not in kwargs:
            kwargs["external_ids"] = []
        if sorted(list(kwargs) + ['id']) != sorted(self.col_type):
            log_error("Columns for user creation do not match, %s != %s" % (sorted(list(kwargs) + ['id']), sorted(self.col_type)))
        self.insert_many([kwargs], restat=False)
        newuser = SeminarsUser(email=email)
        return newuser

    def change_password(self, email, newpwd):
        self.update(
            query={"email": ilike_query(email)},
            changes={"password": self.bchash(newpwd)},
            resort=False,
            restat=False,
        )
        logger.info("password for %s changed!" % email)

    def lookup(self, email, projection=2):
        if not email:
            return None
        return self.lucky({"email": ilike_query(email)}, projection=projection, sort=[])

    def user_exists(self, email):
        if not email:
            return False
        return self.lucky({"email": ilike_query(email)}, projection="id") is not None

    def authenticate(self, email, password):
        bcpass = self.lookup(email, projection="password")
        if bcpass is None:
            raise ValueError("User not present in database!")
        return bcpass == self.bchash(password, existing_hash=bcpass)

    def make_creator(self, email, endorser):
        with DelayCommit(self):
            db.users.update({"email": ilike_query(email)}, {"creator": True, "endorser": endorser}, restat=False)
            # Update all of this user's created seminars and talks
            db.seminars.update({"owner": ilike_query(email)}, {"display": True})
            # Could do this with a join...
            for sem in seminars_search({"owner": ilike_query(email)}, "shortname"):
                db.talks.update({"seminar_id": sem}, {"display": True}, restat=False)

    def save(self, data):
        data = dict(data)  # copy
        email = data.pop("email", None)
        if not email:
            raise ValueError("data must contain email")
        user = self.lookup(email)
        if not user:
            raise ValueError("user does not exist")
        if not data:
            raise ValueError("no data to save")
        if "new_email" in data:
            data["email"] = data.pop("new_email")
            try:
                # standerdize email
                data["email"] = validate_email(data["email"])["email"]
            except EmailNotValidError as e:
                flash_error("""Oops, email '%s' is not allowed. %s""", data["email"], str(e))
                return False
            if self.user_exists(data["email"]):
                flash_error("There is already a user registered with email = %s", data["email"])
                return False
        for key in list(data):
            if key not in self.search_cols:
                if key != "id":
                    critical("Need to update pwdmanager code to account for schema change key=%s" % key)
                data.pop(key)
        with DelayCommit(db):
            if "email" in data:
                newemail = data["email"]
                db.institutions.update({"admin": ilike_query(email)}, {"admin": newemail})
                db.seminars.update({"owner": ilike_query(email)}, {"owner": newemail})
                db.seminar_organizers.update({"email": ilike_query(email)}, {"email": newemail})
                db.talks.update({"speaker_email": ilike_query(email)}, {"speaker_email": newemail})
            self.update({"email": ilike_query(email)}, data, restat=False)
        return True

    def delete(self, data):
        # We keep the uid in the users table (so that it doesn't get reused), but remove all personal information
        uid = data["id"]
        email = data["email"]
        with DelayCommit(db):
            # We probably have code that assumes that admin/owner isn't None....
            db.institutions.update({"admin": ilike_query(email)}, {"admin": "researchseminars@math.mit.edu"})
            db.seminars.update({"owner": ilike_query(email)}, {"owner": "researchseminars@math.mit.edu"})
            db.seminar_organizers.delete({"email": ilike_query(email)})
            db.talks.update({"speaker_email": ilike_query(email)}, {"speaker_email": ""})
            self.update({"id": uid}, {key: None for key in self.search_cols}, restat=False)

    def reset_api_token(self, uid):
        new_token = secrets.token_urlsafe(32)
        self.update({"id": int(uid)}, {"api_token": new_token}, restat=False)
        return new_token

userdb = PostgresUserTable()


class SeminarsUser(UserMixin):
    """
    The User Object
    """

    properties = sorted(userdb.col_type) + ["id"]

    def __init__(self, uid=None, email=None):
        if email:
            if not isinstance(email, str):
                raise Exception("Email is not a string, %s" % email)
            query = {"email": ilike_query(email)}
        else:
            try:
                query = {"id": int(uid)}
            except ValueError:
                query = {"id": None}

        self._authenticated = False
        self._uid = None
        self._dirty = False  # flag if we have to save
        self._data = dict() # dict([(_, None) for _ in SeminarsUser.properties])

        user_row = userdb.lucky(query, projection=SeminarsUser.properties)
        if user_row:
            self._authenticated = True
            self._data.update(user_row)
            self._uid = str(self._data["id"])
            self._organizer = (
                db.seminar_organizers.count({"email": ilike_query(self.email)}, record=False) > 0
            )
            self.try_to_endorse()

    def try_to_endorse(self):
        if self.email_confirmed and not self.is_creator:
            preendorsed = db.preendorsed_users.lucky({"email": ilike_query(self.email)})
            if preendorsed:
                self.endorser = preendorsed["endorser"]  # must set endorser first
                self.creator = True  # it already saves
                db.preendorsed_users.delete({"email": ilike_query(self.email)})
                return True
            # try to endorse if the user is the organizer of some seminar
            if self._organizer:
                shortname = db.seminar_organizers.lucky({"email": ilike_query(self.email)}, "seminar_id")
                owner = seminars_lucky({"shortname": shortname, "display": True}, "owner")
                if owner:
                    owner = userdb.lookup(owner, ["creator", "id"])
                    if owner and owner.get("creator"):
                        self.endorser = owner["id"]  # must set endorser first
                        self.creator = True  # it already saves
                        return True

        return False

    @property
    def id(self):
        return self._uid

    @property
    def name(self):
        return self._data.get("name", "")

    @name.setter
    def name(self, name):
        self._data["name"] = name
        self._dirty = True

    @property
    def email(self):
        return self._data.get("email", "")

    @email.setter
    def email(self, email):
        if email != self._data.get("email", ""):
            self._data["new_email"] = email
            self._data["email_confirmed"] = False
            self._dirty = True

    @property
    def homepage(self):
        return self._data.get("homepage", "")

    @homepage.setter
    def homepage(self, url):
        self._data["homepage"] = url
        self._dirty = True

    @property
    def email_confirmed(self):
        return self._data.get("email_confirmed", False)

    @email_confirmed.setter
    def email_confirmed(self, email_confirmed):
        self._data["email_confirmed"] = email_confirmed
        if email_confirmed:
            self.try_to_endorse()

        self._dirty = True

    @property
    def affiliation(self):
        return self._data.get("affiliation", "")

    @affiliation.setter
    def affiliation(self, affiliation):
        self._data["affiliation"] = affiliation
        self._dirty = True

    @property
    def timezone(self):
        tz = self._data.get("timezone")
        if not tz:
            tz = request.cookies.get("browser_timezone", "UTC")
        return tz

    @property
    def raw_timezone(self):
        # For the user info page, we want to allow the user to set their time zone to blank,
        # which is interpreted as the browser's timezone for other uses.
        return self._data.get("timezone", "")

    @property
    def tz(self):
        try:
            return timezone(self.timezone)
        except UnknownTimeZoneError:
            return timezone("UTC")

    def show_timezone(self, dest="topmenu"):
        # dest can be 'browse', in which case "now" is inserted, or 'selecter', in which case fixed width is used.
        return pretty_timezone(self.tz, dest=dest)

    @timezone.setter
    def timezone(self, timezone):
        self._data["timezone"] = timezone
        self._dirty = True

    @property
    def created(self):
        return self._data.get("created")

    @property
    def endorser(self):
        return self._data.get("endorser")

    @endorser.setter
    def endorser(self, endorser):
        self._data["endorser"] = endorser
        self._dirty = True

    # @property
    # def location(self):
    #     return self._data.get("location", "")

    # @location.setter
    # def location(self, location):
    #     self._data["location"] = location
    #     self._dirty = True


    @property
    def api_token(self):
        token = self._data.get("api_token")
        if token is None:
            token = userdb.reset_api_token(self._uid)
        return token

    @property
    def api_access(self):
        if not self.is_creator:
            return 0
        if self.is_admin:
            return 1
        return self._data.get("api_access", 0)

    @property
    def ics(self):
        return generate_token(self.id, "ics")

    @property
    def ics_link(self):
        return url_for(".user_ics_file", token=self.ics, _external=True, _scheme="https")

    @property
    def ics_gcal_link(self):
        return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(
            {"cid": url_for(".user_ics_file", token=self.ics, _external=True, _scheme="http")}
        )

    @property
    def ics_webcal_link(self):
        return url_for(".user_ics_file", token=self.ics, _external=True, _scheme="webcal")

    @property
    def seminar_subscriptions(self):
        return self._data.get("seminar_subscriptions", [])

    @property
    def seminars(self):
        ans = []
        for elt in self.seminar_subscriptions:
            try:
                ans.append(WebSeminar(elt))
            except ValueError:
                self._data["seminar_subscriptions"].remove(elt)
                self._dirty = True
        ans = next_talk_sorted(ans)
        if self._dirty:
            self.save()
        return ans

    def seminar_subscriptions_add(self, shortname):
        if shortname not in self._data["seminar_subscriptions"]:
            bisect.insort(self._data["seminar_subscriptions"], shortname)
            if shortname in self.talk_subscriptions:
                self._data["talk_subscriptions"].pop(shortname)
            self._dirty = True
            return 200, "Added to favorites"
        else:
            return 200, "Already added to favorites"

    def seminar_subscriptions_remove(self, shortname):
        if shortname in self._data["seminar_subscriptions"]:
            self._data["seminar_subscriptions"].remove(shortname)
            self._dirty = True
            return 200, "Removed from favorites"
        else:
            return 200, "Already removed from favorites"

    @property
    def talk_subscriptions(self):
        return self._data.get("talk_subscriptions", {})

    @property
    def talks(self):
        res = []
        for shortname, ctrs in self.talk_subscriptions.items():
            for ctr in ctrs:
                try:
                    res.append(WebTalk(shortname, ctr))
                except ValueError:
                    self._data["talk_subscriptions"][shortname].remove(ctr)
                    self._dirty = True

        if self._dirty:
            for shortname in self._data["talk_subscriptions"]:
                if not self._data["talk_subscriptions"]:
                    self._data["talk_subscriptions"].pop("shortname")
            self.save()

        res.sort(key=lambda elt: elt.start_time)
        return res

    def talk_subscriptions_add(self, shortname, ctr):
        if shortname in self._data["seminar_subscriptions"]:
            return 200, "Talk is in saved seminar"
        elif ctr in self._data["talk_subscriptions"].get(shortname, []):
            return 200, "Already added to favorites"
        else:
            if shortname in self._data["talk_subscriptions"]:
                bisect.insort(self._data["talk_subscriptions"][shortname], ctr)
            else:
                self._data["talk_subscriptions"][shortname] = [ctr]
            self._dirty = True
            return 200, "Added to favorites"

    def talk_subscriptions_remove(self, shortname, ctr):
        if shortname in self._data["seminar_subscriptions"]:
            return 400, "Talk is part of favorited seminar"
        if ctr in self._data["talk_subscriptions"].get(shortname, []):
            self._data["talk_subscriptions"][shortname].remove(ctr)
            self._dirty = True
            return 200, "Removed from favorites"
        else:
            return 200, "Already removed from favorites"

    @property
    def is_authenticated(self):
        """required by flask-login user class"""
        return self._authenticated

    @is_authenticated.setter
    def is_authenticated(self, is_authenticated):
        """required by flask-login user class"""
        self._authenticated = is_authenticated

    @property
    def is_anonymous(self):
        """required by flask-login user class"""
        return not self._authenticated

    @property
    def is_active(self):
        """required by flask-login user class"""
        # It would be nice to have active tied to email_confirmed,
        # But then users can't see their info page to be able to confirm their email
        return True

    @property
    def is_admin(self):
        return self._data.get("admin", False)

    def is_subject_admin(self, talk_or_seminar):
        if self.is_admin:
            return True
        sa = self._data.get("subject_admin")
        if not talk_or_seminar:
            return sa
        topics = talk_or_seminar.topics
        return sa and sa in topics

    @property
    def is_creator(self):
        return self._data.get("creator", False)

    @property
    def creator(self):
        return self._data.get("creator", False)

    @creator.setter
    def creator(self, creator):
        self._data["creator"] = creator
        self._dirty = True
        if creator:
            assert self.endorser is not None
            userdb.make_creator(self.email, int(self.endorser))  # it already saves
            flash("Someone endorsed you! You can now create series.", "success")

    @property
    def external_ids(self):
        return [ r.split(":") for r in self._data.get("external_ids",[]) ] if self._data.get("external_ids") else []

    @external_ids.setter
    def external_ids(self, author_ids):
        self._data["external_ids"] = author_ids
        self._dirty = True

    @property
    def is_organizer(self):
        return self.id and (self.is_admin or self.is_creator or self._organizer)

    def check_password(self, pwd):
        """
        checks if the given password for the user is valid.
        @return: True: OK, False: wrong password or username
        """
        if "password" not in self._data:
            logger.warning("no password data in db for '%s'!" % self.email)
            return False
        try:
            return userdb.authenticate(self.email, pwd)
        except ValueError:
            return False

    def save(self):
        if not self._dirty:
            return
        logger.debug("saving '%s': %s" % (self.id, self._data))
        userdb.save(self._data)
        if "new_email" in self._data:
            self.__init__(email=self._data["new_email"])

        self._dirty = False
        return True

    def delete(self):
        userdb.delete(self._data)

class SeminarsAnonymousUser(AnonymousUserMixin):
    """
    The sole purpose of this Anonymous User is the 'is_admin' method
    and probably others.
    """

    @property
    def is_authenticated(self):
        return False

    @property
    def is_active(self):
        return False

    @property
    def is_anonymous(self):
        return True

    @property
    def is_organizer(self):
        return False

    @property
    def is_creator(self):
        return False

    @property
    def is_admin(self):
        return False

    def is_subject_admin(self, talk_or_seminar):
        return False

    def get_id(self):
        return

    @property
    def api_token(self):
        return None

    @property
    def api_access(self):
        return 0

    @property
    def email(self):
        return None

    @property
    def homepage(self):
        return None

    @property
    def name(self):
        return ""

    @property
    def timezone(self):
        return request.cookies.get("browser_timezone", "UTC")

    @property
    def tz(self):
        try:
            return timezone(self.timezone)
        except UnknownTimeZoneError:
            return timezone("UTC")

    @property
    def email_confirmed(self):
        return False

    def show_timezone(self, dest="topmenu"):
        # dest can be 'browse', in which case "now" is inserted, or 'selecter', in which case fixed width is used.
        return pretty_timezone(self.tz, dest=dest)
