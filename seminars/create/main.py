# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from seminars.users.main import email_confirmed_required
from seminars import db
from seminars.create import create
from seminars.utils import (
    timezones,
    process_user_input,
    check_time,
    weekdays,
    short_weekdays,
    flash_warning,
    localize_time,
    clean_topics,
    clean_language,
    adapt_datetime,
    format_errmsg,
    show_input_errors,
)
from seminars.seminar import WebSeminar, can_edit_seminar, seminars_search
from seminars.talk import WebTalk, talks_max, talks_search, talks_lucky, can_edit_talk
from seminars.institution import (
    WebInstitution,
    can_edit_institution,
    institutions,
    institution_types,
    institution_known,
    clean_institutions,
)
from seminars.lock import get_lock
from seminars.users.pwdmanager import ilike_query
from lmfdb.utils import flash_error
import datetime
import pytz
from collections import defaultdict

SCHEDULE_LEN = 15  # Number of weeks to show in edit_seminar_schedule

@create.route("manage/")
@email_confirmed_required
def index():
    # TODO: use a join for the following query
    seminars = {}
    conferences = {}
    def key(elt):
        role_key = {'organizer': 0, 'curator': 1, 'creator': 3}
        return (role_key[elt[1]], elt[0].name)

    for rec in db.seminar_organizers.search({"email": ilike_query(current_user.email)},
                                            ["seminar_id", "curator"]):
        semid = rec['seminar_id']
        role = 'curator' if rec['curator'] else 'organizer'
        seminar = WebSeminar(semid)
        pair = (seminar, role)
        if seminar.is_conference:
            conferences[semid] = pair
        else:
            seminars[semid] = pair
    role = "creator"
    for semid in seminars_search({"owner": ilike_query(current_user.email)}, "shortname"):
        if semid not in seminars and semid not in conferences:
            seminar = WebSeminar(semid)
            pair = (seminar, role)
            if seminar.is_conference:
                conferences[semid] = pair
            else:
                seminars[semid] = pair
    seminars = sorted(seminars.values(), key=key)
    conferences = sorted(conferences.values(), key=key)

    manage = "Manage" if current_user.is_organizer else "Create"
    return render_template(
        "create_index.html",
        seminars=seminars,
        conferences=conferences,
        institution_known=institution_known,
        institutions=institutions(),
        section=manage,
        subsection="home",
        title=manage,
        user_is_creator=current_user.is_creator,
    )


@create.route("edit/seminar/", methods=["GET", "POST"])
@email_confirmed_required
def edit_seminar():
    if request.method == "POST":
        data = request.form
    else:
        data = request.args
    shortname = data.get("shortname", "")
    new = data.get("new") == "yes"
    resp, seminar = can_edit_seminar(shortname, new)
    if resp is not None:
        return resp
    if new:
        seminar.is_conference = process_user_input(data.get("is_conference"), "boolean", None)
        if seminar.is_conference:
            seminar.frequency = 1
            seminar.per_day = 4
        seminar.name = data.get("name", "")
        seminar.institutions = clean_institutions(data.get("institutions"))
        if seminar.institutions:
            seminar.timezone = db.institutions.lookup(seminar.institutions[0], "timezone")
    lock = get_lock(shortname, data.get("lock"))
    title = "conference" if seminar.is_conference else "seminar"
    title = "Create " + title if new else "Edit " + title + " properties"
    manage = "Manage" if current_user.is_organizer else "Create"
    return render_template(
        "edit_seminar.html",
        seminar=seminar,
        title=title,
        section=manage,
        subsection="editsem",
        institutions=institutions(),
        weekdays=weekdays,
        timezones=timezones,
        lock=lock,
    )


