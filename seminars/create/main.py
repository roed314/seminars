# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from seminars import db
from seminars.app import app
from seminars.create import create
from seminars.utils import categories, timezones, process_user_input, check_time, weekdays
from seminars.seminar import WebSeminar, seminars_lucky, seminars_lookup, can_edit_seminar
from seminars.talk import WebTalk, talks_lookup, talks_max, talks_search, talks_lucky, can_edit_talk
from seminars.institution import WebInstitution, can_edit_institution, institutions, institution_types, institution_known
from seminars.lock import get_lock
from lmfdb.utils import to_dict, flash_error
import datetime, pytz, json

@create.route("create/")
@login_required
def index():
    # TODO: use a join for the following query
    seminars = []
    conferences = []
    for semid in db.seminar_organizers.search({'email': current_user.email}, 'seminar_id'):
        seminar = WebSeminar(semid)
        if seminar.is_conference:
            conferences.append(seminar)
        else:
            seminars.append(seminar)
    return render_template("create_index.html",
                           seminars=seminars,
                           conferences=conferences,
                           institution_known=institution_known,
                           section="Create",
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
                           #section="Create",
                           categories=categories(),
                           institutions=institutions(),
                           weekdays=weekdays,
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
    def make_error(col=None, err=None):
        if err is not None:
            flash_error("Error processing %s: {0}".format(err), col)
        seminar = WebSeminar(shortname, data=raw_data)
        return render_template("edit_seminar.html",
                               seminar=seminar,
                               title="Edit seminar error",
                               #section="Create",
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
    # Have to get time zone first
    data['timezone'] = tz = raw_data.get('timezone')
    tz = pytz.timezone(tz)
    for col in db.seminars.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.seminars.col_type[col], tz=tz)
        except Exception as err:
            return make_error(col, err)
    if not data['institutions']: # need [] not None
        data['institutions'] = []
    if not data['timezone'] and data['institutions']:
        # Set time zone from institution
        data['timezone'] = WebInstitution(data['institutions'][0]).timezone
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
                    D[col] = process_user_input(val, db.seminar_organizers.col_type[col], tz=tz)
                if col == 'homepage' and val and not val.startswith("http"):
                    data[col] = "http://" + data[col]
            except Exception as err:
                return make_error(col, err)
        if D.get('email') or D.get('full_name'):
            D['order'] = len(organizer_data)
            organizer_data.append(D)
    new_version = WebSeminar(shortname, data=data, organizer_data=organizer_data)
    if check_time(new_version.start_time, new_version.end_time):
        return make_error()
    if seminar.new or new_version != seminar:
        new_version.save()
        edittype = "created" if new else "edited"
        flash("Seminar %s successfully!" % edittype)
    elif seminar.organizer_data == new_version.organizer_data:
        flash("No changes made to seminar.")
    if seminar.organizer_data != new_version.organizer_data:
        new_version.save_organizers()
        flash("Seminar organizers updated!")
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
                           section="Create",
    )

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
    data['timezone'] = tz = raw_data.get('timezone', 'UTC')
    tz = pytz.timezone(tz)
    for col in db.institutions.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.institutions.col_type[col], tz=tz)
            if col == 'admin':
                userdata = db.users.lookup(val)
                if userdata is None:
                    raise ValueError("%s must have account on this site" % val)
            if col == 'homepage' and val and not val.startswith("http"):
                data[col] = "http://" + data[col]
            if col == "access" and val not in ["open", "users", "endorsed"]:
                raise ValueError("Invalid access type")
        except Exception as err:
            # TODO: this probably needs to be a redirect to change the URL?  We want to save the data the user entered.
            flash_error("Error processing %s: %s" % (col, err))
            institution = WebInstitution(shortname, data=raw_data)
            return render_template("edit_institution.html",
                                   institution=institution,
                                   institution_types=institution_types,
                                   timezones=timezones,
                                   title="Edit institution error",
                                   #section="Create",
            )
    new_version = WebInstitution(shortname, data=data)
    if new_version == institution:
        flash("No changes made to institution.")
    else:
        new_version.save()
        edittype = "created" if new else "edited"
        flash("Institution %s successfully!" % edittype)
    return redirect(url_for("show_institution", shortname=shortname), 301)

