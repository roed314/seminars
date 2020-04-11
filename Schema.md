# Schema

This file provides documentation on the underlying schema; try to keep it up to date if you make changes.  Note that there is also some additional infrastructure imported from the LMFDB (counts and stats tables, which we don't use; we have a separate knowls database with the same infrastructure)

## Users

Note that we've adapted the LMFDB's model, so we don't use `lmfdb.backend.searchtable.PostgresSearchTable` but rather `lmfdb.users.pwdmanager.PostgresUserTable`.

`users`: data on users (note that this is in the userdb schema rather than public schema)

Column                | Type        |  Notes
----------------------|-------------|-------
id                    | bigint      | auto
password              | text        | hashed password with bcrypt
email                 | text        | this will act as username
email_confirmed       | boolean     | if the email has been confirmed
admin                 | boolean     |
creator               | boolean     | can create seminars which are displayed
name                  | text        |
affiliation           | text        |
homepage              | text        |
created               | timestamptz |
endorser              | text        | email address of another user who endorses this one
location              | earth       |
timezone              | text        | time zone code, e.g. "US/Eastern"
seminar_subscriptions | text[]      | set of short names of seminars that the user is subscribed to
talks_subscriptions   | json        | dict as {shorname : list of counters}


## Institutions, seminars and talks

`institutions`: mainly universities, but some may be in other categories (e.g. MSRI/Banff)

Column    | Type   | Notes
----------|--------|------
id        | bigint | auto
shortname | text   | Assigned by admin on creation, used in urls, globally unique, cannot be changed (would break links)
name      | text   |
aliases   | text   | comma separated string of aliases
location  | earth  |
homepage  | text   |
timezone  | text   | time zone code, e.g. "US/Eastern"
city      | text   |
type      | text   | university, institute, other
admin     | text   | username responsible for updating, starts as creator

`seminars`: seminars and conferences.  A coherent sequence of talks.

Column       | Type        | Notes
-------------|-------------|------
id           | bigint      | auto
shortname    | text        | Assigned by owner, used in urls, globally unique, cannot be changed (would break links)
name         | text        |
topics       | text[]      |
keywords     | text        |
description  | text        | shown in search results and on seminar homepage, e.g. research seminar, conference, learning seminar
comments     | text        |
institutions | text[]      |
timezone     | text        | time zone code, e.g. "America/New York"
weekday      | smallint    | 0=Monday, 6=Sunday for consistency with Python
start_time   | timestamptz | Start time, on Jan 1 2020.  Pick a fixed date to fix the conversion with utcoffset which postgres uses
end_time     | timestamptz | End time, on Jan 1 2020.  Pick a fixed date to fix the conversion with utcoffset which postgres uses
frequency    | int         | meeting frequency in days (often 7)
room         | text        |
is_conference| boolean     |
homepage     | text        | link to external homepage
display      | boolean     | allowed to show; will be true if and only if all organizers have creator privileges
owner        | text        | email of owner of seminar, who controls the list of organizers (and can transfer ownership)
archived     | boolean     | seminar is no longer active (and won't show up in users' list of seminars)
online       | boolean     |
access       | text        | we need to make a list of predefined access types
live_link    | text        | some seminars may have a consistent link for attending

`talks`: table for individual lectures

Column              | Type        | Notes
--------------------|-------------|------
id                  | bigint      | auto
title               | text        |
abstract            | text        |
token               | text        | give permission for speaker to edit
topics              | text[]      |
keywords            | text        |
comments            | text        |
seminar_id          | text        | shortname of seminar (every talk has to be part of a seminar)
seminar_ctr         | int         | Counter of talks within a given seminar
display             | boolean     | whether seminar creator has creator privileges
start_time          | timestamptz |
end_time            | timestamptz |
timezone            | text        | time zone code, e.g. "America/New York" (this isn't exactly the same as the tz info contained within the datetime, though it's related)
speaker             | text        | full name, not username
speaker_email       | text        | username, may be null
speaker_affiliation | text        | name of university, may be null
speaker_homepage    | text        |
online              | boolean     |
access              | text        | we need to make a list of predefined access types
live_link           | text        |
room                | text        |
video_link          | text        | archive video link
slides_link         | text        | link to slides

`topics`: table of topics for seminars and talks

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
seminar_id | text    |
email      | text    |
full_name  | text    |
order      | int     | Controls order organizers displayed
curator    | boolean | whether to include in the curator (rather than the organizer field)
display    | boolean | whether to display on the page
contact    | boolean | whether to include the email
