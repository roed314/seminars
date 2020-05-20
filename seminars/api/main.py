
import pytz
from flask import jsonify, request, render_template, redirect, url_for, make_response, current_app
from flask_login import current_user
from seminars import db
from seminars.app import app
from seminars.api import api_page
from seminars.seminar import WebSeminar, seminars_lookup, seminars_search
from seminars.talk import WebTalk, talks_lookup, talks_search
from seminars.users.pwdmanager import SeminarsUser, ilike_query
from seminars.users.main import creator_required
from seminars.utils import allowed_shortname, sanity_check_times, short_weekdays, process_user_input, adapt_datetime, APIError, MAX_SLOTS, MAX_ORGANIZERS
from seminars.topic import topic_dag
from seminars.create.main import process_save_seminar, process_save_talk
from functools import wraps

import inspect
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter

def format_error(msg, *args):
    return msg % args

def format_input_error(err, inp, col):
    return 'Unable to process input "%s" for property %s: %s' % (inp, col, err)

def version_error(version):
    return APIError({"code": "invalid_version",
                     "description": "Unknown API version: %s" % version})

def get_request_json():
    try:
        return request.get_json()
    except Exception as err:
        raise APIError({"code": "json_parse_error",
                        "description": "could not parse json",
                        "error": str(err)})

def _get_col(col, raw_data, activity):
    val = raw_data.get(col)
    if val is None:
        raise APIError({"code": "unspecified_%s" % col,
                        "description": "You must specify %s when %s" % (col, activity)})
    return val

@app.errorhandler(APIError)
def handle_api_error(err):
    response = jsonify(err.error)
    response.status_code = err.status
    return response

@api_page.route("/pyhighlight.css")
def pyhighcss():
    response = make_response(HtmlFormatter().get_style_defs('.highlight'))
    response.headers["Content-type"] = "text/css"
    if current_app.debug:
        response.headers["Cache-Control"] = "no-cache, no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=600"
    return response

@api_page.route("/help")
def help():
    code_examples = {}
    from . import example
    from types import FunctionType
    code_examples = {name: highlight(inspect.getsource(func), PythonLexer(), HtmlFormatter())
                     for (name, func) in example.__dict__.items()
                     if isinstance(func, FunctionType)}
    print(code_examples)
    return render_template(
        "api_help.html",
        title="API",
        section="Info",
        code_examples=code_examples,
    )

# Unlike most routes in this module, this one requires a live user to be logged in
@api_page.route("/review/", methods=["POST"])
@creator_required
def review_api():
    decision = request.form.get("submit")
    series = set()
    for series_id in db.seminar_organizers.search({"email": ilike_query(current_user.email)}, "seminar_id"):
        series.add(series_id)
    for series_id in seminars_search({"owner": ilike_query(current_user.email)}, "shortname", prequery={}):
        series.add(series_id)
    series = list(series)
    if decision == "approve":
        db.seminars.update({"shortname": {"$in": series}, "by_api": True, "display": False}, {"display": True}, restat=False)
        db.talks.update({"seminar_id": {"$in": series}, "by_api": True, "display": False}, {"display": True}, restat=False)
    else:
        db.seminars.delete({"shortname": {"$in": series}, "by_api": True, "display": False}, restat=False)
        db.talks.delete({"seminar_id": {"$in": series}, "by_api": True, "display": False}, restat=False)
        # Need to check whether new seminars might have been completely deleted
        for series_id in series:
            if db.seminars.lookup(series_id) is None:
                db.seminar_organizers.delete({"seminar_id": series_id})

    return redirect(url_for("create.index"))

# This static route allows access to the topic graph
@api_page.route("/<int:version>/topics")
def topics(version=0):
    if version != 0:
        raise version_error(version)
    topics = {rec["topic_id"]: {"name": rec["name"], "children": rec["children"]}
              for rec in db.new_topics.search()}
    return jsonify(topics)

# This static route allows access to a list of all institutions
@api_page.route("/<int:version>/institutions")
def institutions(version=0):
    if version != 0:
        raise version_error(version)
    institutions = {rec["shortname"]: {key: rec[key] for key in ["name", "city", "timezone", "type", "homepage"]}
                    for rec in db.institutions.search()}
    return jsonify(institutions)

