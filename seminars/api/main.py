
from flask import jsonify, request
from seminars import db
from seminars.app import app
from seminars.api import api_page
from seminars.seminar import WebSeminar, seminars_lookup
from seminars.users.pwdmanager import SeminarsUser
from seminars.utils import allowed_shortname, sanity_check_times
from seminars.create.main import process_save_seminar
from functools import wraps

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

@api_page.route("/<int:version>/save/seminar/", methods=["POST"])
@api_auth_required
def save_seminar(version, user):
    if version != 1:
        raise APIError({"code": "invalid_version",
                        "description": "Unknown API version: %s" % version}, 400)
    raw_data = request.get_json()
    shortname = raw_data.get("shortname")
    if shortname is None:
        raise APIError({"code": "unspecified_shortname",
                        "description": "You must specify shortname when saving a series"}, 400)
    seminar = seminars_lookup(shortname, include_deleted=True)
    if seminar is None:
        # Creating new seminar
        if not allowed_shortname(shortname) or len(shortname) < 3 or len(shortname) > 32:
            raise APIError({"code": "invalid_shortname",
                           "description": "The identifier must be 3 to 32 characters in length and can include only letters, numbers, hyphens and underscores."}, 400)
        update_organizers = True
        seminar = WebSeminar(shortname, data=None, editing=True)
    else:
        # Make sure user has permission to edit
        if not seminar.user_can_edit(user):
            raise APIError({"code":"unauthorized_user",
                            "description": "You do not have permission to edit %s." % shortname}, 401)
        if seminar.deleted:
            raise APIError({"code": "norevive",
                            "description": "You cannot revive a seminar through the API"})
        update_organizers = False
    warnings = []
    def warn(msg, *args):
        warnings.append(msg % args)
    def format_error(msg, *args):
        return msg % args
    def format_input_error(err, inp, col):
        return 'Unable to process input "%s" for property %s: %s' % (inp, col, err)
    data, organizer_data, errmsgs = process_save_seminar(seminar, raw_data, warn, format_error, format_input_error, update_organizers)
    if errmsgs:
        raise APIError({"code": "processing_error",
                        "description": "Error in processing input",
                        "errors": errmsgs}, 400)
    new_version = WebSeminar(shortname, data=data, organizer_data=organizer_data)
    sanity_check_times(new_version.start_time, new_version.end_time, warn)
    if seminar.new or new_version != seminar:
        new_version.save(user)
    else:
        raise APIError({"code": "no_changes",
                        "description": "No changes detected"}, 400)
    if seminar.new:
        new_version.save_organizers()
    edittype = "created" if seminar.new else "edited"
    if warnings:
        response = jsonify({"code": "warning",
                            "description": "seminar successfully %s, but..." % edittype,
                            "warnings": warnings})
    else:
        response = jsonify({"code": "success",
                            "description": "seminar successfully %s" % edittype})
    return response

@api_page.route("/<int:version>/save/talk/", methods=["POST"])
@api_auth_required
def save_talk(version, user):
    pass