@create.route("delete/seminar/<shortname>")
@email_confirmed_required
def delete_seminar(shortname):
    seminar = WebSeminar(shortname)
    manage = "Manage" if current_user.is_organizer else "Create"
    lock = get_lock(shortname, request.args.get("lock"))

    def failure():
        return render_template(
            "edit_seminar.html",
            seminar=seminar,
            title="Edit properties",
            section=manage,
            subsection="editsem",
            institutions=institutions(),
            weekdays=weekdays,
            timezones=timezones,
            lock=lock,
        )

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
@email_confirmed_required
def delete_talk(semid, semctr):
    talk = WebTalk(semid, semctr)

    def failure():
        return render_template(
            "edit_talk.html",
            talk=talk,
            seminar=talk.seminar,
            title="Edit talk",
            section="Manage",
            subsection="edittalk",
            institutions=institutions(),
            timezones=timezones,
        )

    if not talk.user_can_delete():
        flash_error("Only the organizers of a seminar can delete talks in it")
        return failure()
    else:
        if talk.delete():
            flash("Talk deleted")
            return redirect(url_for(".edit_seminar_schedule", shortname=talk.seminar_id), 302)
        else:
            flash_error("Only the organizers of a seminar can delete talks in it")
            return failure()


@create.route("save/seminar/", methods=["POST"])
@email_confirmed_required
def save_seminar():
    raw_data = request.form
    shortname = raw_data["shortname"]
    new = raw_data.get("new") == "yes"
    resp, seminar = can_edit_seminar(shortname, new)
    if resp is not None:
        return resp
    errmsgs = []

    if seminar.new:
        data = {
            "shortname": shortname,
            "display": current_user.is_creator,
            "owner": current_user.email,
            "archived": False,
        }
    else:
        data = {
            "shortname": shortname,
            "display": seminar.display,
            "owner": seminar.owner,
        }
    # Have to get time zone first
    data["timezone"] = tz = raw_data.get("timezone")
    tz = pytz.timezone(tz)

    # This seems like a risky hack.  We want to treat start_time/end_time as times of day which will be converted
    # to timestamps offset from 1/1/2020 by process_user_input whtn the type is "time", but unilaterally converting
    # all timestamps to times seems risky.  What if we want the user to enter a datetime in the future?
    def replace(a):
        if a == "timestamp with time zone":
            return "time"
        return a

    for col in db.seminars.search_cols:
        if col in data:
            continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, replace(db.seminars.col_type[col]), tz=tz)
        except Exception as err:
            errmsgs.append(format_errmsg("Unable to process input %s for %s: {0}".format(err), val, col))
    for col in ["frequency","per_day"]:
        if data[col] is not None and data[col] < 1:
            errmsgs.append(format_errmsg("Unable to process input %s for %s: a positive integer is required", raw_data.get(col), col))
    data["institutions"] = clean_institutions(data.get("institutions"))
    data["topics"] = clean_topics(data.get("topics"))
    data["language"] = clean_language(data.get("language"))
    if not data["timezone"] and data["institutions"]:
        # Set time zone from institution
        data["timezone"] = WebInstitution(data["institutions"][0]).timezone
    organizer_data = []
    display_count = email_count = 0
    for i in range(10):
        D = {"seminar_id": seminar.shortname}
        for col in db.seminar_organizers.search_cols:
            if col in D:
                continue
            name = "org_%s%s" % (col, i)
            typ = db.seminar_organizers.col_type[col]
            try:
                val = raw_data.get(name)
                if val == "":
                    D[col] = None
                elif val is None:
                    D[col] = False if type == "boolean" else None  # checkboxes
                else:
                    D[col] = process_user_input(val, typ, tz=tz)
                # if col == 'homepage' and val and not val.startswith("http"):
                #     D[col] = "http://" + data[col]
            except Exception as err:
                errmsgs.append(format_errmsg("Unable to process input %s for %s: {0}".format(err), val, col))
        if D.get("homepage") or D.get("email") or D.get("full_name"):
            if not D.get("full_name"):
                errmsgs.append(format_errmsg("Organizer %s cannot be blank", "name"))
            D["order"] = len(organizer_data)
            # WARNING the header on the template says organizer
            # but it sets the database column curator, so the 
            # boolean needs to be inverted
            D["curator"] = not D["curator"]
            if D["display"]:
                display_count += 1
            if D["email"]:
                email_count += 1
            organizer_data.append(D)
    if display_count == 0:
       errmsgs.append(format_errmsg("At least one organizer or curator must be displayed."))
    if email_count == 0:
       errmsgs.append(format_errmsg("At least one organizer or curator needs %s set to ensure that someone can maintain this listing.<br>%s", "email",
                                    "Note that the email will not be public if homepage is set or display is not checked, it is used only to identify the organizer."))
    # Don't try to create new_version using invalid input
    if errmsgs:
        return show_input_errors(errmsgs)
    new_version = WebSeminar(shortname, data=data, organizer_data=organizer_data)
    if check_time(new_version.start_time, new_version.end_time):
        errmsgs.append(format_errmsg("Incompatible or invalid start time %s and end time %s", new_version.start_time, new_version.end_time))
        return show_input_errors(errmsgs)
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
    return redirect(url_for(".edit_seminar", shortname=shortname), 302)


