#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import print_function
from __future__ import absolute_import
from six import string_types, text_type
import random
import string
import bcrypt
# store passwords, check users, ...
# password hashing is done with fixed and variable salting
# Author: Harald Schilly <harald.schilly@univie.ac.at>
# Modified : Chris Brady and Heather Ratcliffe

from seminars import db
from lmfdb.backend.base import PostgresBase
from lmfdb.backend.searchtable import PostgresSearchTable
from lmfdb.backend.encoding import Array
from psycopg2.sql import SQL, Identifier, Placeholder
from datetime import datetime, timedelta
from pytz import UTC, all_timezones

from .main import logger, FLASK_LOGIN_VERSION, FLASK_LOGIN_LIMIT
from distutils.version import StrictVersion

# Read about flask-login if you are unfamiliar with this UserMixin/Login
from flask_login import UserMixin, AnonymousUserMixin

class PostgresUserTable(PostgresSearchTable):
    def __init__(self):
        PostgresSearchTable.__init__(self, db=db, search_table="users", label_col="email", include_nones=True)
        # FIXME
        self._rw_userdb = db.can_read_write_userdb()

    def log_db_change(self, what, **kwargs):
        " no need to log the changes "
        #FIXME: also the logger can't handle bytes
        pass

    def can_read_write_userdb(self):
        return self._rw_userdb



    def bchash(self, pwd, existing_hash=None):
        """
        Generate a bcrypt based password hash.
        """
        if not existing_hash:
            existing_hash = bcrypt.gensalt().decode('utf-8')
        return bcrypt.hashpw(pwd.encode('utf-8'), existing_hash.encode('utf-8'))

    def generate_key(self):
        return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(12)])

    def new_user(self, **kwargs):
        """
        Creates a new user.
        Required keyword arguments:
            - email
            - password
            - name
            - affiliation
        """
        for col in ["email", "password", "name", "affiliation"]:
            assert col in kwargs
        kwargs['password'] = self.bchash(kwargs['password'])
        if 'approver' not in kwargs:
            kwargs['approver'] = None
            kwargs['admin'] = kwargs['editor'] = kwargs['creator'] = False
        for col in ['email_confirmed', 'admin', 'editor', 'creator']:
            kwargs[col] = kwargs.get(col, False)
        kwargs['email_confirm_code'] = kwargs.get("email_confirm_code", self.generate_key())
        kwargs['homepage'] = kwargs.get('homepage', None)
        kwargs['timezone'] = kwargs.get('timezone', "US/Eastern")
        assert kwargs['timezone'] in all_timezones
        kwargs['location'] = None
        kwargs['created'] = datetime.now(UTC)
        kwargs['ics_key'] = self.generate_key()
        email = kwargs.pop('email')
        self.upsert({'email':email}, kwargs)
        newuser = SeminarsUser(email)
        return newuser


    def change_password(self, email, newpwd):
        self.update(query={'email': email},
                    changes={'password': self.bchash(newpwd)},
                    resort=False,
                    restat=False)
        logger.info("password for %s changed!" % email)


    def user_exists(self, email):
        return self.lookup(email, projection='id') is not None


    def authenticate(self, email, password):
        bcpass = self.lookup(email, projection='password')
        if bcpass is None:
            raise ValueError("User not present in database!")
        print(bcpass)
        return bcpass.encode('utf-8') == self.bchash(password, existing_hash=bcpass)

    def confirm_email(self, token):
        email = self.lucky({'email_confirm_code': token}, "email")
        if email is not None:
            self.update({'email':email}, {'email_confirmed': True, 'email_confirm_code': None})
            return True
        else:
            return False


    def save(self, data):
        data = dict(data) # copy
        email = data.pop("email", None)
        if not email:
            raise ValueError("data must contain email")
        user = self.lookup(email)
        if not user:
            raise ValueError("user does not exist")
        if not data:
            raise ValueError("no data to save")
        if 'new_email' in data:
            data['email'] = data.pop('new_email')

        self.update({'email': email}, data)



userdb = PostgresUserTable()

class SeminarsUser(UserMixin):
    """
    The User Object
    """
    properties =  sorted(userdb.col_type)

    def __init__(self, email):
        if not isinstance(email, string_types):
            raise Exception("Username is not a string, %s" % email)

        self._email = email
        self._uid = email.encode('utf-8')
        self._authenticated = False
        self._dirty = False  # flag if we have to save
        self._data = dict([(_, None) for _ in SeminarsUser.properties])

        user_row = userdb.lookup(email)
        if user_row:
            self._data.update(user_row)

    @property
    def name(self):
        return self._data['name']

    @name.setter
    def name(self, name):
        self._data['name'] = name
        self._dirty = True

    @property
    def email(self):
        return self._data['email']

    @email.setter
    def email(self, email):
        self._data['new_email'] = email
        if self._data['new_email'] != self._data.get('email'):
            self._data['email_confirmed'] = False
            self._data['email_confirm_code'] = userdb.generate_key()
        self._dirty = True

    @property
    def homepage(self):
        return self._data['homepage']

    @homepage.setter
    def homepage(self, url):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url
        self._data['homepage'] = url
        self._dirty = True

    @property
    def created(self):
        return self._data.get('created')

    def id(self):
        return self._data['email']

    def is_anonymous(self):
        """required by flask-login user class"""
        if StrictVersion(FLASK_LOGIN_VERSION) < StrictVersion(FLASK_LOGIN_LIMIT):
            return not self.is_authenticated()
        return not self.is_authenticated

    def is_admin(self):
        return self._data.get("admin", False)

    def make_admin(self):
        self._data["admin"] = True
        self._dirty = True

    def is_editor(self):
        return self._data.get("editor", False)

    def make_editor(self):
        self._data["editor"] = True
        self._dirty = True

    def is_creator(self):
        return self._data.get("creator", False)

    def make_creator(self):
        self._data["creator"] = True
        self._dirty = True

    def authenticate(self, pwd):
        """
        checks if the given password for the user is valid.
        @return: True: OK, False: wrong password.
        """
        if 'password' not in self._data:
            logger.warning("no password data in db for '%s'!" % self._email)
            return False
        self._authenticated = userdb.authenticate(self._email, pwd)
        return self._authenticated

    def save(self):
        if not self._dirty:
            return
        logger.debug("saving '%s': %s" % (self.id, self._data))
        userdb.save(self._data)
        self._dirty = False

class SeminarsAnonymousUser(AnonymousUserMixin):
    """
    The sole purpose of this Anonymous User is the 'is_admin' method
    and probably others.
    """
    def is_admin(self):
        return False

    def is_editor(self):
        return False

    def is_creator(self):
        return False

    def name(self):
        return "Anonymous"

    # For versions of flask_login earlier than 0.3.0,
    # AnonymousUserMixin.is_anonymous() is callable. For later versions, it's a
    # property. To match the behavior of SeminarsUser, we make it callable always.
    def is_anonymous(self):
        return True

if __name__ == "__main__":
    print("Usage:")
    print("add user")
    print("remove user")
    print("…")
