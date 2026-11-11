"""Opt-in digest sender for issue #82.

Follow-up to the prototype in ``seminars/notify.py`` (PR #1002): that
module builds change events and resolves subscribers but sends nothing.
This module wires the send path as a safe, reviewable slice:

* :func:`build_digest` -- pure per-subscriber digest rendering.
* :func:`send_digest` -- Flask-Mail delivery, dry-run by default,
  rate-limited, only to explicitly opted-in recipients, never to
  unsubscribed users.
* :func:`preview_digest` -- counts + sample for the organizer preview
  route (never sends).
* :func:`recently_changed` / :func:`mark_recently_changed` -- in-app
  "changed" badge hook reusing ``edited_at`` (7-day window).

Standalone by design: only stdlib imports at module load so unit tests
can load this file without a live DB (cf. ``tests/test_notify.py``).
Flask-Mail/DB access is lazy inside the send helpers.  Nothing here
auto-sends on save; the manage routes call :func:`send_digest`
explicitly with a confirm token.

User dict shape (mirrors ``seminars/notify.py`` plus opt-in)::

    {"email": ..., "email_confirmed": bool,
     "mail_digest_opt_in": bool,          # explicit opt-in, missing == False
     "seminar_subscriptions": [shortname, ...],
     "talk_subscriptions": {shortname: [ctr, ...]},
     "talk_exclusions": {shortname: [ctr, ...]}}

The ``mail_digest_opt_in`` key is the explicit opt-in flag.  There is
currently no such column in the DB (see ``Schema.md``); until it lands,
missing/False means "do not mail".
"""

import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone


#: Per-run recipient cap for the manage send route (anti-spam).
MAX_DIGEST_RECIPIENTS = 50

#: Leaky-bucket ceiling: at most this many real sends per rolling 60s.
MAX_SENDS_PER_MINUTE = 60

#: In-app "changed" badge window (talks edited in the last 7 days).
CHANGED_WINDOW_DAYS = 7

#: Explicit opt-in key on the user dict.  Missing/False == do not mail.
OPT_IN_KEY = "mail_digest_opt_in"

#: Module-level send timestamps (monotonic seconds) for rate limiting.
_SEND_LOG = []


def _as_utc(dt):
    """Return aware-UTC datetime or None (tolerates naive/date/str)."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
        dt = parsed
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    # date (not datetime) -> midnight UTC
    try:
        import datetime as _dt

        if isinstance(dt, _dt.date):
            return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def is_opted_in(user):
    """True only for explicit opt-in + confirmed email address."""
    if not isinstance(user, dict):
        try:
            user = dict(user)
        except Exception:
            return False
    if not user.get(OPT_IN_KEY):
        return False
    if not user.get("email_confirmed"):
        return False
    return bool(user.get("email"))


def _subscribed_to(user, event):
    """True when ``user`` follows the event's series/talk (not excluded)."""
    if not isinstance(event, dict):
        return False
    sid = event.get("seminar_id")
    if not sid:
        return False
    if sid in (user.get("seminar_subscriptions") or []):
        if event.get("scope") == "talk":
            ctr = event.get("seminar_ctr")
            excluded = (user.get("talk_exclusions") or {}).get(sid) or []
            if ctr in excluded:
                return False
        return True
    if event.get("scope") == "talk":
        ctrs = (user.get("talk_subscriptions") or {}).get(sid) or []
        if event.get("seminar_ctr") in ctrs:
            excluded = (user.get("talk_exclusions") or {}).get(sid) or []
            if event.get("seminar_ctr") in excluded:
                return False
            return True
    return False


def eligible_recipients(events, users, max_recipients=MAX_DIGEST_RECIPIENTS):
    """Opt-in, confirmed, subscribed recipients across ``events``.

    Never includes unconfirmed, non-opt-in, or unsubscribed users.
    Returns a sorted email list, capped at ``max_recipients``.
    Pure (no DB, no send).
    """
    if not events:
        return []
    wanted = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        sid = event.get("seminar_id")
        if not sid:
            continue
        for user in users or []:
            if not isinstance(user, dict):
                continue
            if not is_opted_in(user):
                continue
            if _subscribed_to(user, event):
                wanted.add(user["email"])
    return sorted(wanted)[:max_recipients]