@create.route("edit/talk/<seminar_id>/<seminar_ctr>/<token>")
def edit_talk_with_token(seminar_id, seminar_ctr, token):
    # For emailing, where encoding ampersands in a mailto link is difficult
    return redirect(url_for(".edit_talk", seminar_id=seminar_id, seminar_ctr=seminar_ctr, token=token), 301)

@create.route("edit/talk/", methods=["GET", "POST"])
def edit_talk():
    if request.method == 'POST':
        data = request.form
    else:
        data = request.args
    resp, seminar, talk = can_edit_talk(
        data.get("seminar_id", ""),
        data.get("seminar_ctr", ""),
        data.get("token", ""))
    if resp is not None:
        return resp
    #lock = get_lock(seminar_id, data.get("lock"))
    title = "Create talk" if talk.new else "Edit talk"
    return render_template("edit_talk.html",
                           talk=talk,
                           seminar=seminar,
                           title=title,
                           #section="Create",
                           categories=categories(),
                           institutions=institutions(),
                           timezones=timezones)

@create.route("save/talk/", methods=["POST"])
def save_talk():
    raw_data = request.form
    resp, seminar, talk = can_edit_talk(
        raw_data.get("seminar_id", ""),
        raw_data.get("seminar_ctr", ""),
        raw_data.get("token", ""))
    if resp is not None:
        return resp

    def make_error(col=None, err=None):
        if err is not None:
            flash_error("Error processing %s: {0}".format(err), col)
        talk = WebTalk(talk.seminar_id, talk.seminar_ctr, data=raw_data)
        title = "Create talk error" if talk.new else "Edit talk error"
        return render_template("edit_talk.html",
                               talk=talk,
                               seminar=seminar,
                               title=title,
                               #section="Create",
                               institutions=institutions(),
                               timezones=timezones)

    data = {
        'seminar_id': talk.seminar_id,
        'token': talk.token,
        'display': talk.display, # could be being edited by anonymous user
    }
    if talk.new:
        curmax = talks_max('seminar_ctr', {'seminar_id': talk.seminar_id})
        if curmax is None:
            curmax = 0
        data['seminar_ctr'] = curmax + 1
    else:
        data['seminar_ctr'] = talk.seminar_ctr
    default_tz = seminar.timezone
    if not default_tz:
        default_tz = 'UTC'
    data['timezone'] = tz = raw_data.get('timezone', default_tz)
    tz = pytz.timezone(tz)
    for col in db.talks.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.talks.col_type[col], tz=tz)
            if col == 'speaker_homepage' and val and not val.startswith("http"):
                data[col] = "http://" + data[col]
            if col == "access" and val not in ["open", "users", "endorsed"]:
                raise ValueError("Invalid access type")
        except Exception as err:
            return make_error(col, err)
    new_version = WebTalk(talk.seminar_id, data['seminar_ctr'], data=data)
    if check_time(new_version.start_time, new_version.end_time):
        return make_error()
    if new_version == talk:
        flash("No changes made to talk.")
    else:
        new_version.save()
        edittype = "created" if talk.new else "edited"
        flash("Talk successfully %s!" % edittype)
    return redirect(url_for("show_talk", semid=new_version.seminar_id, talkid=new_version.seminar_ctr), 301)

def make_date_data(seminar):
    shortname = seminar.shortname
    if not seminar.frequency or seminar.frequency < 0 or not seminar.schedule_len or seminar.schedule_len < 0 or seminar.schedule_len > 400:
        print(seminar.frequency, seminar.schedule_len)
        flash_error("You must specify a meeting frequency to use the scheduler")
        return redirect(url_for("show_seminar", shortname=shortname), 301), None, None, None
    now = datetime.datetime.now(tz=pytz.utc)
    today = now.date()
    day = datetime.timedelta(days=1)
    last_talk = talks_lucky({'seminar_id': shortname, 'start_time':{'$lte': now}}, sort=[('start_time', -1)])
    future_talks = list(talks_search({'seminar_id': shortname, 'start_time':{'$gte': now}}, sort=['start_time']))
    by_date = {T.start_time.date(): T for T in future_talks}
    if len(by_date) != len(future_talks):
        flash_error("Cannot use scheduler when there are multiple talks on the same day")
        return redirect(url_for("show_seminar", shortname=shortname), 301), None, None, None
    if last_talk is None:
        if seminar.weekday is None:
            if not future_talks:
                flash_error("You must specify a weekday or add a talk to the seminar")
                return redirect(url_for("show_seminar", shortname=shortname), 301), None, None, None
            seminar.weekday = future_talks[0].start_time.date().weekday()
        next_date = today
        while next_date.weekday() != seminar.weekday:
            next_date += day
    else:
        next_date = last_talk.start_time.date()
        today = now.date()
        while next_date < today:
            next_date += seminar.frequency * day
    all_dates = sorted(set([next_date + i*seminar.frequency*day for i in range(seminar.schedule_len)] + list(by_date)))
    if seminar.start_time is None:
        if future_talks:
            seminar.start_time = future_talks[0].start_time.time()
        elif last_talk is not None:
            seminar.start_time = last_talk.start_time.time()
    if seminar.end_time is None:
        if future_talks:
            seminar.end_time = future_talks[0].end_time.time()
        elif last_talk is not None:
            seminar.end_time = last_talk.end_time.time()
    return None, seminar, all_dates, by_date

