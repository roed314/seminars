# -*- coding: utf-8 -*-
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from seminars.users.main import email_confirmed_required
from seminars import db
from seminars.create import create
from seminars.utils import (
    adapt_datetime,
    clean_language,
    clean_subjects,
    clean_topics,
    flash_warning,
    format_errmsg,
    format_input_errmsg,
    format_warning,
    localize_time,
    process_user_input,
    sanity_check_times,
    short_weekdays,
    show_input_errors,
    timezones,
    weekdays,
)
from seminars.seminar import (
    WebSeminar,
    can_edit_seminar,
    seminars_lookup,
    seminars_search,
)
from seminars.talk import (
    WebTalk,
    can_edit_talk,
    talks_lookup,
    talks_lucky,
    talks_max,
    talks_search,
)
from seminars.institution import (
    WebInstitution,
    can_edit_institution,
    clean_institutions,
    institution_known,
    institution_types,
    institutions,
)
from seminars.lock import get_lock
from seminars.users.pwdmanager import ilike_query, ilike_escape, userdb
from lmfdb.utils import flash_error
from lmfdb.backend.utils import IdentifierWrapper
from psycopg2.sql import SQL
import datetime
from datetime import timedelta
import pytz
from collections import defaultdict

SCHEDULE_LEN = 15  # Number of weeks to show in edit_seminar_schedule


