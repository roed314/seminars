# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from seminars import db
from seminars.app import app
from seminars.create import create
from seminars.utils import basic_top_menu, categories, timezones, process_user_input
from seminars.seminar import WebSeminar, seminars_lucky, seminars_lookup, can_edit_seminar
from seminars.talk import WebTalk, talks_lookup
from seminars.institution import WebInstitution, can_edit_institution, institutions, institution_types
from seminars.lock import get_lock
from lmfdb.utils import to_dict, flash_error
import datetime, json

@create.route("create/")
@login_required
def index():
    # TODO: use a join for the following query
    print("CREATE?")
    seminars = []
    conferences = []
    for semid in db.seminar_organizers.search({'email': current_user.email}, 'seminar_id'):
        seminar = WebSeminar(semid)
        if seminar.is_conference:
            conferences.append(seminar)
        else:
            seminars.append(seminar)
    menu = basic_top_menu()
    menu.pop(-3)
    return render_template("create_index.html",
                           seminars=seminars,
                           conferences=conferences,
                           top_menu=menu,
                           title="Create",
                           user_is_creator=current_user.is_creator())

@create.route("edit/seminar/", methods=["GET", "POST"])
@login_required
def edit_seminar():
    if request.method == 'POST':
        data = request.form
    else:
        data = request.args
    shortname = data.get("shortname", "")
    new = (data.get("new") == "yes")
    resp, seminar = can_edit_seminar(shortname, new)
    if resp is not None:
        return resp
    lock = get_lock(shortname, data.get("lock"))
    title = "Create seminar" if new else "Edit seminar"
    return render_template("edit_seminar.html",
                           seminar=seminar,
                           title=title,
                           top_menu=basic_top_menu(),
                           categories=categories(),
                           institutions=institutions(),
                           timezones=timezones,
                           lock=lock)

@create.route("save/seminar/", methods=["POST"])
@login_required
def save_seminar():
    raw_data = request.form
    shortname = raw_data["shortname"]
    new = (raw_data.get("new") == "yes")
    resp, seminar = can_edit_seminar(shortname, new)
    if resp is not None:
        return resp
    def make_error(err):
        flash_error("Error processing %s: %s" % (col, err))
        seminar = WebSeminar(shortname, data=raw_data)
        return render_template("edit_seminar.html",
                               seminar=seminar,
                               title="Edit seminar error",
                               top_menu=basic_top_menu(),
                               categories=categories(),
                               institutions=institutions(),
                               lock=None)

    if seminar.new:
        data = {'shortname': shortname,
                'display': current_user.is_creator(),
                'owner': current_user.email,
                'archived':False}
    else:
        data = {'shortname': shortname,
                'display': seminar.display or current_user.is_creator(),
                'owner': seminar.owner}
    for col in db.seminars.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.seminars.col_type[col])
        except Exception as err:
            return make_error(err)
    if not data['timezone'] and data['institutions']:
        # Set time zone from institution
        data['timezone'] = WebInstitution(data['institutions'][0]).timezone
    print(data)
    organizer_data = []
    for i in range(6):
        D = {'seminar_id': seminar.shortname}
        for col in db.seminar_organizers.search_cols:
            if col in D: continue
            name = "org_%s%s" % (col, i)
            try:
                val = raw_data.get(name)
                if val == '':
                    D[col] = None
                elif val is None:
                    D[col] = False # checkboxes
                else:
                    D[col] = process_user_input(val, db.seminar_organizers.col_type[col])
            except Exception as err:
                return make_error(err)
        if D.get('email') or D.get('full_name'):
            D['order'] = len(organizer_data)
            organizer_data.append(D)
    new_version = WebSeminar(shortname, data=data, organizer_data=organizer_data)
    if seminar.new or new_version != seminar:
        new_version.save()
    if seminar.organizer_data != new_version.organizer_data:
        new_version.save_organizers()
    edittype = "created" if new else "edited"
    flash("Seminar successfully %s!" % edittype)
    return redirect(url_for("show_seminar", shortname=shortname), 301)

