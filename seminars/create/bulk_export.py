# -*- coding: utf-8 -*-
"""Bulk ICS export for organizers (issue #910).

Organizers can download all talks for one series they manage, or for all
series they manage in a single action.

Route: GET /manage/export/ics?series=<shortname>[,..]&past&future&datarange=...&offset=..&limit=..&format=ics|zip

Authz (main risk): the requested series must be a subset of the series the
user manages (organizer row email ilike, or owner email ilike, same pattern
as create.main.index).  Talks are additionally filtered in Python by
``searchable() or user_can_edit()`` and by membership in the authorized id
set, so a stale organizer row or a crafted series id can never leak talks
from other series.
"""
import re
import zipfile
from datetime import datetime, timedelta
from io import BytesIO

from dateutil.parser import parse as parse_time
from flask import abort, request, send_file
from flask_login import current_user

from seminars import db
from seminars.create import create
from seminars.seminar import seminars_search
from seminars.talk import talks_search
from seminars.users.main import email_confirmed_required
from seminars.users.pwdmanager import ilike_query
from seminars.utils import allowed_shortname, flash_error, ics_file

MAX_EXPORT_TALKS = 900
MAX_EXPORT_BYTES = 800 * 1024
MAX_PAGE_LIMIT = 2000


def get_managed_series_ids(organizer_ids, owned_ids):
    """Union of organizer-row ids and owned ids, de-duplicated and sorted."""
    seen = set()
    for elt in list(organizer_ids or []) + list(owned_ids or []):
        if elt:
            seen.add(elt)
    return sorted(seen)


def parse_series_param(raw, managed_ids):
    """Resolve the ?series= param against the managed id set.

    Returns the authorized subset (deduped, in managed order for stability,
    or requested order filtered).  Raises PermissionError if any requested
    id is not managed (authz), ValueError on malformed input.
    """
    managed = list(managed_ids or [])
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return list(managed)
    if not isinstance(raw, str):
        raise ValueError("Invalid series parameter")
    if "\x00" in raw:
        raise ValueError("Invalid series parameter")
    wanted = [elt.strip() for elt in raw.split(",")]
    wanted = [elt for elt in wanted if elt]
    if not wanted:
        return list(managed)
    managed_set = set(managed)
    for elt in wanted:
        if not allowed_shortname(elt):
            raise ValueError("Invalid series identifier %r" % (elt,))
        if elt not in managed_set:
            raise PermissionError("Not authorized for series %r" % (elt,))
    # de-dupe preserving requested order
    seen = set()
    out = []
    for elt in wanted:
        if elt not in seen:
            seen.add(elt)
            out.append(elt)
    return out


def parse_pagination(args):
    """Parse ?offset=&limit=, returning (offset, limit-or-None).

    Raises ValueError on malformed input.
    """
    raw_offset = args.get("offset", "")
    raw_limit = args.get("limit", "")
    if raw_offset in (None, ""):
        offset = 0
    else:
        try:
            offset = int(raw_offset)
        except (TypeError, ValueError):
            raise ValueError("Invalid offset")
        if offset < 0:
            raise ValueError("Invalid offset")
    if raw_limit in (None, ""):
        limit = None
    else:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise ValueError("Invalid limit")
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise ValueError("Invalid limit")
    return offset, limit


def parse_daterange_to_query(daterange_str, tz):
    """Pure daterange parser mirroring homepage.parse_daterange.

    Returns (query_update, error).  query_update is {} or
    {"start_time": {...}}; error is None or a message string.
    """
    if daterange_str is None or not str(daterange_str).strip():
        return {}, None
    s = str(daterange_str)
    if "\x00" in s:
        return {}, "Invalid daterange input"
    if "-" not in s:
        s = s + "-" + s
    elif s.count("-") > 1:
        return {}, "Too many hyphens in date"
    start_s, end_s = s.split("-", 1)
    sub = {}
    if start_s.strip():
        try:
            start = tz.localize(parse_time(start_s))
            sub["$gte"] = start
        except Exception as exc:
            return {}, "Could not parse start date: %s" % (exc,)
    if end_s.strip():
        try:
            end = tz.localize(parse_time(end_s))
            end = end + timedelta(hours=23, minutes=59, seconds=59)
            sub["$lte"] = end
        except Exception as exc:
            return {}, "Could not parse end date: %s" % (exc,)
    if not sub:
        return {}, None
    return {"start_time": sub}, None