@create.route("edit/institution/", methods=["GET", "POST"])
@email_confirmed_required
def edit_institution():
    if request.method == "POST":
        data = request.form
    else:
        data = request.args
    shortname = data.get("shortname", "")
    new = data.get("new") == "yes"
    resp, institution = can_edit_institution(shortname, new)
    if resp is not None:
        return resp
    if new:
        institution.name = data.get("name", "")
    # Don't use locks for institutions since there's only one non-admin able to edit.
    title = "Create institution" if new else "Edit institution"
    return render_template(
        "edit_institution.html",
        institution=institution,
        institution_types=institution_types,
        timezones=timezones,
        title=title,
        section="Manage",
        subsection="editinst",
    )


@create.route("save/institution/", methods=["POST"])
@email_confirmed_required
def save_institution():
    raw_data = request.form
    shortname = raw_data["shortname"]
    new = raw_data.get("new") == "yes"
    resp, institution = can_edit_institution(shortname, new)
    if resp is not None:
        return resp

    data = {}
    data["timezone"] = tz = raw_data.get("timezone", "UTC")
    tz = pytz.timezone(tz)
    for col in db.institutions.search_cols:
        if col in data:
            continue
        try:
            val = raw_data.get(col)
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.institutions.col_type[col], tz=tz)
            if col == "admin":
                userdata = db.users.lookup(val)
                if userdata is None:
                    raise ValueError("%s must have account on this site" % val)
            if col == "homepage" and val and not val.startswith("http"):
                data[col] = "http://" + data[col]
            if col == "access" and val not in ["open", "users", "endorsed"]:
                raise ValueError("Invalid access type")
        except Exception as err:
            # TODO: this probably needs to be a redirect to change the URL?  We want to save the data the user entered.
            flash_error("Error processing %s: %s" % (col, err))
            institution = WebInstitution(shortname, data=raw_data)
            return render_template(
                "edit_institution.html",
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
    return redirect(url_for(".edit_institution", shortname=shortname), 302)


@create.route("edit/talk/<seminar_id>/<seminar_ctr>/<token>")
def edit_talk_with_token(seminar_id, seminar_ctr, token):
    # For emailing, where encoding ampersands in a mailto link is difficult
    return redirect(
        url_for(".edit_talk", seminar_id=seminar_id, seminar_ctr=seminar_ctr, token=token), 302,
    )


@create.route("edit/talk/", methods=["GET", "POST"])
def edit_talk():
    if request.method == "POST":
        data = request.form
    else:
        data = request.args
    token = data.get("token", "")
    resp, talk = can_edit_talk(data.get("seminar_id", ""), data.get("seminar_ctr", ""), token)
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
            return redirect(url_for(".edit_seminar_schedule", shortname=talk.seminar_id), 302)
        talk.start_time = start_time
        talk.end_time = end_time
    # lock = get_lock(seminar_id, data.get("lock"))
    title = "Create talk" if talk.new else "Edit talk"
    return render_template(
        "edit_talk.html",
        talk=talk,
        seminar=talk.seminar,
        title=title,
        section="Manage",
        subsection="edittalk",
        institutions=institutions(),
        timezones=timezones,
        token=token,
        **extras
    )


@create.route("save/talk/", methods=["POST"])
def save_talk():
    raw_data = request.form
    token = raw_data.get("token", "")
    resp, talk = can_edit_talk(
        raw_data.get("seminar_id", ""), raw_data.get("seminar_ctr", ""), token
    )
    if resp is not None:
        return resp
    errmsgs = []

    data = {
        "seminar_id": talk.seminar_id,
        "token": talk.token,
        "display": talk.display,  # could be being edited by anonymous user
    }
    if talk.new:
        curmax = talks_max("seminar_ctr", {"seminar_id": talk.seminar_id})
        if curmax is None:
            curmax = 0
        data["seminar_ctr"] = curmax + 1
    else:
        data["seminar_ctr"] = talk.seminar_ctr
    default_tz = talk.seminar.timezone
    if not default_tz:
        default_tz = "UTC"
    data["timezone"] = tz = raw_data.get("timezone", default_tz)
    tz = pytz.timezone(tz)
    for col in db.talks.search_cols:
        if col in data:
            continue
        try:
            val = raw_data.get(col, "").strip()
            if not val:
                data[col] = None
            else:
                data[col] = process_user_input(val, db.talks.col_type[col], tz=tz)
            if col == "speaker_homepage" and val and not val.startswith("http"):
                data[col] = "http://" + data[col]
            if col == "access" and val not in ["open", "users", "endorsed"]:
                raise ValueError("Invalid access type")
        except Exception as err:
            errmsgs.append(format_errmsg("Unable to process input %s for %s: {0}".format(err), val, col))
    data["topics"] = clean_topics(data.get("topics"))
    data["language"] = clean_language(data.get("language"))
    # Don't try to create new_version using invalid input
    if errmsgs:
        return show_input_errors(errmsgs)
    new_version = WebTalk(talk.seminar_id, data["seminar_ctr"], data=data)
    if check_time(new_version.start_time, new_version.end_time, check_past=True):
        errmsgs.append(format_errmsg("Incompatible or invalid start time %s and end time %s", new_version.start_time, new_version.end_time))
        return show_input_errors(errmsgs)
    if new_version == talk:
        flash("No changes made to talk.")
    else:
        new_version.save()
        edittype = "created" if talk.new else "edited"
        flash("Talk successfully %s!" % edittype)
    edit_kwds = dict(seminar_id=new_version.seminar_id, seminar_ctr=new_version.seminar_ctr)
    if token:
        edit_kwds["token"] = token
    else:
        edit_kwds.pop("token", None)
    return redirect(url_for(".edit_talk", **edit_kwds), 302)


def make_date_data(seminar, data):
    tz = seminar.tz
    def parse_date(key):
        date = data.get(key)
        if date:
            try:
                return process_user_input(date, "date", tz)
            except ValueError:
                pass
    begin = parse_date("begin")
    end = parse_date("end")
    frequency = data.get("frequency")
    try:
        frequency = int(frequency)
    except Exception:
        frequency = None
    if not frequency or frequency < 0:
        frequency = seminar.frequency
        if not frequency or frequency < 0:
            frequency = 1 if seminar.is_conference else 7
    try:
        weekday = short_weekdays.index(data.get("weekday", "")[:3])
    except ValueError:
        weekday = None
    if weekday is None:
        weekday = seminar.weekday
    shortname = seminar.shortname
    day = datetime.timedelta(days=1)
    now = datetime.datetime.now(tz=tz)
    today = now.date()
    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if begin is None or seminar.start_time is None or seminar.end_time is None:
        future_talk = talks_lucky(
            {"seminar_id": shortname, "start_time": {"$exists": True, "$gte": midnight_today}}, sort=["start_time"]
        )
        last_talk = talks_lucky(
            {"seminar_id": shortname, "start_time": {"$exists": True, "$lt": midnight_today}}, sort=[("start_time", -1)],
        )

    if begin is None:
        if seminar.is_conference:
            if seminar.start_date:
                begin = seminar.start_date
            else:
                begin = today
        else:
            if weekday is not None and frequency == 7:
                begin = today
                # Will set to next weekday below
            else:
                # Try to figure out a plan from future and past talks
                if future_talk is None:
                    if last_talk is None:
                        # Give up
                        begin = today
                    else:
                        begin = last_talk.start_time.date()
                        while begin < today:
                            begin += frequency * day
                else:
                    begin = future_talk.start_time.date()
                    while begin >= today:
                        begin -= frequency * day
                    begin += frequency * day
    if not seminar.is_conference and seminar.weekday is not None:
        # Weekly meetings: take the next one
        while begin.weekday() != weekday:
            begin += day
    if end is None:
        if seminar.is_conference:
            if seminar.end_date:
                end = seminar.end_date
                schedule_len = int((end - begin) / (frequency*day)) + 1
            else:
                end = begin + 6*day
                schedule_len = 7
        else:
            end = begin + (SCHEDULE_LEN-1)*frequency*day
            schedule_len = SCHEDULE_LEN
    else:
        schedule_len = abs(int((end - begin) / (frequency*day))) + 1
    seminar.frequency = frequency
    data["begin"] = seminar.show_input_date(begin)
    data["end"] = seminar.show_input_date(end)
    midnight_begin = localize_time(datetime.datetime.combine(begin, datetime.time()), tz)
    midnight_end = localize_time(datetime.datetime.combine(end, datetime.time()), tz)
    # add a day since we want to allow talks on the final day
    if end < begin:
        # Only possible by user input
        frequency = -frequency
        query = {"$gte": midnight_end, "$lt": midnight_begin + day}
    else:
        query = {"$gte": midnight_begin, "$lt": midnight_end + day}
    schedule_days = [begin + i * frequency * day for i in range(schedule_len)]
    scheduled_talks = list(
        talks_search({"seminar_id": shortname, "start_time": query})
    )
    by_date = defaultdict(list)
    for T in scheduled_talks:
        by_date[adapt_datetime(T.start_time, tz).date()].append(T)
    all_dates = sorted(set(schedule_days + list(by_date)), reverse=(end < begin))
    # Fill in by_date with Nones up to the per_day value
    for date in all_dates:
        by_date[date].extend([None] * (seminar.per_day - len(by_date[date])))
    if seminar.start_time is None:
        if future_talk is not None and future_talk.start_time:
            seminar.start_time = future_talk.start_time
        elif last_talk is not None and last_talk.start_time:
            seminar.start_time = last_talk.start_time
    if seminar.end_time is None:
        if future_talk is not None and future_talk.start_time:
            seminar.end_time = future_talk.end_time
        elif last_talk is not None and last_talk.start_time:
            seminar.end_time = last_talk.end_time
    return seminar, all_dates, by_date

@create.route("edit/schedule/", methods=["GET", "POST"])
@email_confirmed_required
def edit_seminar_schedule():
    # It would be good to have a version of this that worked for a conference, but that's a project for later
    if request.method == "POST":
        data = dict(request.form)
    else:
        data = dict(request.args)
    shortname = data.get("shortname", "")
    resp, seminar = can_edit_seminar(shortname, new=False)
    if resp is not None:
        return resp
    seminar, all_dates, by_date = make_date_data(seminar, data)
    title = "Edit %s schedule" % ("conference" if seminar.is_conference else "seminar")
    return render_template(
        "edit_seminar_schedule.html",
        seminar=seminar,
        all_dates=all_dates,
        by_date=by_date,
        weekdays=weekdays,
        raw_data=data,
        title=title,
        section="Manage",
        subsection="schedule",
    )


required_cols = ["date", "time", "speaker"]
optional_cols = ["speaker_affiliation", "speaker_email", "title"]


@create.route("save/schedule/", methods=["POST"])
@email_confirmed_required
def save_seminar_schedule():
    raw_data = request.form
    shortname = raw_data["shortname"]
    resp, seminar = can_edit_seminar(shortname, new=False)
    if resp is not None:
        return resp
    frequency = raw_data.get("frequency")
    try:
        frequency = int(frequency)
    except Exception:
        pass
    schedule_count = int(raw_data["schedule_count"])
    # FIXME not being used
    # update_times = bool(raw_data.get("update_times"))
    curmax = talks_max("seminar_ctr", {"seminar_id": shortname})
    if curmax is None:
        curmax = 0
    ctr = curmax + 1
    updated = 0
    warned = False
    for i in list(range(schedule_count)):
        seminar_ctr = raw_data.get("seminar_ctr%s" % i)
        speaker = process_user_input(
            raw_data.get("speaker%s" % i, ""), "text", tz=seminar.timezone
        )
        if not speaker:
            if not warned and any(
                    raw_data.get("%s%s" % (col, i), "").strip() for col in optional_cols
            ):
                warned = True
                flash_warning("Talks are only saved if you specify a speaker")
            continue
        date = raw_data.get("date%s" % i).strip()
        if date:
            try:
                date = process_user_input(date, "date", tz=seminar.tz)
            except ValueError as err:
                flash_error("invalid date %s: {0}".format(err), date)
                redirect(url_for(".edit_seminar_schedule", shortname=shortname, **raw_data), 302)
        else:
            date = None
        time_input = raw_data.get("time%s" % i, "").strip()
        if time_input:
            try:
                time_split = time_input.split("-")
                if len(time_split) == 1:
                    raise ValueError("Must specify both start and end times")
                elif len(time_split) > 2:
                    raise ValueError("More than one hyphen")
                # TODO: clean this up
                start_time = process_user_input(time_split[0], "time", seminar.tz).time()
                end_time = process_user_input(time_split[1], "time", seminar.tz).time()
                if check_time(start_time, end_time):
                    raise ValueError
            except ValueError as err:
                if str(err):
                    flash_error("invalid time range %s: {0}".format(err), time_input)
                return redirect(url_for(".edit_seminar_schedule", **raw_data), 302)
        else:
            start_time = end_time = None
        if any(X is None for X in [start_time, end_time, date]):
            flash_error(
                "You must give a date, start and end time for %s" % speaker
            )
            return redirect(url_for(".edit_seminar_schedule", **raw_data), 302)
        if seminar_ctr:
            # existing talk
            seminar_ctr = int(seminar_ctr)
            talk = WebTalk(shortname, seminar_ctr, seminar=seminar)
        else:
            # new talk
            talk = WebTalk(shortname, seminar=seminar, editing=True)
        data = dict(talk.__dict__)
        data["speaker"] = speaker
        for col in optional_cols:
            data[col] = process_user_input(
                raw_data.get("%s%s" % (col, i), ""), "text", tz=seminar.timezone
            )
        data["start_time"] = localize_time(datetime.datetime.combine(date, start_time), seminar.tz)
        data["end_time"] = localize_time(datetime.datetime.combine(date, end_time), seminar.tz)
        if seminar_ctr:
            new_version = WebTalk(talk.seminar_id, data["seminar_ctr"], data=data)
            if new_version != talk:
                updated += 1
                new_version.save()
        else:
            data["seminar_ctr"] = ctr
            ctr += 1
            new_version = WebTalk(talk.seminar_id, ctr, data=data)
            new_version.save()

    if raw_data.get("detailctr"):
        return redirect(
            url_for(
                ".edit_talk", seminar_id=shortname, seminar_ctr=int(raw_data.get("detailctr")),
            ),
            302,
        )
    else:
        if updated or ctr > curmax + 1:
            flash("%s talks updated, %s talks created" % (updated, ctr - curmax - 1))
        if warned:
            return redirect(url_for(".edit_seminar_schedule", **raw_data), 302)
        else:
            return redirect(url_for(".edit_seminar_schedule", shortname=shortname, begin=raw_data.get('begin'), end=raw_data.get('end'), frequency=raw_data.get('frequency'), weekday=raw_data.get('weekday')), 302)
