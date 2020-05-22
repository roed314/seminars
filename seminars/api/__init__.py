# -*- coding: utf-8 -*
from __future__ import absolute_import
from flask import Blueprint
from seminars.app import app

api_page = Blueprint("api", __name__, template_folder="templates")

from . import main
assert main

app.register_blueprint(api_page, url_prefix="/api")
