# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from seminars.users.main import email_confirmed_required
from seminars import db
from seminars.app import app
from seminars.create import create
from seminars.utils import timezones, process_user_input, check_time, weekdays, flash_warning, localize_time, clean_topics
from seminars.seminar import WebSeminar, seminars_lucky, seminars_lookup, can_edit_seminar
from seminars.talk import WebTalk, talks_lookup, talks_max, talks_search, talks_lucky, can_edit_talk
from seminars.institution import WebInstitution, can_edit_institution, institutions, institution_types, institution_known, clean_institutions
from seminars.lock import get_lock
from lmfdb.utils import to_dict, flash_error
import datetime, pytz, json
from collections import defaultdict

SCHEDULE_LEN = 15 # Number of weeks to show in edit_seminar_schedule

@create.route("manage/")
@login_required
@email_confirmed_required
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
    manage = "Manage" if current_user.is_organizer() else "Create"
    return render_template("create_index.html",
                           seminars=seminars,
                           conferences=conferences,
                           institution_known=institution_known,
                           section=manage,
                           subsection="home",
                           title=manage,
                           user_is_creator=current_user.is_creator())

@create.route("edit/seminar/", methods=["GET", "POST"])
@login_required
@email_confirmed_required
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
    title = "Create seminar" if new else "Edit properties"
    manage = "Manage" if current_user.is_organizer() else "Create"
    return render_template("edit_seminar.html",
                           seminar=seminar,
                           title=title,
                           section=manage,
                           subsection="editsem",
                           institutions=institutions(),
                           weekdays=weekdays,
                           timezones=timezones,
                           lock=lock)

@create.route("delete/seminar/<shortname>")
@login_required
@email_confirmed_required
def delete_seminar(shortname):
    seminar = WebSeminar(shortname)
    manage = "Manage" if current_user.is_organizer() else "Create"
    lock = get_lock(shortname, request.args.get("lock"))
    def failure():
        return render_template("edit_seminar.html",
                           seminar=seminar,
                           title="Edit properties",
                           section=manage,
                           subsection="editsem",
                           institutions=institutions(),
                           weekdays=weekdays,
                           timezones=timezones,
                           lock=lock)
    if not seminar.user_can_delete():
        flash_error("Only the owner of the seminar can delete it")
        return failure()
    else:
        if seminar.delete():
            flash("Seminar deleted")
            return redirect(url_for(".index"))
        else:
            flash_error("Only the owner of the seminar can delete it")
            return failure()

@create.route("delete/talk/<semid>/<semctr>")
@login_required
@email_confirmed_required
def delete_talk(semid,semctr):
    talk = WebTalk(semid, semctr)
    lock = get_lock(id, request.args.get("lock"))
    def failure():
        title = "Create talk" if talk.new else "Edit talk"
        return render_template("edit_talk.html",
                               talk=talk,
                               seminar=talk.seminar,
                               title=title,
                               section="Manage",
                               subsection="edittalk",
                               institutions=institutions(),
                               timezones=timezones,
                               #token=token,
                               **extras)
    if not talk.user_can_delete():
        flash_error("Only the organisers of a seminar can delete talks in it")
        return failure()
    else:
        if talk.delete():
            flash("Talk deleted")
            return redirect(url_for(".index"))
        else:
            flash_error("Only the organisers of a seminar can delete talks in it")
            return failure()