def build_talks_query(series_ids, past_only=False, future_only=False,
                      start_time_filter=None, now=None):
    """Build a talks_search query for the given authorized series ids."""
    if not series_ids:
        raise ValueError("No series selected")
    query = {
        "seminar_id": {"$in": list(series_ids)},
        "seminar_ctr": {"$gt": 0},
    }
    if start_time_filter:
        query["start_time"] = dict(start_time_filter)
        return query
    if past_only and future_only:
        return query
    if now is None:
        try:
            import pytz
            now = datetime.now(pytz.UTC)
        except Exception:
            now = datetime.utcnow()
    if past_only and not future_only:
        # past talks: started at or before now
        query["start_time"] = {"$lte": now}
    elif future_only and not past_only:
        query["end_time"] = {"$gte": now}
    return query


def is_talk_visible_to_organizer(talk, user, allowed_ids=None):
    """Authz gate for a single talk: series membership + visibility/edit."""
    sid = getattr(talk, "seminar_id", None)
    if allowed_ids is not None and sid not in set(allowed_ids):
        return False
    try:
        if talk.searchable():
            return True
    except Exception:
        pass
    try:
        return bool(talk.user_can_edit(user=user))
    except TypeError:
        # stub user_can_edit() without user kwarg
        return bool(talk.user_can_edit())
    except Exception:
        return False


def filter_authorized_talks(talks, user, allowed_ids=None):
    """Keep only talks the user may export (no cross-series leak)."""
    allowed = set(allowed_ids) if allowed_ids is not None else None
    out = []
    for talk in talks or []:
        if is_talk_visible_to_organizer(talk, user, allowed_ids=allowed):
            out.append(talk)
    return out


def needs_split(n_talks, n_bytes=None):
    """True when the export should be split (zip per-series or paginate)."""
    if n_talks is None:
        return False
    try:
        if int(n_talks) > MAX_EXPORT_TALKS:
            return True
    except (TypeError, ValueError):
        pass
    if n_bytes is not None:
        try:
            if int(n_bytes) > MAX_EXPORT_BYTES:
                return True
        except (TypeError, ValueError):
            pass
    return False


def paginate_talks(talks, offset=0, limit=None):
    """Slice a talk list; validates bounds.  Raises ValueError if bad."""
    if offset is None:
        offset = 0
    offset = int(offset)
    if offset < 0:
        raise ValueError("Invalid offset")
    seq = list(talks or [])
    if limit is None or limit == "":
        return seq[offset:]
    limit = int(limit)
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise ValueError("Invalid limit")
    return seq[offset:offset + limit]


def group_talks_by_series(talks):
    """Group talks by seminar_id for per-series zip export."""
    grouped = {}
    for talk in talks or []:
        sid = getattr(talk, "seminar_id", "")
        grouped.setdefault(sid, []).append(talk)
    return grouped


def export_filename(series_ids):
    """ICS filename for the export."""
    if series_ids is not None and len(series_ids) == 1:
        base = series_ids[0]
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", base) or "export"
        return "%s.ics" % base
    return "my-series.ics"


def _managed_ids_for_user(email):
    organizer_ids = []
    for rec in db.seminar_organizers.search({"email": ilike_query(email)}):
        sid = rec.get("seminar_id")
        if sid:
            organizer_ids.append(sid)
    try:
        owned_ids = list(seminars_search(
            {"owner": ilike_query(email)},
            "shortname",
            include_pending=True,
        ))
    except Exception:
        owned_ids = []
    # seminars_search with a column projection returns a list of values
    flat = []
    for elt in owned_ids:
        if isinstance(elt, dict):
            for val in elt.values():
                flat.append(val)
        else:
            flat.append(elt)
    return get_managed_series_ids(organizer_ids, flat)