def _event_line(event):
    if not isinstance(event, dict):
        return "unknown update"
    if event.get("scope") == "talk":
        what = "%s talk %s" % (event.get("seminar_id"), event.get("seminar_ctr"))
        link = "/talk/%s/%s/" % (event.get("seminar_id"), event.get("seminar_ctr"))
    else:
        what = "series %s" % event.get("seminar_id")
        link = "/seminar/%s" % event.get("seminar_id")
    detail = ", ".join(event.get("changed") or [])
    line = "%s %s" % (event.get("kind", "updated"), what)
    if detail:
        line += ": " + detail
    return "%s (%s)" % (line, link)


def build_digest(subscriber, events):
    """Render a per-subscriber plain-text digest.  Pure (no DB, no send).

    Filters ``events`` to the ones ``subscriber`` follows (never leaks
    unsubscribed series/talks into someone else's mail) and respects
    per-talk mutes (``talk_exclusions``).  Returns
    ``{"to":..., "subject":..., "body":..., "event_count":...}``.
    """
    subscriber = dict(subscriber or {})
    events = [e for e in (events or []) if isinstance(e, dict)]
    mine = [e for e in events if _subscribed_to(subscriber, e)]
    n = len(mine)
    email = subscriber.get("email", "")
    if n == 1:
        subject = "[researchseminars] 1 update to your saved series/talks"
    else:
        subject = "[researchseminars] %d updates to your saved series/talks" % n
    lines = [
        "Hello,",
        "",
        ("You have %d update%s to series/talks you follow:" % (n, "" if n == 1 else "s")),
        "",
    ]
    for event in mine[:25]:
        lines.append("- " + _event_line(event))
    if not mine:
        lines.append("(No updates to your saved series/talks in this batch.)")
    lines += [
        "",
        "You receive this because you opted in to mail digests.",
        "To stop these emails, unfollow the series/talk on the site or turn off the digest opt-in.",
    ]
    return {
        "to": email,
        "subject": subject,
        "body": "\n".join(lines),
        "event_count": n,
    }


def preview_digest(events, users, sample_user=None, max_sample_events=10):
    """Counts + sample for the organizer preview route.  Pure, never sends."""
    events = [e for e in (events or []) if isinstance(e, dict)]
    users = list(users or [])
    recipients = eligible_recipients(events, users)
    if sample_user is None:
        sample_user = next((u for u in users if is_opted_in(u)), {"email": "organizer@example.edu"})
    sample = build_digest(sample_user, events[:max_sample_events])
    return {
        "event_count": len(events),
        "recipient_count": len(eligible_recipients(events, users, max_recipients=10**6)),
        "recipients_capped": len(recipients),
        "recipients_sample": recipients[:5],
        "sample_to": sample["to"],
        "sample_subject": sample["subject"],
        "sample_body": sample["body"],
        "dry_run": True,
        "sent": False,
    }


def check_rate_limit(count, now=None, log=None, cap=MAX_SENDS_PER_MINUTE, window=60.0):
    """Pure rate-limit check: True when ``count`` more sends fit in window."""
    now = time.monotonic() if now is None else now
    log = _SEND_LOG if log is None else log
    cutoff = now - window
    recent = sum(1 for t in log if t > cutoff)
    return recent + count <= cap


def _prune_log(now):
    cutoff = now - 60.0
    while _SEND_LOG and _SEND_LOG[0] <= cutoff:
        _SEND_LOG.pop(0)


