# -*- coding: utf-8 -*-
# Math Seminars - https://mathseminars.org
# Copyright (C) 2020 by the Math Seminars authors
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
"""
start this via $ sage -python website.py --port <portnumber>
add --debug if you are developing (auto-restart, full stacktrace in browser, ...)
"""
from __future__ import print_function, absolute_import

# Needs to be done first so that other modules and gunicorn can use logging
from lmfdb.logger import info
from .app import app, set_running  # So that we can set it running below


from . import users
assert users

from . import homepage
assert homepage

from . import create
assert create

from . import api
assert api


from lmfdb.backend import db

if db.is_verifying:
    raise RuntimeError("Cannot start website while verifying (SQL injection vulnerabilities)")


def main():
    info("main: ...done.")
    from lmfdb.utils.config import Configuration

    flask_options = Configuration().get_flask()

    if "profiler" in flask_options and flask_options["profiler"]:
        info("Profiling!")
        from werkzeug.contrib.profiler import ProfilerMiddleware

        app.wsgi_app = ProfilerMiddleware(
            app.wsgi_app, restrictions=[30], sort_by=("cumulative", "time", "calls")
        )
        del flask_options["profiler"]

    set_running()
    app.run(**flask_options)