@create.route("manage/export/ics", methods=["GET"])
@email_confirmed_required
def export_ics():
    email = current_user.email
    managed_ids = _managed_ids_for_user(email)
    if not managed_ids:
        return abort(404, "No series found for this account")
    try:
        requested = parse_series_param(request.args.get("series"), managed_ids)
    except PermissionError:
        return abort(403, "Not authorized for requested series")
    except ValueError:
        return abort(400, "Invalid series parameter")
    try:
        offset, limit = parse_pagination(request.args)
    except ValueError as exc:
        return abort(400, str(exc))

    # date window: ?daterange= (string, "past", "future") or ?past / ?future
    # flags, mirroring homepage.talks_search_api
    past_only = future_only = False
    start_time_filter = None
    daterange_raw = request.args.get("daterange")
    if daterange_raw is not None and str(daterange_raw).strip() not in ("",):
        val = str(daterange_raw).strip()
        if val == "past":
            past_only = True
        elif val == "future":
            future_only = True
        else:
            update, err = parse_daterange_to_query(val, current_user.tz)
            if err:
                flash_error("Could not parse daterange: %s", val)
                return abort(400, err)
            if "start_time" in update:
                start_time_filter = update["start_time"]
    elif "past" in request.args and "future" in request.args:
        pass  # no restriction
    elif "past" in request.args:
        past_only = True
    elif "future" in request.args:
        future_only = True

    try:
        import pytz
        now_dt = datetime.now(pytz.UTC)
    except Exception:
        now_dt = datetime.utcnow()
    try:
        query = build_talks_query(
            requested,
            past_only=past_only,
            future_only=future_only,
            start_time_filter=start_time_filter,
            now=now_dt,
        )
    except ValueError as exc:
        return abort(400, str(exc))

    try:
        seminar_dict = {
            s.shortname: s
            for s in seminars_search(
                {"shortname": {"$in": requested}},
                include_pending=True,
            )
        }
    except Exception:
        seminar_dict = {}
    try:
        talks = list(talks_search(query, seminar_dict=seminar_dict,
                                  sort=["seminar_id", "start_time"]))
    except Exception as exc:
        return abort(400, str(exc))
    allowed_set = set(requested)
    talks = [t for t in talks if getattr(t, "seminar_id", None) in allowed_set]
    talks = filter_authorized_talks(talks, current_user, allowed_ids=allowed_set)

    fmt = (request.args.get("format") or "ics").strip().lower()
    if fmt not in ("ics", "zip"):
        return abort(400, "Invalid format (expected ics or zip)")

    if fmt == "zip" or (len(requested) > 1 and needs_split(len(talks)) and limit is None):
        # per-series zip split for large multi-series exports (#910)
        from icalendar import Calendar
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            grouped = group_talks_by_series(talks)
            if not grouped:
                grouped = {sid: [] for sid in requested}
            for sid in sorted(grouped):
                cal = Calendar()
                cal.add("VERSION", "2.0")
                cal.add("PRODID", "researchseminars")
                for talk in grouped[sid]:
                    try:
                        cal.add_component(talk.event(user=current_user))
                    except Exception:
                        continue
                data = cal.to_ical()
                if needs_split(len(grouped[sid]), len(data)) and len(data) > MAX_EXPORT_BYTES:
                    # still too big single-series: paginate hint
                    pass
                zf.writestr("%s.ics" % (sid,), data)
        buf.seek(0)
        return send_file(buf, download_name="my-series.zip",
                         mimetype="application/zip", as_attachment=True)

    # single-file ICS, honoring offset/limit pagination
    try:
        page = paginate_talks(talks, offset=offset, limit=limit)
    except ValueError as exc:
        return abort(400, str(exc))
    if needs_split(len(talks)) and limit is None and len(requested) == 1:
        flash_error(
            "Export has %s talks; use ?offset=&limit= to paginate or ?format=zip.",
            len(talks),
        )
    return ics_file(page, filename=export_filename(requested), user=current_user)
