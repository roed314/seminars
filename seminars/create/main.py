# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for
from flask_login import login_required, current_user
from seminars import db
from seminars.app import app
from seminars.create import create
from seminars.utils import basic_top_menu
from lmfdb.utils import to_dict
import datetime

def process_user_input(inp, typ):
    """
    INPUT:

    - ``inp`` -- unsanitized input, as a string
    - ``typ`` -- a Postgres type, as a string
    """
    if inp is None:
        return None
    if typ == 'timestamp with time zone':
        # Need to sanitize more, include time zone
        return datetime.strptime(inp, "%Y-%m-%d-%H:%M")
    elif type == 'boolean':
        if inp in ['yes', 'true', 'y', 't']:
            return True
        elif inp in ['no', 'false', 'n', 'f']:
            return False
        raise ValueError
    elif type == 'interval':
        # should sanitize somehow
        return inp
    else:
        # should sanitize somehow
        return inp

@create.route("/")
@login_required
def index():
    # TODO: use a join for the following query
    seminars = []
    for semid in db.seminar_organizers.search({'email': current_user.email}, 'seminar_id'):
        seminars.append((semid, db.seminars.lucky({'id': semid}, 'name')))
    menu = basic_top_menu()
    menu.pop(-3)
    return render_template("create_index.html",
                           seminars=seminars,
                           top_menu=menu,
                           user_is_creator=current_user.is_creator())

@create.route("/seminar/")
@login_required
def create_seminar():
    info = to_dict(request.args)
    if info:
        # What sanitation needs to be done here?
        # We override any display input
        info["display"] = current_user.is_creator()
        data = {}
        for col in db.seminars.search_cols:
            try:
                data[col] = process_user_input(info.pop(col, None), db.seminars.col_type[col])
            except Exception:
                return render_template("create_seminar.html",
                                       err=col,
                                       info=info,
                                       user_is_creator=current_user.is_creator())
        db.seminars.insert_many([data], resort=False, restat=False)
        return redirect(url_for(".index"), 301)
    return render_template("create_seminar.html",
                           info=info,
                           user_is_creator=current_user.is_creator())