@create.route("edit/institution/", methods=["GET", "POST"])
@login_required
def edit_institution():
    if request.method == 'POST':
        data = request.form
    else:
        data = request.args
    shortname = data.get("shortname", "")
    new = (data.get("new") == "yes")
    resp, institution = can_edit_institution(shortname, new)
    if resp is not None:
        return resp
    # Don't use locks for institutions since there's only one non-admin able to edit.
    title = "Create institution" if new else "Edit institution"
    return render_template("edit_institution.html",
                           institution=institution,
                           institution_types=institution_types,
                           timezones=timezones,
                           title=title,
                           top_menu=basic_top_menu())

@create.route("save/institution/", methods=["POST"])
@login_required
def save_institution():
    raw_data = request.form
    shortname = raw_data["shortname"]
    new = (raw_data.get("new") == "yes")
    resp, institution = can_edit_institution(shortname, new)
    if resp is not None:
        return resp

    data = {}
    for col in db.institutions.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.institutions.col_type[col])
            if col == 'admin':
                userdata = db.users.lookup(val)
                if userdata is None:
                    raise ValueError("%s must have account on this site" % val)
                if not userdata['phd']:
                    raise ValueError("%s must have a PhD to administer an institution" % val)
            if col == 'homepage' and not val.startswith("http"):
                data[col] = "https://" + data[col]
        except Exception as err:
            flash_error("Error processing %s: %s" % (col, err))
            institution = WebInstitution(shortname, data=raw_data)
            return render_template("edit_institution.html",
                                   institution=institution,
                                   institution_types=institution_types,
                                   timezones=timezones,
                                   title="Edit institution error",
                                   top_menu=basic_top_menu())
    print(data)
    new_version = WebInstitution(shortname, data=data)
    new_version.save()
    edittype = "created" if new else "edited"
    flash("Institution successfully %s!" % edittype)
    return redirect(url_for("show_institution", shortname=shortname), 301)


@create.route("edit/talk/", methods=["GET", "POST"])
def edit_talk():
    if request.method == 'POST':
        data = request.form
    else:
        data = request.args
    seminar_id = data.get("seminar_id", "")
    seminar_ctr = data.get("seminar_ctr", "")
    new = not seminar_ctr
    if seminar_ctr:
        try:
            seminar_ctr = int(seminar_ctr)
        except ValueError:
            flash_error("Invalid talk id")
            return redirect(url_for("show_seminar", shortname=seminar_id), 301)
    token = data.get("token", "")
    if token:
        if seminar_ctr == "":
            flash_error("Must provide talk id with token")
            return redirect(url_for("show_seminar", shortname=seminar_id), 301)
        talk = talks_lookup(seminar_id, seminar_ctr)
        if talk is None:
            flash_error("Talk does not exist")
            return redirect(url_for("show_seminar", shortname=seminar_id), 301)
        elif token != talk['token']:
            flash_error("Invalid token for editing talk")
            return redirect(url_for("show_talk", semid=seminar_id, talkid=seminar_ctr), 301)
        seminar = seminars_lookup(seminar_id)
    else:
        resp, seminar = can_edit_seminar(seminar_id, new=False)
        if resp is not None:
            return resp
        if new:
            talk = WebTalk(seminar_id, seminar=seminar, editing=True)
        else:
            talk = WebTalk(seminar_id, seminar_ctr) # editing=True means we look up data
    lock = get_lock(seminar_id, data.get("lock"))
    title = "Create talk" if new else "Edit talk"
    return render_template("edit_talk.html",
                           talk=talk,
                           seminar=seminar,
                           title=title,
                           top_menu=basic_top_menu(),
                           categories=categories(),
                           institutions=institutions(),
                           timezones=timezones,
                           lock=lock)

    new = (data.get("new") == "yes")
    resp, institution = can_edit_seminar(seminar_id, new)
    if resp is not None:
        return resp
    # Don't use locks for institutions since there's only one non-admin able to edit.
    title = "Create institution" if new else "Edit institution"
    return render_template("edit_institution.html",
                           institution=institution,
                           institution_types=institution_types,
                           timezones=timezones,
                           title=title,
                           top_menu=basic_top_menu())

@create.route("save/talk/", methods=["POST"])
def save_talk():
    pass