@api_page.route("/<int:version>/lookup/series", methods=["GET", "POST"])
def lookup_series(version=0):
    if version != 0:
        raise version_error(version)
    if request.method == "POST":
        raw_data = get_request_json()
    else:
        raw_data = dict(request.args)
    series_id = _get_col("series_id", raw_data, "looking up a series")
    result = seminars_lookup(series_id, objects=False, sanitized=True)
    tz = pytz.timezone(raw_data.get("timezone", result.get("timezone", "UTC")))
    # TODO: adapt the times, support daterange, sort
    talks = talks_search({"seminar_id": series_id}, sanitized=True, objects=False)
    return jsonify({"code": "success",
                    "properties": result,
                    "talks": talks})

@api_page.route("/<int:version>/lookup/series", methods=["GET", "POST"])
def lookup_talk(version=0):
    if version != 0:
        raise version_error(version)
    if request.method == "POST":
        raw_data = get_request_json()
    else:
        raw_data = dict(request.args)
    series_id = get_series_id("series_id", raw_data, "looking up a talk")
    series_ctr = get_series_ctr("series_ctr", raw_data, "looking up a talk")
    result = talks_lookup(series_id, series_ctr, objects=False, sanitized=True)
    tz = pytz.timezone(raw_data.get("timezone", result.get("timezone", "UTC")))
    # TODO: adapt the times, support daterange
    return jsonify({"code": "success",
                    "properties": result})

@api_page.route("/<int:version>/search/series", methods=["GET", "POST"])
def search_series(version=0):
    if version != 0:
        raise version_error(version)
    if request.method == "POST":
        raw_data = get_request_json()
        query = raw_data.pop("query", {})
        tz = raw_data.pop("timezone", "UTC")
    else:
        query = dict(request.args)
        tz = current_user.tz # Is this the right choice?
        for col, val in query.items():
            if col in db.seminars.col_type:
                query[col] = process_user_input(val, col, db.seminars.col_type[col], tz)
            else:
                raise APIError({"code": "unknown_column",
                                "col": col,
                                "description": "%s not a column of seminars" % col})
        raw_data = {}
    query["visibility"] = 2
    # TODO: encode the times....
    try:
        results = seminars_search(query, objects=False, sanitized=True, **raw_data)
    except Exception as err:
        raise APIError({"code": "search_error",
                        "description": "error in executing search",
                        "error": str(err)})
    return jsonify({"code": "success",
                    "results": results})

@api_page.route("/<int:version>/search/talks", methods=["GET", "POST"])
def search_talks(version=0):
    if version != 0:
        raise version_error(version)
    if request.method == "POST":
        try:
            raw_data = request.get_json()
        except Exception:
            raw_data = None
        query = raw_data.pop("query", {})
        projection = raw_data.pop("projection", 1)
    else:
        query = dict(request.args)
        projection = 1
        raw_data = {}
    query["hidden"] = False
    visible_series = set(seminars_search({"visibility": 2}, "shortname"))
    # TODO: Need to check visibility on the seminar
    try:
        results = talks_search(query, projection, objects=False, **raw_data)
    except Exception as err:
        raise APIError({"code": "search_error",
                        "description": "error in executing search",
                        "error": str(err)})
    results = [rec for rec in results if rec["seminar_id"] in visible_series]
    return jsonify({"code": "success",
                    "results": results})

def api_auth_required(fn):
    # Note that this wrapper will pass the user as a keyword argument to the wrapped function
    @wraps(fn)
    def inner(*args, **kwds):
        auth = request.headers.get("authorization", None)
        if auth is None:
            raise APIError({"code": "missing_authorization",
                            "description": "No authorization header"}, 401)
        pieces = auth.split()
        if len(pieces) != 2:
            raise APIError({"code": "invalid_header",
                            "description": "Authorization header must have length 2"}, 401)
        email, token = pieces
        user = SeminarsUser(email=email)
        if user.id is None:
            raise APIError({"code": "missing_user",
                            "description": "User %s not found" % email}, 401)
        if token == user.api_token:
            kwds["user"] = user
            return fn(*args, **kwds)
        else:
            raise APIError({"code": "invalid_token",
                            "description": "Token not valid"}, 401)
    return inner

