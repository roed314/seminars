# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for
from flask_login import login_required, current_user
from seminars import db
from seminars.app import app
from seminars.create import create
from seminars.utils import basic_top_menu
from seminars.seminar import allowed_semid, is_locked, set_locked, WebSeminar
from lmfdb.utils import to_dict
import datetime, json
from psycopg2 import DatabaseError
from seminars.create import create_logger as logger

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

@create.route("create/")
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
                           title="Create",
                           user_is_creator=current_user.is_creator())

@create.route("edit/seminar/<shortname>")
@login_required
def edit_seminar(shortname):
    if not allowed_semid(shortname):
        flash_error("The seminar identifier can only include letters, numbers, hyphens and underscores.")
        return redirect(url_for(".index"), 301)
    # Check if seminar exists
    seminar = db.seminars.lucky({'shortname': semid})
    new = (seminar is None)
    if not new and not current_user.is_admin():
        # Make sure user has permission to edit
        organizer_data = db.seminar_organizers.lucky({'seminar_id': semid, 'email':current_user.email})
        if organizer_data is None:
            owner = "<%s>" % (owner_name, seminar['owner'])
            owner_name = db.users.lucky({'email': seminar['owner']}, 'full_name')
            if owner_name:
                owner = owner_name + " " + owner
            flash_error("You do not have permssion to edit seminar %s.  Contact the seminar owner, %s, and ask them to grant you permission." % (semid, owner))
            return redirect(url_for(".index"), 301)
    lock = None
    if request.args.get("lock") != "ignore":
        try:
            lock = is_locked(shortname)
        except DatabaseError as e:
            logger.info("Oops, failed to get the lock. Error: %s" % e)
    author_edits = lock and lock['email'] == current_user.email
    logger.debug(author_edits)
    if author_edits:
        lock = None
    if not lock:
        try:
            set_locked(shortname)
        except DatabaseError as e:
            logger.info("Oops, failed to set the lock. Error: %s" % e)
    title = "Create seminar" if new else "Edit seminar"
    return render_template("edit_seminar.html",
                           seminar=seminar,
                           title=title,
                           top_menu=basic_top_menu(),
                           lock=lock)

@create.route("save", methods=["POST"])
@login_required
def save_seminar():
    semid = request.form["shortname"]
    if not semid:
        raise ValueError("no id")
    if not allowed_semid(semid):
        return redirect(url_for(".index"))

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
