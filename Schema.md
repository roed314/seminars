# Schema

This file provides documentation on the underlying schema; try to keep it up to date if you make changes.  Note that there is also some additional infrastructure imported from the LMFDB (counts and stats tables, which we don't use; we have a separate knowls database with the same infrastructure).  Except for id (always first), columns are sorted by name (please maintain this).

## Users

Note that we've adapted the LMFDB's model, so we don't use `lmfdb.backend.searchtable.PostgresSearchTable` but rather `lmfdb.users.pwdmanager.PostgresUserTable`.

`users`: data on users (note that this is in the userdb schema rather than public schema)

Column                | Type        |  Notes
----------------------|-------------|-------
id                    | bigint      | auto
admin                 | boolean     | whether the user has admin privileges
affiliation           | text        | university or other institution
api_access            | smallint    | 0 = no access, 1 access
api_token             | text        | a string that grants access to the account through the api
created               | timestamptz | when account was created
creator               | boolean     | can create seminars which are displayed
email                 | text        | this will act as username
email_confirmed       | boolean     | if the email has been confirmed
endorser              | integer     | userid of another user who endorses this one
homepage              | text        | user's website
name                  | text        | user's name
password              | text        | hashed password with bcrypt
seminar_subscriptions | text[]      | set of short names of seminars that the user is subscribed to
subject_admin         | text        | topic_id for a topic that this user has admin privileges for
talks_subscriptions   | json        | dict as {shorname : list of counters}
timezone              | text        | time zone code, e.g. "US/Eastern"


## Institutions, seminars and talks

`institutions`: mainly universities, but some may be in other categories (e.g. MSRI/Banff)

Column    | Type        | Notes
----------|-------------|------
id        | bigint      | auto
admin     | text        | users.email of user responsible for maintaining institution listing
city      | text        | name of the city where the institution is located
deleted   | text        | set if institution has been deleted (may still be revived)
edited_at | timestamptz | timestamp of this version
edited_by | bigint      | users.id of user who created this version
homepage  | text        | URL of homepage for the institution
name      | text        | name displayed for the institution (anchor for homepage link)
shortname | text        | Assigned by admin on creation, used in urls, globally unique, cannot be changed (would break links)
timezone  | text        | time zone code, e.g. "US/Eastern"
type      | text        | university, institute, other, taken from selector

`seminars`: seminars and conferences.  A coherent sequence of talks.  Columns marked [inherited] are copied into each talk that is part of the seminar and can then be customized for individual talks.

Column              | Type        | Notes
--------------------|-------------|------
id                  | bigint      | auto
access_control      | smallint    | live_link access control: 0=open  1=time, 2=password, 3=users, 4=internal reg., 5=external reg., null if not online [inherited]
access_time         | integer     | number of minutes before talks.start_time that talks.live_link is shown if access_control=1, null otherwise [inherited]
accces_hint         | text        | hint for live_link password, required if access_control=2, null otherwise [inherited]
access_registration | text        | URL (possibly an email) for external registration if access_control=5, null otherwise [inhertied]
audience            | smallint    | 0 = researchers in topic, 1 = researchers in discipline, 2 = advanced learners, 3 = learners, 4 = undergraudates, 5 = general public [inherited]
chat_link           | text        | URL linking to chat stream for the series (e.g. Zulip, Slack, Discord, ...)
comments            | text        |
deleted             | boolean     | True if seminar has been deleted (it can still be revived)
display             | boolean     | shown on browse/search pages; will be set once the owner has creator privileges.  Also used by API.
edited_at           | timestamptz | timestamp of this version
edited_by           | bigint      | users.id of user who created this version
end_date            | date        | end date of the conference, null for seminar series
frequency           | iinteger    | for seminar series, the periodicity of the meetings (0=no fixed schedule, 7=weekly, 14=biweekly, 21=triweekly), null for conferences
homepage            | text        | link to external homepage (if any)
institutions        | text[]      | list of institutions.shortname values for the institutions associated to this seminar
is_conference       | boolean     | True for conferences, False for seminar_series; per_day, start_date, end_date are specific to conferences; frequency, weekdays, time_slots are specific to seminar_series
language            | text        | language abbreviation taken from language selector, required [inherited]
live_link           | text        | URL for online meeting link (e.g. Zoom) if fixed, may be set to "see comments" (once access_control is in place, "see comments" should no longer be necessary) [inherited]
name                | text        |
online              | boolean     | True if talks in the seminar can be viewed online [inherited]
owner               | text        | users.email of owner of seminar, who controls the list of organizers (and can transfer ownership)
per_day             | integer     | number of talks per day of a conference (only used to layout schedule), null for seminar_series
room                | text        | physical location of the conference, if any [inherited]
shortname           | text        | Unique identifier assigned by owner, used in urls, cannot be changed (would break links)
start_date          | date        | start date of the conference, null for seminar_series
stream_link         | text        | URL for non-interactive livestream (e.g. YouTube), not yet used [inherited]
timezone            | text        | time zone code, e.g. "America/New York"
time_slots          | text[]      | list of time slots for seminar series with frequency != 0, null for conferences.  Each entry is a daytime interval of the form "HH:MM-HH:MM"; if end time is less than start time the interval extends to the next day.  All of relative to the timezone of the seminar.
topics              | text[]      | list of topics.abbreviation for each topic associated ot the seminar [inherited]
visibility          | smallint    | 0 = private, 1 = unlisted, 2 = public (only talks in public seminars are shown on the browse/search pages)
weekdays            | smallint[]  | list of weekdays (0=Monday, 6=Sunday) one for each time slot for the seminar series, null for conferences

`talks`: table for individual lectures

Column              | Type        | Notes
--------------------|-------------|------
id                  | bigint      | auto
abstract            | text        | may contain latex
access_control      | smallint    | live_link access control: 0=open  1=time, 2=password, 3=users, 4=internal reg, 5=external reg., null if not online [inherited]
access_time         | integer     | number of minutes before talk start time live_link is shown if access_control=1, null otherwise [inherited]
accces_hint         | text        | hint for live_link password, required if access_control=2, null otherwise [inherited]
access_registration | text        | URL (possibly an email) for external registration if access_control=5, null otherwise [inhertied]
audience            | smallint    | 0 = researchers in topic, 1 = researchers in discipline, 2 = advanced learners, 3 = learners, 4 = undergraudates, 5 = general public [inherited]
chat_link           | text        | URL linking to chat stream for the talk (e.g. Zulip, Slack, Discord, ...)
comments            | text        | talk specific comments to be displayed in addition to seminar comments
deleted             | boolean     | indicates talk has been deleted (but can still be revived)
deleted_with_seminar| boolean     | indicates talk was deleted when seminar was deleted (will be automatically revived if/when seminar is revived)
display             | boolean     | whether to display publicly (set if creator is True for the user who created the seminar).  Also used by API [inherited]
edited_at           | timestamptz | timestamp of this version
edited_by           | bigint      | users.id of user who created this version
end_time            | timestamptz | 
hidden              | boolean     | if True, the talk will be visible only on the Edit schedule page for the seminar (independent of display)
language            | text        | language abbreviation taken from language selector, required [inherited]
live_link           | text        | URL for online meeting link (e.g. Zoom) [inherited]
online              | boolean     | True if talk can be viewed online (copied from seminar), note that both online and room may be set
paper_link          | text        | URL providing link to a paper the talk is about
room                | text        | physical location of the talk [inherited]
seminar_ctr         | integer     | unique identifier for this talk among the talks in this series
seminar_id          | text        | seminars.shortname of series containing this talk (every talk belongs to some series)
slides_link         | text        | URL providing link to slides for the talk
speaker             | text        | full name of the speaker (required) [to be replaced by speakers]
speaker_email       | text        | email address of the speaker, it need not match the email of any user [to be replaced by speaker_emails]
speaker_affiliation | text        | free text, it need not be present in the insitutions table (optional) [to be replaced by speaker_affiliations]
speaker_homepage    | text        | URL of the homepage for the speaker (speaker's name will be anchor for this link) [to be replaced by speaker_homepages]
start_time          | timestamptz | 
stream_link         | text        | URL for non-interactive livestream (e.g. YouTube), not yet used [inherited]
timezone            | text        | time zone, e.g. "America/New York" (not necessarily the same as the tz in start_time, but related) (copied from semianr)
title               | text        | may contain latex, will be shown as TBA if left blank
token               | text        | used to give permission for speaker to edit
topics              | text[]      | list of topic identifiers for the talk
video_link          | text        | archived video recording of the talk (should be set after the talk takes place)

`topics`: table of topics for seminars and talks (to be changed soon)

Column       | Type   |  Notes
-------------|--------|-------
id           | bigint | auto
name         | text   |
abbreviation | text   |

## Relations

These tables record various multi-multi relations between entities in the database


`seminar_organizers`: records which users are the organizers of each seminar

Column     | Type    | Notes
-----------|---------|------
id         | bigint  | auto
seminar_id | text    | seminars.shortname of seminar this organizer record belongs to
email      | text    | email of the organizer
homepage   | text    | URL for the homepage of the organizer
name       | text    | full name of the organizer
curator    | boolean | True if curator, False if organizer
display    | boolean | whether to display on the page for the series
order      | integer | controls the order in which organizers are displayed