@api_page.route("/<int:version>/test")
@api_auth_required
def test_api(version, user):
    response = jsonify({"code": "success"})
    return response

@api_page.route("/<int:version>/save/series/", methods=["POST"])
@api_auth_required
def save_series(version=0, user=None):
    if version != 0:
        raise version_error(version)
    try:
        raw_data = request.get_json()
    except Exception:
        raw_data = None
    if not isinstance(raw_data, dict):
        raise APIError({"code": "invalid_json",
                        "description": "request must contain a json dictionary"})
    # Temporary measure while we rename shortname
    series_id = raw_data.pop("series_id", None)
    raw_data["shortname"] = series_id
    if series_id is None:
        raise APIError({"code": "unspecified_series_id",
                        "description": "You must specify series_id when saving a series"})
    series = seminars_lookup(series_id, include_deleted=True)
    if series is None:
        # Creating new series
        if not allowed_shortname(series_id) or len(series_id) < 3 or len(series_id) > 32:
            raise APIError({"code": "invalid_series_id",
                           "description": "The identifier must be 3 to 32 characters in length and can include only letters, numbers, hyphens and underscores."})
        if "organizers" not in raw_data:
            raise APIError({"code": "organizers_required",
                            "description": "You must specify organizers when creating new series"})
        update_organizers = True
        series = WebSeminar(series_id, data=None, editing=True, user=user)
    else:
        # Make sure user has permission to edit
        if not series.user_can_edit(user):
            raise APIError({"code":"unauthorized_user",
                            "description": "You do not have permission to edit %s." % series_id}, 401)
        if series.deleted:
            raise APIError({"code": "norevive",
                            "description": "You cannot revive a series through the API"})
        if "organizers" in raw_data:
            raise APIError({"code": "organizers_prohibited",
                            "description": "You may not specify organizers when editing series"})
        update_organizers = False
    # Check that there aren't extraneous keys (which might be misspelled)
    extra_keys = [key for key in raw_data if key not in db.seminars.search_cols + ["slots", "organizers"]]
    if extra_keys:
        raise APIError({"code": "extra_keys",
                        "description": "Unrecognized keys",
                        "errors": extra_keys})
    # Time slots/weekdays and organizers are handled differently by the processing code
    # We want to allow them to be unspecified (in which case we fall back on the current value)
    # and for an API call it's also more convenient to specify them using a list
    if "slots" in raw_data:
        slots = raw_data["slots"]
    else:
        slots = [short_weekdays[day] + " " + slot for (day, slot) in zip(series.weekdays, series.time_slots)]
    if not isinstance(slots, list) or len(slots) > MAX_SLOTS or not all(isinstance(slot, str) for slot in slots):
        raise APIError({"code": "processing_error",
                        "description": "Error in processing slots",
                        "errors": ["slots must be a list of strings of length at most %s" % MAX_SLOTS]})
    for i, slot in enumerate(slots):
        day, time = slot.split(None, 1)
        try:
            day = short_weekdays.index(day)
        except ValueError:
            raise APIError({"code": "processing_error",
                            "description": "Error in processing slots",
                            "errors": ["slots must start with a three letter day-of-week"]})
        raw_data["weekday%s"%i] = str(day)
        raw_data["time_slot%s"%i] = time
    for i in range(len(slots), MAX_SLOTS):
        raw_data["weekday%s"%i] = raw_data["time_slot%s"%i] = ""

    if update_organizers:
        # We require specifying the organizers of a new seminar and don't allow updates,
        # so we don't need to get anything from the seminar object
        organizers = raw_data.get("organizers", [])
        if not (isinstance(organizers, list) and
                len(organizers) <= MAX_ORGANIZERS and
                all(isinstance(OD, dict) and
                    all(key in db.seminar_organizers.search_cols for key in OD)
                    for OD in organizers)):
            raise APIError({"code": "processing_error",
                            "description": "Error in processing organizers",
                            "errors": ["organizers must be a list of dictionaries (max length %s) with keys %s" % (MAX_ORGANIZERS, ", ".join(db.seminar_organizers.search_cols))]})
        for i, OD in enumerate(organizers):
            for col in db.seminar_organizers.search_cols:
                default = True if col == "display" else ""
                raw_data["org_%s%s" % (col, i)] = OD.get(col, default)
            # We store curator in the database but ask for organizer from the API
            raw_data["org_curator%s" % i] = not OD.get("organizer", True)

    warnings = []
    def warn(msg, *args):
        warnings.append(msg % args)
    data, organizers, errmsgs = process_save_seminar(series, raw_data, warn, format_error, format_input_error, update_organizers)
    if errmsgs:
        raise APIError({"code": "processing_error",
                        "description": "Error in processing input",
                        "errors": errmsgs})
    else:
        new_version = WebSeminar(series_id, data=data, organizers=organizers, user=user)
    if series.new or new_version != series:
        # Series saved by the API are not displayed until user approves
        new_version.display = False
        new_version.by_api = True
        new_version.save(user)
    else:
        raise APIError({"code": "no_changes",
                        "description": "No changes detected"})
    if series.new:
        new_version.save_organizers()
    edittype = "created" if series.new else "edited"
    if warnings:
        response = jsonify({"code": "warning",
                            "description": "series successfully %s, but..." % edittype,
                            "warnings": warnings})
    else:
        response = jsonify({"code": "success",
                            "description": "series successfully %s" % edittype})
    return response