def send_digest(
    events,
    users,
    mailer=None,
    send_one=None,
    dry_run=True,
    max_recipients=MAX_DIGEST_RECIPIENTS,
    now=None,
):
    """Send per-subscriber digests.  Dry-run by default (sends nothing).

    Only users with the explicit opt-in flag, a confirmed email, and a
    subscription to at least one event are mailed; unsubscribed users
    are never included.  Recipients are capped at ``max_recipients``
    (clamped to :data:`MAX_DIGEST_RECIPIENTS`) and throttled to
    :data:`MAX_SENDS_PER_MINUTE` per rolling 60s.

    ``send_one`` is a ``(to, subject, body)`` callable used for delivery
    (tests inject a stub); when None and not dry-running, Flask-Mail is
    used lazily.  Returns a summary dict; never raises on per-recipient
    delivery failure (failures are collected in ``errors``).
    """
    events = [e for e in (events or []) if isinstance(e, dict)]
    users = list(users or [])
    cap = min(int(max_recipients or 0), MAX_DIGEST_RECIPIENTS)
    by_email = {}
    for user in users:
        if isinstance(user, dict) and user.get("email"):
            by_email.setdefault(user["email"], user)
    recipients = eligible_recipients(events, users, max_recipients=cap)
    if dry_run:
        sample = build_digest(by_email[recipients[0]], events) if recipients else None
        return {
            "dry_run": True,
            "sent": [],
            "would_send": recipients,
            "skipped_unsubscribed": True,
            "opt_in_only": True,
            "capped_at": cap,
            "sample": sample,
        }
    if send_one is None:
        send_one = _flask_mail_send_one
    moment = time.monotonic() if now is None else now
    _prune_log(moment)
    allowed = max(0, MAX_SENDS_PER_MINUTE - len(_SEND_LOG))
    if allowed <= 0:
        return {
            "dry_run": False,
            "sent": [],
            "would_send": [],
            "rate_limited": True,
            "capped_at": cap,
            "errors": [],
        }
    recipients = recipients[:allowed]
    sent, errors = [], []
    for email in recipients:
        try:
            msg = build_digest(by_email[email], events)
            send_one(msg["to"], msg["subject"], msg["body"])
            sent.append(email)
            _SEND_LOG.append(time.monotonic() if now is None else now)
        except Exception as exc:  # never let one bad address abort the batch
            errors.append({"to": email, "error": str(exc)})
    return {
        "dry_run": False,
        "sent": sent,
        "would_send": [],
        "rate_limited": len(recipients) < len(eligible_recipients(events, users, max_recipients=cap)),
        "capped_at": cap,
        "errors": errors,
    }


def _flask_mail_send_one(to, subject, body):
    """Production delivery via Flask-Mail (lazy import; no top-level dep)."""
    from seminars.app import mail

    try:
        from flask_mail import Message

        sender = "researchseminarsnoreply@math.mit.edu"
        mail.send(Message(subject=subject, body=body, sender=sender, recipients=[to]))
    except Exception:
        # Fallback to the app's html wrapper if Message is unavailable.
        from seminars.app import send_email

        send_email(to, subject, "<pre>%s</pre>" % body)


def recently_changed(edited_at, now=None, window_days=CHANGED_WINDOW_DAYS):
    """True when ``edited_at`` is within ``window_days`` of ``now``.

    Reuses the versioned-write ``edited_at`` stamp.  Naive datetimes are
    read as UTC; None/unparsable stamps return False.  Pure.
    """
    edited_utc = _as_utc(edited_at)
    if edited_utc is None:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    now_utc = _as_utc(now)
    if now_utc is None:
        return False
    delta = now_utc - edited_utc
    if delta < timedelta(0):
        # Tolerate mild clock skew (up to 1h in the future) as "changed".
        return delta >= timedelta(hours=-1)
    return delta <= timedelta(days=window_days)


def mark_recently_changed(talks, now=None, window_days=CHANGED_WINDOW_DAYS):
    """Flag talks edited in the last ``window_days`` days.

    Sets ``changed_badge = True/False`` on dicts (key) or objects
    (attribute) so ``talks_index``/``oneline`` can render an in-app
    "changed" badge reusing ``edited_at``.  Returns the flagged count.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    count = 0
    for talk in talks or []:
        if isinstance(talk, dict):
            edited = talk.get("edited_at")
        else:
            edited = getattr(talk, "edited_at", None)
        flag = recently_changed(edited, now=now, window_days=window_days)
        try:
            if isinstance(talk, dict):
                talk["changed_badge"] = flag
            else:
                setattr(talk, "changed_badge", flag)
        except Exception:
            continue
        if flag:
            count += 1
    return count


def new_confirm_token(nbytes=16):
    """One-time token for the manage send route (stored in session)."""
    return secrets.token_urlsafe(nbytes)


def confirm_token_ok(submitted, expected):
    """Constant-time confirm-token comparison.  Pure."""
    if not submitted or not expected:
        return False
    return hmac.compare_digest(str(submitted), str(expected))