@create.route("save/seminar/", methods=["POST"])
@login_required
@email_confirmed_required
def save_seminar():
    raw_data = request.form
    shortname = raw_data["shortname"]
    new = (raw_data.get("new") == "yes")
    resp, seminar = can_edit_seminar(shortname, new)
    if resp is not None:
        return resp
    def make_error(shortname, col=None, err=None):
        if err is not None:
            flash_error("Error processing %s: {0}".format(err), col)
        seminar = WebSeminar(shortname, data=raw_data)
        manage = "Manage" if current_user.is_organizer() else "Create"
        return render_template("edit_seminar.html",
                               seminar=seminar,
                               title="Edit seminar error",
                               section=manage,
                               institutions=institutions(),
                               lock=None)

    if seminar.new:
        data = {'shortname': shortname,
                'display': current_user.is_creator(),
                'owner': current_user.email,
                'archived':False}
    else:
        data = {'shortname': shortname,
                'display': seminar.display,
                'owner': seminar.owner}
    # Have to get time zone first
    data['timezone'] = tz = raw_data.get('timezone')
    tz = pytz.timezone(tz)
    def replace(a):
        if a == "timestamp with time zone":
            return "time"
        return a
    for col in db.seminars.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, replace(db.seminars.col_type[col]), tz=tz)
        except Exception as err:
            return make_error(shortname, col, err)
    data['institutions'] = clean_institutions(data.get('institutions'))
    data['topics'] = clean_topics(data.get('topics'))
    if not data['timezone'] and data['institutions']:
        # Set time zone from institution
        data['timezone'] = WebInstitution(data['institutions'][0]).timezone
    organizer_data = []
    for i in range(10):
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
                return make_error(shortname, col, err)
        if D.get('email') or D.get('full_name'):
            D['order'] = len(organizer_data)
            organizer_data.append(D)
    new_version = WebSeminar(shortname, data=data, organizer_data=organizer_data)
    if check_time(new_version.start_time, new_version.end_time):
        return make_error(shortname)
    if seminar.new or new_version != seminar:
        new_version.save()
        edittype = "created" if new else "edited"
        flash("Seminar %s successfully!" % edittype)
    elif seminar.organizer_data == new_version.organizer_data:
        flash("No changes made to seminar.")
    if seminar.new or seminar.organizer_data != new_version.organizer_data:
        new_version.save_organizers()
        if not seminar.new:
            flash("Seminar organizers updated!")
    return redirect(url_for(".edit_seminar", shortname=shortname), 301)

@create.route("edit/institution/", methods=["GET", "POST"])
@login_required
@email_confirmed_required
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
                           section="Manage",
                           subsection="editinst",
    )

@create.route("save/institution/", methods=["POST"])
@login_required
@email_confirmed_required
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
                                   section="Manage",
                                   subsection="editinst",
            )
    new_version = WebInstitution(shortname, data=data)
    if new_version == institution:
        flash("No changes made to institution.")
    else:
        new_version.save()
        edittype = "created" if new else "edited"
        flash("Institution %s successfully!" % edittype)
    return redirect(url_for(".edit_institution", shortname=shortname), 301)

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
    token = data.get("token", "")
    resp, talk = can_edit_talk(
        data.get("seminar_id", ""),
        data.get("seminar_ctr", ""),
        token)
    if resp is not None:
        return resp
    if token:
        # Also want to override top menu
        from seminars.utils import top_menu
        menu = top_menu()
        menu[2] = (url_for("create.index"), "", "Manage")
        extras = {"top_menu": menu}
    else:
        extras = {}
    # The seminar schedule page adds in a date and times
    if data.get("date", "").strip():
        tz = pytz.timezone(talk.seminar.timezone)
        date = process_user_input(data["date"], "date", tz)
        try:
            # TODO: clean this up
            start_time = process_user_input(data.get("start_time"), "time", tz)
            end_time = process_user_input(data.get("end_time"), "time", tz)
            start_time = localize_time(datetime.datetime.combine(date, start_time), tz)
            end_time = localize_time(datetime.datetime.combine(date, end_time), tz)
        except ValueError:
            return redirect(url_for(".edit_seminar_schedule", shortname=talk.seminar_id), 301)
        talk.start_time = start_time
        talk.end_time = end_time
    #lock = get_lock(seminar_id, data.get("lock"))
    title = "Create talk" if talk.new else "Edit talk"
    return render_template("edit_talk.html",
                           talk=talk,
                           seminar=talk.seminar,
                           title=title,
                           section="Manage",
                           subsection="edittalk",
                           institutions=institutions(),
                           timezones=timezones,
                           token=token,
                           **extras)

