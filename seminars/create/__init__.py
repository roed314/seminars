# -*- coding: utf-8 -*-
from __future__ import absolute_import
from seminars.app import app
from lmfdb.logger import make_logger
from flask import Blueprint

create_page = Blueprint("create", __name__, template_folder='templates', static_folder="static")
create = cmf_page
create_logger = make_logger(create_page)

from . import main
assert main # silence pyflakes

app.register_blueprint(create_page, url_prefix="/create")