@api_page.route("/<int:version>/save/talk/", methods=["POST"])
@api_auth_required
def save_talk(version=0, user=None):
    if version != 0:
        raise APIError({"code": "invalid_version",
                        "description": "Unknown API version: %s" % version})
    raw_data = request.get_json()
    # Temporary measure while we rename seminar_id
    series_id = raw_data.pop("series_id", None)
    raw_data["seminar_id"] = series_id
    if series_id is None:
        raise APIError({"code": "unspecified_series_id",
                        "description": "You must specify series_id when saving a talk"})
    series = seminars_lookup(series_id)
    if series is None:
        raise APIError({"code": "no_series",
                        "description": "The series %s does not exist (or is deleted)" % series_id})
    else:
        # Make sure user has permission to edit
        if not series.user_can_edit(user):
            raise APIError({"code": "unauthorized_user",
                            "description": "You do not have permission to edit %s." % series_id}, 401)
    # Temporary measure while we rename seminar_ctr
    series_ctr = raw_data.pop("series_ctr", None)
    raw_data["seminar_ctr"] = series_ctr
    if series_ctr is None:
        # Creating new talk
        talk = WebTalk(series_id, seminar=series, editing=True)
    else:
        talk = talks_lookup(series_id, series_ctr)
        if talk is None:
            raise APIError({"code": "no_talk",
                            "description": "The talk %s/%s does not exist (or is deleted)" % (series_id, series_ctr)})
    warnings = []
    def warn(msg, *args):
        warnings.append(msg % args)
    data, errmsgs = process_save_talk(talk, raw_data, warn, format_error, format_input_error)
    if errmsgs:
        raise APIError({"code": "processing_error",
                        "description": "Error in processing input",
                        "errors": errmsgs})
    else:
        new_version = WebTalk(talk.seminar_id, data=data)
    sanity_check_times(new_version.start_time, new_version.end_time)
    if talk.new or new_version != talk:
        # Talks saved by the API are not displayed until user approves
        new_version.display = False
        new_version.by_api = True
        new_version.save(user)
    else:
        raise APIError({"code": "no_changes",
                        "description": "No changes detected"})
    edittype = "created" if talk.new else "edited"
    if warnings:
        response = jsonify({"code": "warning",
                            "description": "series successfully %s, but..." % edittype,
                            "warnings": warnings})
    else:
        response = jsonify({"code": "success",
                            "description": "series successfully %s" % edittype})
    return response
