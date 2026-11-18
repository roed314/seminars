"""Push-on-edit notification prototype (part of #82).

Pure functions only: build change events from old/new version dicts and
resolve subscribed recipients from user dicts.  Deliberately NOT wired
into any request path and sends nothing -- the mailer/queue is follow-up.

User dict shape mirrors PostgresUserTable columns:
    {"email": ..., "email_confirmed": bool,
     "seminar_subscriptions": [shortname, ...],
     "talk_subscriptions": {shortname: [ctr, ...]}}
Talk/series dicts are plain version rows (WebTalk/WebSeminar __dict__).
"""

TALK_WATCHED_FIELDS = [
    "title", "abstract", "speaker", "speaker_affiliation",
    "start_time", "end_time", "timezone", "room", "online",
    "live_link", "stream_link", "video_link", "slides_link",
    "language", "topics", "access_control",
]

SERIES_WATCHED_FIELDS = [
    "name", "description", "homepage", "room", "online",
    "live_link", "stream_link", "language", "topics",
    "institutions", "timezone", "visibility",
]


def _changed(old, new, fields):
    """Names of watched fields whose values differ (missing == None)."""
    return [f for f in fields if (old or {}).get(f) != (new or {}).get(f)]


def talk_event(old, new):
    """Describe the edit from version ``old`` to ``new`` (either may be None).

    Returns None when nothing subscriber-visible changed.
    """
    if old is None and new is None:
        return None
    if old is None:
        return {
            "scope": "talk",
            "kind": "created",
            "seminar_id": new.get("seminar_id"),
            "seminar_ctr": new.get("seminar_ctr"),
            "changed": [f for f in TALK_WATCHED_FIELDS if new.get(f) is not None],
        }
    if new is None or new.get("deleted") or not new.get("display", True):
        return {
            "scope": "talk",
            "kind": "cancelled",
            "seminar_id": old.get("seminar_id"),
            "seminar_ctr": old.get("seminar_ctr"),
            "changed": [],
        }
    changed = _changed(old, new, TALK_WATCHED_FIELDS)
    if not changed:
        return None
    kind = "rescheduled" if "start_time" in changed or "end_time" in changed else "updated"
    return {
        "scope": "talk",
        "kind": kind,
        "seminar_id": new.get("seminar_id"),
        "seminar_ctr": new.get("seminar_ctr"),
        "changed": changed,
    }


def series_event(old, new):
    """Describe the edit from series version ``old`` to ``new``."""
    if old is None and new is None:
        return None
    if old is None:
        return {
            "scope": "series",
            "kind": "created",
            "seminar_id": new.get("shortname"),
            "changed": [f for f in SERIES_WATCHED_FIELDS if new.get(f) is not None],
        }
    if new is None or new.get("deleted") or not new.get("display", True):
        return {
            "scope": "series",
            "kind": "cancelled",
            "seminar_id": old.get("shortname"),
            "changed": [],
        }
    changed = _changed(old, new, SERIES_WATCHED_FIELDS)
    if not changed:
        return None
    return {
        "scope": "series",
        "kind": "updated",
        "seminar_id": new.get("shortname"),
        "changed": changed,
    }


def subscribers_for_event(event, users):
    """Confirmed-email recipients subscribed to the event's series/talk.

    Talk events fan out to whole-series subscribers plus subscribers of
    that exact talk; series events go to whole-series subscribers.
    Topic filtering is future work (topic prefs live in cookies, #82).
    """
    if event is None:
        return []
    sid = event.get("seminar_id")
    recips = set()
    for user in users:
        if not user.get("email_confirmed"):
            continue
        email = user.get("email")
        if not email:
            continue
        if sid in (user.get("seminar_subscriptions") or []):
            recips.add(email)
        elif event.get("scope") == "talk":
            ctrs = (user.get("talk_subscriptions") or {}).get(sid) or []
            if event.get("seminar_ctr") in ctrs:
                recips.add(email)
    return sorted(recips)


def render_digest(events):
    """One-line-per-event plain-text digest (feeds the future mailer)."""
    lines = []
    for event in events:
        if event.get("scope") == "talk":
            what = "%s talk %d" % (event.get("seminar_id"), event.get("seminar_ctr"))
        else:
            what = "series %s" % event.get("seminar_id")
        detail = ", ".join(event.get("changed") or [])
        lines.append("%s %s%s" % (event.get("kind"), what,
                                  (": " + detail) if detail else ""))
    return "\n".join(lines)
