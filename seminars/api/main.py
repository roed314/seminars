
from flask import jsonify, request
from seminars import db
from seminars.app import app
from seminars.api import api_page
from seminars.seminar import WebSeminar, seminars_lookup
from seminars.talk import WebTalk, talks_lookup
from seminars.users.pwdmanager import SeminarsUser
from seminars.utils import allowed_shortname, sanity_check_times, short_weekdays
from seminars.create.main import process_save_seminar, process_save_talk, MAX_SLOTS, MAX_ORGANIZERS
from functools import wraps

def format_error(msg, *args):
    return msg % args

def format_input_error(err, inp, col):
    return 'Unable to process input "%s" for property %s: %s' % (inp, col, err)

class APIError(Exception):
    def __init__(self, error, status):
        self.error = error
        self.status = status

@app.errorhandler(APIError)
def handle_api_error(err):
    response = jsonify(err.error)
    response.status_code = err.status
    return response

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

@api_page.route("/test")
@api_auth_required
def test_api(user):
    response = jsonify({"code": "success"})
    return response

@api_page.route("/<int:version>/save/series/", methods=["POST"])
@api_auth_required
def save_series(version, user):
    if version != 0:
        raise APIError({"code": "invalid_version",
                        "description": "Unknown API version: %s" % version}, 400)
    try:
        raw_data = request.get_json()
    except Exception:
        raw_data = None
    if not isinstance(raw_data, dict):
        raise APIError({"code": "invalid_json",
                        "description": "request must contain a json dictionary"}, 400)
    # Temporary measure while we rename shortname
    series_id = raw_data.pop("series_id", None)
    raw_data["shortname"] = series_id
    if series_id is None:
        raise APIError({"code": "unspecified_series_id",
                        "description": "You must specify series_id when saving a series"}, 400)
    series = seminars_lookup(series_id, include_deleted=True)
    if series is None:
        # Creating new series
        if not allowed_shortname(series_id) or len(series_id) < 3 or len(series_id) > 32:
            raise APIError({"code": "invalid_series_id",
                           "description": "The identifier must be 3 to 32 characters in length and can include only letters, numbers, hyphens and underscores."}, 400)
        if "organizers" not in raw_data:
            raise APIError({"code": "organizers_required",
                            "description": "You must specify organizers when creating new series"}, 400)
        update_organizers = True
        series = WebSeminar(series_id, data=None, editing=True, user=user)
    else:
        # Make sure user has permission to edit
        if not series.user_can_edit(user):
            raise APIError({"code":"unauthorized_user",
                            "description": "You do not have permission to edit %s." % series_id}, 401)
        if series.deleted:
            raise APIError({"code": "norevive",
                            "description": "You cannot revive a series through the API"}, 400)
        if "organizers" in raw_data:
            raise APIError({"code": "organizers_prohibited",
                            "description": "You may not specify organizers when editing series"}, 400)
        update_organizers = False
    # Check that there aren't extraneous keys (which might be misspelled)
    extra_keys = [key for key in raw_data if key not in db.seminars.search_cols + ["slots", "organizers"]]
    if extra_keys:
        raise APIError({"code": "extra_keys",
                        "description": "Unrecognized keys",
                        "errors": extra_keys}, 400)
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
                        "errors": ["slots must be a list of strings of length at most %s" % MAX_SLOTS]}, 400)
    for i, slot in enumerate(slots):
        day, time = slot.split(None, 1)
        try:
            day = short_weekdays.index(day)
        except ValueError:
            raise APIError({"code": "processing_error",
                            "description": "Error in processing slots",
                            "errors": ["slots must start with a three letter day-of-week"]}, 400)
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
                raw_data["org_%s%s" % (col, i)] = OD.get(col, "")

    warnings = []
    def warn(msg, *args):
        warnings.append(msg % args)
    data, organizer_data, errmsgs = process_save_seminar(series, raw_data, warn, format_error, format_input_error, update_organizers)
    if errmsgs:
        raise APIError({"code": "processing_error",
                        "description": "Error in processing input",
                        "errors": errmsgs}, 400)
    else:
        new_version = WebSeminar(series_id, data=data, organizer_data=organizer_data)
    if series.new or new_version != series:
        # Series saved by the API are not displayed until user approves
        new_version.display = False
        new_version.save(user)
    else:
        raise APIError({"code": "no_changes",
                        "description": "No changes detected"}, 400)
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
def save_talk(version, user):
    if version != 0:
        raise APIError({"code": "invalid_version",
                        "description": "Unknown API version: %s" % version}, 400)
    raw_data = request.get_json()
    # Temporary measure while we rename seminar_id
    series_id = raw_data.pop("series_id", None)
    raw_data["seminar_id"] = series_id
    if series_id is None:
        raise APIError({"code": "unspecified_series_id",
                        "description": "You must specify series_id when saving a talk"}, 400)
    series = seminars_lookup(series_id)
    if series is None:
        raise APIError({"code": "no_series",
                        "description": "The series %s does not exist (or is deleted)" % series_id}, 400)
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
                            "description": "The talk %s/%s does not exist (or is deleted)" % (series_id, series_ctr)}, 400)
    warnings = []
    def warn(msg, *args):
        warnings.append(msg % args)
    data, errmsgs = process_save_talk(talk, raw_data, warn, format_error, format_input_error)
    if errmsgs:
        raise APIError({"code": "processing_error",
                        "description": "Error in processing input",
                        "errors": errmsgs}, 400)
    else:
        new_version = WebTalk(talk.seminar_id, data=data)
    sanity_check_times(new_version.start_time, new_version.end_time)
    if talk.new or new_version != talk:
        # Talks saved by the API are not displayed until user approves
        new_version.display = False
        new_version.save(user)
    else:
        raise APIError({"code": "no_changes",
                        "description": "No changes detected"}, 400)
    edittype = "created" if talk.new else "edited"
    if warnings:
        response = jsonify({"code": "warning",
                            "description": "series successfully %s, but..." % edittype,
                            "warnings": warnings})
    else:
        response = jsonify({"code": "success",
                            "description": "series successfully %s" % edittype})
    return response
