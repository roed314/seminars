# -*- coding: utf-8 -*-
from __future__ import absolute_import
from seminars.app import app
from flask import Blueprint

create = Blueprint("create", __name__, template_folder="templates", static_folder="static")

from . import main

assert main  # silence pyflakes

app.register_blueprint(
    create, url_prefix="/"
)  # we don't have a url_prefix since we want to use /edit/* sometimes