@create.route("manage/")
@email_confirmed_required
def index():
    # TODO: use a join for the following query
    seminars = {}
    conferences = {}
    deleted_seminars = []
    deleted_talks = []

    def key(elt):
        role_key = {"organizer": 0, "curator": 1, "creator": 3}
        return (role_key[elt[1]], elt[0].name)

    for rec in db.seminar_organizers.search({"email": ilike_query(current_user.email)}, ["seminar_id", "curator"]):
        semid = rec["seminar_id"]
        role = "curator" if rec["curator"] else "organizer"
        seminar = WebSeminar(semid)
        pair = (seminar, role)
        if seminar.is_conference:
            conferences[semid] = pair
        else:
            seminars[semid] = pair
    role = "creator"
    for semid in seminars_search({"owner": ilike_query(current_user.email)}, "shortname", include_deleted=True):
        if semid not in seminars and semid not in conferences:
            seminar = WebSeminar(semid, deleted=True)  # allow deleted
            pair = (seminar, role)
            if seminar.deleted:
                deleted_seminars.append(seminar)
            elif seminar.is_conference:
                conferences[semid] = pair
            else:
                seminars[semid] = pair
    seminars = sorted(seminars.values(), key=key)
    conferences = sorted(conferences.values(), key=key)
    deleted_seminars.sort(key=lambda sem: sem.name)
    for semid, semctr in db._execute(
        # ~~* is case insensitive amtch
        SQL(
            """
SELECT DISTINCT ON ({Ttalks}.{Csemid}, {Ttalks}.{Csemctr}) {Ttalks}.{Csemid}, {Ttalks}.{Csemctr}
FROM {Ttalks} INNER JOIN {Tsems} ON {Ttalks}.{Csemid} = {Tsems}.{Csname}
WHERE {Tsems}.{Cowner} ~~* %s AND {Ttalks}.{Cdel} = %s AND {Tsems}.{Cdel} = %s
            """
        ).format(
            Ttalks=IdentifierWrapper("talks"),
            Tsems=IdentifierWrapper("seminars"),
            Csemid=IdentifierWrapper("seminar_id"),
            Csemctr=IdentifierWrapper("seminar_ctr"),
            Csname=IdentifierWrapper("shortname"),
            Cowner=IdentifierWrapper("owner"),
            Cdel=IdentifierWrapper("deleted"),
        ),
        [ilike_escape(current_user.email), True, False],
    ):
        talk = WebTalk(semid, semctr, deleted=True)
        deleted_talks.append(talk)
    deleted_talks.sort(key=lambda talk: (talk.seminar.name, talk.start_time))

    manage = "Manage" if current_user.is_organizer else "Create"
    return render_template(
        "create_index.html",
        seminars=seminars,
        conferences=conferences,
        deleted_seminars=deleted_seminars,
        deleted_talks=deleted_talks,
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
        subjects = clean_subjects(data.get("subjects"))
        if not subjects:
            return show_input_errors([format_errmsg("Please select at least one subject.")])
        else:
            seminar.subjects = subjects

        seminar.is_conference = process_user_input(data.get("is_conference"), "is_conference", "boolean", None)
        if seminar.is_conference:
            seminar.frequency = 1
            seminar.per_day = 4
        seminar.name = data.get("name", "")
        seminar.institutions = clean_institutions(data.get("institutions"))
        if seminar.institutions:
            seminar.timezone = db.institutions.lookup(seminar.institutions[0], "timezone")
    lock = get_lock(shortname, data.get("lock"))
    title = "Create series" if new else "Edit series"
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
    try:
        seminar = WebSeminar(shortname)
    except ValueError as err:
        flash_error(str(err))
        return redirect(url_for(".index"), 302)
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

    if not seminar or not seminar.user_can_delete():
        flash_error("Only the owner of the seminar can delete it")
        return failure()
    else:
        if seminar.delete():
            flash("Series deleted")
            return redirect(url_for(".deleted_seminar", shortname=shortname), 302)
        else:
            flash_error("Only the owner of the seminar can delete it")
            return failure()


@create.route("deleted/seminar/<shortname>")
@email_confirmed_required
def deleted_seminar(shortname):
    try:
        seminar = WebSeminar(shortname, deleted=True)
    except ValueError as err:
        flash_error(str(err))
        return redirect(url_for(".index"), 302)
    return render_template("deleted_seminar.html", seminar=seminar, title="Deleted")


@create.route("revive/seminar/<shortname>")
@email_confirmed_required
def revive_seminar(shortname):
    seminar = seminars_lookup(shortname, include_deleted=True)

    if seminar is None:
        flash_error("Series %s was deleted permanently", shortname)
        return redirect(url_for(".index"), 302)
    if not current_user.is_subject_admin(seminar) and seminar.owner != current_user:
        flash_error("You do not have permission to revive seminar %s", shortname)
        return redirect(url_for(".index"), 302)
    if not seminar.deleted:
        flash_error("Series %s was not deleted, so cannot be revived", shortname)
    else:
        db.seminars.update({"shortname": shortname}, {"deleted": False})
        db.talks.update({"seminar_id": shortname}, {"deleted": False})
        flash(
            "Series %s revived.  You should reset the organizers, and note that any users that were subscribed no longer are."
            % shortname
        )
    return redirect(url_for(".edit_seminar", shortname=shortname), 302)


@create.route("permdelete/seminar/<shortname>")
@email_confirmed_required
def permdelete_seminar(shortname):
    seminar = seminars_lookup(shortname, include_deleted=True)

    if seminar is None:
        flash_error("Series %s already deleted permanently", shortname)
        return redirect(url_for(".index"), 302)
    if not current_user.is_subject_admin(seminar) and seminar.owner != current_user:
        flash_error("You do not have permission to delete seminar %s", shortname)
        return redirect(url_for(".index"), 302)
    if not seminar.deleted:
        flash_error("You must delete seminar %s first", shortname)
        return redirect(url_for(".edit_seminar", shortname=shortname), 302)
    else:
        db.seminars.delete({"shortname": shortname})
        db.talks.delete({"seminar_id": shortname})
        flash("Series %s permanently deleted" % shortname)
        return redirect(url_for(".index"), 302)


@create.route("delete/talk/<semid>/<int:semctr>")
@email_confirmed_required
def delete_talk(semid, semctr):
    try:
        talk = WebTalk(semid, semctr)
    except ValueError as err:
        flash_error(str(err))
        return redirect(url_for(".edit_seminar_schedule", shortname=semid), 302)

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


@create.route("deleted/talk/<semid>/<int:semctr>")
@email_confirmed_required
def deleted_talk(semid, semctr):
    try:
        talk = WebTalk(semid, semctr, deleted=True)
    except ValueError as err:
        flash_error(str(err))
        return redirect(url_for(".edit_seminar_schedule", shortname=semid), 302)
    return render_template("deleted_talk.html", talk=talk, title="Deleted")


@create.route("revive/talk/<semid>/<int:semctr>")
@email_confirmed_required
def revive_talk(semid, semctr):
    talk = talks_lookup(semid, semctr, include_deleted=True)

    if talk is None:
        flash_error("Talk %s/%s was deleted permanently", semid, semctr)
        return redirect(url_for(".edit_seminar_schedule", shortname=semid), 302)
    if not current_user.is_subject_admin(talk) and talk.seminar.owner != current_user:
        flash_error("You do not have permission to revive this talk")
        return redirect(url_for(".index"), 302)
    if not talk.deleted:
        flash_error("Talk %s/%s was not deleted, so cannot be revived", semid, semctr)
        return redirect(url_for(".edit_talk", seminar_id=semid, seminar_ctr=semctr), 302)
    else:
        db.talks.update({"seminar_id": semid, "seminar_ctr": semctr}, {"deleted": False})
        flash("Talk revived.  Note that any users who were subscribed no longer are.")
        return redirect(url_for(".edit_seminar_schedule", shortname=semid), 302)


@create.route("permdelete/talk/<semid>/<int:semctr>")
@email_confirmed_required
def permdelete_talk(semid, semctr):
    talk = talks_lookup(semid, semctr, include_deleted=True)

    if talk is None:
        flash_error("Talk %s/%s already deleted permanently", semid, semctr)
        return redirect(url_for(".edit_seminar_schedule", shortname=semid), 302)
    if not current_user.is_subject_admin(talk) and talk.seminar.owner != current_user:
        flash_error("You do not have permission to delete this seminar")
        return redirect(url_for(".index"), 302)
    if not talk.deleted:
        flash_error("You must delete talk %s/%s first", semid, semctr)
        return redirect(url_for(".edit_talk", seminar_id=semid, seminar_ctr=semctr), 302)
    else:
        db.talks.delete({"seminar_id": semid, "seminar_ctr": semctr})
        flash("Talk %s/%s permanently deleted" % (semid, semctr))
        return redirect(url_for(".edit_seminar_schedule", shortname=semid), 302)


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

    for col in db.seminars.search_cols:
        if col in data:
            continue
        typ = db.seminars.col_type[col]
        ### Hack to be removed ###
        if col.endswith("time") and typ == "timestamp with time zone":
            typ = "time"
        try:
            val = raw_data.get(col, "")
            data[col] = None  # make sure col is present even if process_user_input fails
            data[col] = process_user_input(val, col, typ, tz)
        except Exception as err:  # should only be ValueError's but let's be cautious
            errmsgs.append(format_input_errmsg(err, val, col))
    if not data["name"]:
        errmsgs.append("The name cannot be blank")
    if seminar.is_conference and data["start_date"] and data["end_date"] and data["end_date"] < data["start_date"]:
        errmsgs.append("End date cannot precede start date")
    for col in ["frequency", "per_day"]:
        if data[col] is not None and data[col] < 1:
            errmsgs.append(format_input_errmsg("integer must be positive", data[col], col))
    data["institutions"] = clean_institutions(data.get("institutions"))
    data["topics"] = clean_topics(data.get("topics"))
    data["language"] = clean_language(data.get("language"))
    data["subjects"] = clean_subjects(data.get("subjects"))
    if not data["subjects"]:
        errmsgs.append(format_errmsg("Please select at least one subject."))
    if not data["timezone"] and data["institutions"]:
        # Set time zone from institution
        data["timezone"] = WebInstitution(data["institutions"][0]).timezone
    organizer_data = []
    contact_count = 0
    for i in range(10):
        D = {"seminar_id": seminar.shortname}
        for col in db.seminar_organizers.search_cols:
            if col in D:
                continue
            name = "org_%s%s" % (col, i)
            typ = db.seminar_organizers.col_type[col]
            try:
                val = raw_data.get(name, "")
                D[col] = None  # make sure col is present even if process_user_input fails
                D[col] = process_user_input(val, col, typ, tz)
            except Exception as err:  # should only be ValueError's but let's be cautious
                errmsgs.append(format_input_errmsg(err, val, col))
        if D["homepage"] or D["email"] or D["full_name"]:
            if not D["full_name"]:
                errmsgs.append(format_errmsg("Organizer name cannot be left blank"))
            D["order"] = len(organizer_data)
            # WARNING the header on the template says organizer
            # but it sets the database column curator, so the
            # boolean needs to be inverted
            D["curator"] = not D["curator"]
            if not errmsgs and D["display"] and D["email"] and not D["homepage"]:
                flash(
                    format_warning(
                        "The email address %s of organizer %s will be publicily visible.<br>%s",
                        D["email"],
                        D["full_name"],
                        "Set homepage or disable display to prevent this.",
                    ),
                    "error",
                )
            if D["email"]:
                r = db.users.lookup(D["email"])
                if r and r["email_confirmed"]:
                    if D["full_name"] != r["name"]:
                        errmsgs.append(
                            format_errmsg(
                                "Organizer name %s does not match the name %s of the account with email address %s",
                                D["full_name"],
                                r["name"],
                                D["email"],
                            )
                        )
                    else:
                        if D["homepage"] and r["homepage"] and D["homepage"] != r["homepage"]:
                            flash(
                                format_warning(
                                    "The homepage %s does not match the homepage %s of the account with email address %s, please correct if unintended.",
                                    D["homepage"],
                                    r["homepage"],
                                    D["email"],
                                )
                            )
                        if D["display"]:
                            contact_count += 1

            organizer_data.append(D)
    if contact_count == 0:
        errmsgs.append(
            format_errmsg(
                "There must be at least one displayed organizer or curator with a %s so that there is a contact for this listing.<br>%s<br>%s",
                "confirmed email",
                "This email will not be visible if homepage is set or display is not checked, it is used only to identify the organizer's account.",
                "If none of the organizers has a confirmed account, add yourself and leave the organizer box unchecked.",
            )
        )
    # Don't try to create new_version using invalid input
    if errmsgs:
        return show_input_errors(errmsgs)
    else: # to make it obvious that these two statements should be together
        new_version = WebSeminar(shortname, data=data, organizer_data=organizer_data)

    # Warnings
    sanity_check_times(new_version.start_time, new_version.end_time)
    if not data["topics"]:
        flash_warning("This series has no topics selected; don't forget to set the topics for each new talk individually.")
    if seminar.new or new_version != seminar:
        new_version.save()
        edittype = "created" if new else "edited"
        flash("Series %s successfully!" % edittype)
    elif seminar.organizer_data == new_version.organizer_data:
        flash("No changes made to series.")
    if seminar.new or seminar.organizer_data != new_version.organizer_data:
        new_version.save_organizers()
        if not seminar.new:
            flash("Series organizers updated!")
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
    errmsgs = []
    for col in db.institutions.search_cols:
        if col in data:
            continue
        typ = db.institutions.col_type[col]
        try:
            val = raw_data.get(col, "")
            data[col] = None  # make sure col is present even if process_user_input fails
            data[col] = process_user_input(val, col, typ, tz)
            if col == "admin":
                userdata = userdb.lookup(data[col])
                if userdata is None:
                    if not data[col]:
                        errmsgs.append("You must specify the email address of the maintainer.")
                        continue
                    else:
                        errmsgs.append(format_errmsg("User %s does not have an account on this site", data[col]))
                        continue
                elif not userdata["creator"]:
                    errmsgs.append(format_errmsg("User %s has not been endorsed", data[col]))
                    continue
                if not userdata["homepage"]:
                    if current_user.email == userdata["email"]:
                        flash(
                            format_warning(
                                "Your email address will become public if you do not set your homepage in your user profile."
                            )
                        )
                    else:
                        flash(
                            format_warning(
                                "The email address %s of maintainer %s will be publicily visible.<br>%s",
                                userdata["email"],
                                userdata["name"],
                                "The homepage on the maintainer's user account should be set prevent this.",
                            ),
                            "error",
                        )
        except Exception as err:  # should only be ValueError's but let's be cautious
            errmsgs.append(format_input_errmsg(err, val, col))
    if not data["name"]:
        errmsgs.append("Institution name cannot be blank.")
    if not errmsgs and not data["homepage"]:
        errmsgs.append("Institution homepage cannot be blank.")
    # Don't try to create new_version using invalid input
    if errmsgs:
        return show_input_errors(errmsgs)
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
    return redirect(url_for(".edit_talk", seminar_id=seminar_id, seminar_ctr=seminar_ctr, token=token), 302,)


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
        tz = talk.seminar.tz
        date = process_user_input(data["date"], "date", "date", tz)
        try:
            # TODO: clean this up
            start_time = process_user_input(data.get("start_time"), "start_time", "time", tz)
            end_time = process_user_input(data.get("end_time"), "end_time", "time", tz)
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
    resp, talk = can_edit_talk(raw_data.get("seminar_id", ""), raw_data.get("seminar_ctr", ""), token)
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
        typ = db.talks.col_type[col]
        try:
            val = raw_data.get(col, "")
            data[col] = None  # make sure col is present even if process_user_input fails
            data[col] = process_user_input(val, col, typ, tz)
            if col == "access" and data[col] not in ["open", "users", "endorsed"]:
                errmsgs.append(format_errmsg("Access type %s invalid", data[col]))
        except Exception as err:  # should only be ValueError's but let's be cautious
            errmsgs.append(format_input_errmsg(err, val, col))
    if not data["speaker"]:
        errmsgs.append("Speaker name cannot be blank -- use TBA if speaker not chosen.")
    if data["start_time"] is None or data["end_time"] is None:
        errmsgs.append("Talks must have both a start and end time.")
    data["topics"] = clean_topics(data.get("topics"))
    data["language"] = clean_language(data.get("language"))
    data["subjects"] = clean_subjects(data.get("subjects"))
    if not data["subjects"]:
        errmsgs.append("Please select at least one subject")

    # Don't try to create new_version using invalid input
    if errmsgs:
        return show_input_errors(errmsgs)
    else: # to make it obvious that these two statements should be together
        new_version = WebTalk(talk.seminar_id, data["seminar_ctr"], data=data)

    # Warnings
    sanity_check_times(new_version.start_time, new_version.end_time)
    if "zoom" in data["video_link"] and not "rec" in data["video_link"]:
        flash_warning("Recorded video link should not be used for Zoom meeting links; be sure to use Livestream link for meeting links.")
    if not data["topics"]:
        flash_warning("This talk has no topics, and thus will only be visible to users when they disable their topics filter.")
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
                return process_user_input(date, "date", "date", tz)
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
            {"seminar_id": shortname, "start_time": {"$exists": True, "$gte": midnight_today},}, sort=["start_time"],
        )
        last_talk = talks_lucky(
            {"seminar_id": shortname, "start_time": {"$exists": True, "$lt": midnight_today},},
            sort=[("start_time", -1)],
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
                schedule_len = int((end - begin) / (frequency * day)) + 1
            else:
                end = begin + 6 * day
                schedule_len = 7
        else:
            end = begin + (SCHEDULE_LEN - 1) * frequency * day
            schedule_len = SCHEDULE_LEN
    else:
        schedule_len = abs(int((end - begin) / (frequency * day))) + 1
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
        sort = [("start_time", -1)]
    else:
        query = {"$gte": midnight_begin, "$lt": midnight_end + day}
        sort = ["start_time"]
    schedule_days = [begin + i * frequency * day for i in range(schedule_len)]
    scheduled_talks = list(talks_search({"seminar_id": shortname, "start_time": query}, sort=sort))
    by_date = defaultdict(list)
    for T in scheduled_talks:
        by_date[adapt_datetime(T.start_time, tz).date()].append(T)
    all_dates = sorted(set(schedule_days + list(by_date)), reverse=(end < begin))
    # Fill in by_date with Nones up to the per_day value
    per_day = seminar.per_day if seminar.per_day else 1
    for date in all_dates:
        by_date[date].extend([None] * (per_day - len(by_date[date])))
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
    return seminar, all_dates, by_date, len(all_dates) * per_day


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
    if not seminar.topics:
        flash_warning("This series has no topics selected; don't forget to set the topics for each new talk individually.")
    seminar, all_dates, by_date, slots = make_date_data(seminar, data)
    title = "Edit %s schedule" % ("conference" if seminar.is_conference else "seminar")
    return render_template(
        "edit_seminar_schedule.html",
        seminar=seminar,
        all_dates=all_dates,
        by_date=by_date,
        weekdays=weekdays,
        slots=slots,
        raw_data=data,
        title=title,
        section="Manage",
        subsection="schedule",
    )


required_cols = ["date", "time", "speaker"]
optional_cols = ["speaker_affiliation", "speaker_email", "title", "hidden"]


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
    slots = int(raw_data["slots"])
    curmax = talks_max("seminar_ctr", {"seminar_id": shortname})
    if curmax is None:
        curmax = 0
    ctr = curmax + 1
    updated = 0
    warned = False
    errmsgs = []
    tz = seminar.tz
    for i in list(range(slots)):
        seminar_ctr = raw_data.get("seminar_ctr%s" % i)
        speaker = process_user_input(raw_data.get("speaker%s" % i, ""), "speaker", "text", tz)
        if not speaker:
            if not warned and any(raw_data.get("%s%s" % (col, i), "").strip() for col in optional_cols):
                warned = True
                flash_warning("Talks are only saved if you specify a speaker")
            elif (
                not warned
                and seminar_ctr
                and not any(raw_data.get("%s%s" % (col, i), "").strip() for col in optional_cols)
            ):
                warned = True
                flash_warning("To delete an existing talk, click Details and then click delete on the Edit talk page")
            continue
        date = raw_data.get("date%s" % i).strip()
        if date:
            try:
                date = process_user_input(date, "date", "date", tz)
            except Exception as err:  # should only be ValueError's but let's be cautious
                errmsgs.append(format_input_errmsg(err, date, "date"))
        else:
            errmsgs.append(format_errmsg("You must specify a date for the talk by %s", speaker))
        time_input = raw_data.get("time%s" % i, "").strip()
        start_time = end_time = None
        if time_input:
            try:
                time_split = time_input.split("-")
                if len(time_split) < 2:
                    raise ValueError("Invalid time range.")
                elif len(time_split) > 2:
                    raise ValueError("Time range contains more than one hyphen, expected hh:mm-hh:mm.")
                if not time_split[0].strip() or not time_split[1].strip():
                    raise ValueError("Invalid time range.")
                # TODO: clean this up
                start_time = process_user_input(time_split[0], "start_time", "time", tz)
                end_time = process_user_input(time_split[1], "end_time", "time", tz)
            except Exception as err:
                errmsgs.append(format_input_errmsg(err, time_input, "time"))
        if any(X is None for X in [start_time, end_time]):
            errmsgs.append(format_errmsg("You must specify a start and end time for the talk by speaker %s", speaker))
        else:
            start_time = start_time.time()
            end_time = end_time.time()

        # we need to flag date and time errors before we go any further
        if errmsgs:
            return show_input_errors(errmsgs)

        if seminar_ctr:
            # existing talk
            seminar_ctr = int(seminar_ctr)
            talk = WebTalk(shortname, seminar_ctr, seminar=seminar)
        else:
            # new talk
            talk = WebTalk(shortname, seminar=seminar, editing=True)
        data = dict(talk.__dict__)
        data["speaker"] = speaker
        data["start_time"] = localize_time(datetime.datetime.combine(date, start_time), seminar.tz)
        data["end_time"] = localize_time(datetime.datetime.combine(date, end_time), seminar.tz)

        # if end_time < start_time push it to the next day
        if end_time < start_time:
            data["end_time"] += timedelta(days=int(1))
        assert data["end_time"] >= data["start_time"]

        if data["start_time"] + timedelta(hours=int(8)) < data["end_time"]:
            flash_warning(
                "Talk for speaker %s is longer than 8 hours; if this was not intended, please check (24-hour) times.",
                data["speaker"],
            )

        for col in optional_cols:
            typ = db.talks.col_type[col]
            try:
                val = raw_data.get("%s%s" % (col, i), "")
                data[col] = None  # make sure col is present even if process_user_input fails
                data[col] = process_user_input(val, col, typ, tz)
            except Exception as err:
                errmsgs.append(format_input_errmsg(err, val, col))

        # Don't try to create new_version using invalid input
        if errmsgs:
            return show_input_errors(errmsgs)
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
        return redirect(url_for(".edit_talk", seminar_id=shortname, seminar_ctr=int(raw_data.get("detailctr")),), 302,)
    else:
        flash("%s talks updated, %s talks created" % (updated, ctr - curmax - 1))
        if warned:
            return redirect(url_for(".edit_seminar_schedule", **raw_data), 302)
        else:
            return redirect(
                url_for(
                    ".edit_seminar_schedule",
                    shortname=shortname,
                    begin=raw_data.get("begin"),
                    end=raw_data.get("end"),
                    frequency=raw_data.get("frequency"),
                    weekday=raw_data.get("weekday"),
                ),
                302,
            )