@create.route("save/talk/", methods=["POST"])
def save_talk():
    raw_data = request.form
    token = raw_data.get("token", "")
    resp, talk = can_edit_talk(
        raw_data.get("seminar_id", ""),
        raw_data.get("seminar_ctr", ""),
        token)
    if resp is not None:
        return resp

    def make_error(talk, col=None, err=None):
        if err is not None:
            flash_error("Error processing %s: {0}".format(err), col)
        talk = WebTalk(talk.seminar_id, talk.seminar_ctr, data=raw_data)
        title = "Create talk error" if talk.new else "Edit talk error"
        return render_template("edit_talk.html",
                               talk=talk,
                               seminar=talk.seminar,
                               title=title,
                               section="Manage",
                               subsection="edittalk",
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
    default_tz = talk.seminar.timezone
    if not default_tz:
        default_tz = 'UTC'
    data['timezone'] = tz = raw_data.get('timezone', default_tz)
    tz = pytz.timezone(tz)
    for col in db.talks.search_cols:
        if col in data: continue
        try:
            val = raw_data.get(col, "").strip()
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.talks.col_type[col], tz=tz)
            if col == 'speaker_homepage' and val and not val.startswith("http"):
                data[col] = "http://" + data[col]
            if col == "access" and val not in ["open", "users", "endorsed"]:
                raise ValueError("Invalid access type")
        except Exception as err:
            return make_error(talk, col, err)
    data['topics'] = clean_topics(data.get('topics'))
    new_version = WebTalk(talk.seminar_id, data['seminar_ctr'], data=data)
    if check_time(new_version.start_time, new_version.end_time):
        return make_error(talk)
    if new_version == talk:
        flash("No changes made to talk.")
    else:
        new_version.save()
        edittype = "created" if talk.new else "edited"
        flash("Talk successfully %s!" % edittype)
    edit_kwds = dict(seminar_id=new_version.seminar_id, seminar_ctr=new_version.seminar_ctr)
    if token:
        edit_kwds['token'] = token
    else:
        edit_kwds.pop('token', None)
    return redirect(url_for(".edit_talk", **edit_kwds), 301)

def make_date_data(seminar):
    shortname = seminar.shortname
    now = datetime.datetime.now(tz=pytz.timezone(seminar.timezone))
    today = now.date()
    day = datetime.timedelta(days=1)
    last_talk = talks_lucky({'seminar_id': shortname, 'start_time':{'$lte': now}}, sort=[('start_time', -1)])
    future_talks = list(talks_search({'seminar_id': shortname, 'start_time':{'$gte': now}}, sort=['start_time']))
    by_date = defaultdict(list)
    for T in future_talks:
        by_date[T.start_time.date()].append(T)
    frequency = seminar.frequency
    if last_talk is None:
        if seminar.weekday is None:
            if future_talks:
                seminar.weekday = future_talks[0].start_time.weekday()
            else:
                # No talks and no weekday information.  We just use today.
                seminar.weekday = datetime.datetime.now(tz=pytz.timezone(seminar.timezone)).weekday()
        next_date = today
        while next_date.weekday() != seminar.weekday:
            next_date += day
    elif frequency and frequency > 0:
        next_date = last_talk.start_time.date()
        while next_date < today:
            next_date += seminar.frequency * day
    else:
        next_date = today
        frequency = None
    if frequency is None:
        schedule_days = []
    else:
        schedule_days = [next_date + i*frequency*day for i in range(SCHEDULE_LEN)]
    all_dates = sorted(set(schedule_days + list(by_date)))
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
    return seminar, all_dates, by_date

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
    seminar, all_dates, by_date = make_date_data(seminar)
    title = "Edit schedule"
    return render_template("edit_seminar_schedule.html",
                           seminar=seminar,
                           all_dates=all_dates,
                           by_date=by_date,
                           weekdays=weekdays,
                           raw_data=data,
                           title=title,
                           section="Manage",
                           subsection="schedule",
    )