@create.route("edit/schedule/", methods=["GET", "POST"])
def edit_seminar_schedule():
    # It would be good to have a version of this that worked for a conference, but that's a project for later
    if request.method == 'POST':
        data = request.form
    else:
        data = request.args
    shortname = data.get("shortname", "")
    resp, seminar = can_edit_seminar(shortname, new=False)
    if resp is not None:
        return resp
    resp, seminar, all_dates, by_date = make_date_data(seminar)
    if resp is not None:
        return resp
    title = "Edit seminar schedule"
    return render_template("edit_seminar_schedule.html",
                           seminar=seminar,
                           all_dates=all_dates,
                           by_date=by_date,
                           weekdays=weekdays,
                           title=title,
                           #section="Create",
    )

@create.route("save/schedule/", methods=["POST"])
def save_seminar_schedule():
    raw_data = request.form
    shortname = raw_data["shortname"]
    resp, seminar = can_edit_seminar(shortname, new=False)
    if resp is not None:
        return resp
    schedule_count = int(raw_data["schedule_count"])
    update_times = bool(raw_data.get("update_times"))
    curmax = talks_max('seminar_ctr', {'seminar_id': shortname})
    if curmax is None:
        curmax = 0
    ctr = curmax + 1
    try:
        start_time = datetime.time.fromisoformat(raw_data["start_time"])
        end_time = datetime.time.fromisoformat(raw_data["end_time"])
    except ValueError as err:
        flash_error("Invalid time: %s", err)
        return redirect(url_for(".edit_seminar_schedule", shortname=shortname), 301)
    for i in range(schedule_count):
        seminar_ctr = raw_data.get("seminar_ctr%s" % i)
        date = datetime.date.fromisoformat(raw_data["date%s" % i])
        if seminar_ctr:
            # existing talk
            seminar_ctr = int(seminar_ctr)
            talk = WebTalk(shortname, seminar_ctr, seminar=seminar)
            data = dict(talk.__dict__)
            for col in ["speaker", "speaker_affiliation", "speaker_email", "title"]:
                data[col] = process_user_input(raw_data["%s%s" % (col, i)], 'text', tz=seminar.timezone)
            if update_times:
                data["start_time"] = datetime.datetime.combine(date, start_time)
                data["end_time"] = datetime.datetime.combine(date, end_time)
            new_version = WebTalk(talk.seminar_id, data['seminar_ctr'], data=data)
            if new_version != talk:
                print(data)
                new_version.save()
        elif raw_data["speaker%s" % i].strip():
            # new talk
            talk = WebTalk(shortname, seminar=seminar, editing=True)
            data = dict(talk.__dict__)
            for col in ["speaker", "speaker_affiliation", "speaker_email", "title"]:
                data[col] = process_user_input(raw_data["%s%s" % (col, i)], 'text', tz=seminar.timezone)
            data["start_time"] = datetime.datetime.combine(date, start_time)
            data["end_time"] = datetime.datetime.combine(date, end_time)
            data["seminar_ctr"] = ctr
            ctr += 1
            new_version = WebTalk(talk.seminar_id, ctr, data=data)
            print(data)
            new_version.save()

    return redirect(url_for(".edit_seminar_schedule", shortname=shortname), 301)