non_speaker_cols = ["speaker_affiliation", "speaker_email", "title"]
@create.route("save/schedule/", methods=["POST"])
def save_seminar_schedule():
    raw_data = request.form
    shortname = raw_data["shortname"]
    resp, seminar = can_edit_seminar(shortname, new=False)
    if resp is not None:
        return resp
    schedule_count = int(raw_data["schedule_count"])
    # FIXME not being used
    # update_times = bool(raw_data.get("update_times"))
    curmax = talks_max('seminar_ctr', {'seminar_id': shortname})
    if curmax is None:
        curmax = 0
    ctr = curmax + 1
    updated = 0
    warned = False
    for i in list(range(schedule_count)) + ['X']:
        seminar_ctr = raw_data.get("seminar_ctr%s" % i)
        if i == 'X':
            date = raw_data.get("dateX").strip()
            if date:
                try:
                    date = process_user_input(date, "date", tz=seminar.tz)
                except ValueError as err:
                    flash_error("invalid date %s: {0}".format(err), date)
                    redirect(url_for(".edit_seminar_schedule", shortname=shortname, **raw_data), 301)
            else:
                date = None
        else:
            date = datetime.date.fromisoformat(raw_data["date%s" % i])
        if seminar_ctr:
            # existing talk
            seminar_ctr = int(seminar_ctr)
            talk = WebTalk(shortname, seminar_ctr, seminar=seminar)
            data = dict(talk.__dict__)
            for col in ["speaker"] + non_speaker_cols:
                data[col] = process_user_input(raw_data.get("%s%s" % (col, i), ''), 'text', tz=seminar.timezone)
            new_version = WebTalk(talk.seminar_id, data['seminar_ctr'], data=data)
            if new_version != talk:
                updated += 1
                new_version.save()
        elif raw_data["speaker%s" % i].strip() and date:
            # new talk
            talk = WebTalk(shortname, seminar=seminar, editing=True)
            data = dict(talk.__dict__)
            for col in ["speaker", "speaker_affiliation", "speaker_email", "title"]:
                data[col] = process_user_input(raw_data.get("%s%s" % (col, i), ''), 'text', tz=seminar.timezone)
            time_input = raw_data.get("time%s" % i, "").strip()
            if time_input: # seminar may not have a time, in which case user can enter one
                try:
                    time_split = time_input.split("-")
                    if len(time_split) == 1:
                        raise ValueError("Must specify both start and end times")
                    elif len(time_split) > 2:
                        raise ValueError("More than one hyphen")
                    # TODO: clean this up
                    start_time = process_user_input(time_split[0], "time", seminar.tz).time()
                    end_time = process_user_input(time_split[1], "time", seminar.tz).time()
                except ValueError as err:
                    flash_error("invalid time range %s: {0}".format(err), time_input)
                    return redirect(url_for(".edit_seminar_schedule", **raw_data), 301)
            elif seminar.start_time is None or seminar.end_time is None:
                flash_error("Since the seminar does not have a time specified, you must provide one")
                return redirect(url_for(".edit_seminar_schedule", **raw_data), 301)
            else:
                start_time = seminar.start_time.time()
                end_time = seminar.end_time.time()
            data["start_time"] = localize_time(datetime.datetime.combine(date, start_time), seminar.tz)
            data["end_time"] = localize_time(datetime.datetime.combine(date, end_time), seminar.tz)
            data["seminar_ctr"] = ctr
            ctr += 1
            new_version = WebTalk(talk.seminar_id, ctr, data=data)
            new_version.save()
        elif not warned and any(raw_data.get("%s%s" % (col, i), "").strip() for col in non_speaker_cols):
            warned = True
            flash_warning("Talks are only saved if you specify a speaker")

    if raw_data.get("detailctr"):
        return redirect(url_for(".edit_talk", seminar_id=shortname, seminar_ctr=int(raw_data.get("detailctr"))), 301)
    else:
        if updated or ctr > curmax + 1:
            flash("%s talks updated, %s talks created" % (updated, ctr - curmax - 1))
        if warned:
            return redirect(url_for(".edit_seminar_schedule", **raw_data), 301)
        else:
            return redirect(url_for(".edit_seminar_schedule", shortname=shortname), 301)
