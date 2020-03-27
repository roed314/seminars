# Schema

This file provides documentation on the underlying schema; try to keep it up to date if you make changes.  Note that there is also some additional infrastructure imported from the LMFDB (counts and stats tables, which we don't use; we have a separate knowls database with the same infrastructure)

## Users

Note that we've adapted the LMFDB's model, so we don't use `lmfdb.backend.searchtable.PostgresSearchTable` but rather `lmfdb.users.pwdmanager.PostgresUserTable`.

`users`: data on users (note that this is in the userdb schema rather than public schema)

Column              | Type        |  Notes
--------------------|-------------|-------
id                  | bigint      | auto
password            | text        | hashed password with bcrypt
email               | text        | this will act as username
email_confirmed     | boolean     | if the email has been confirmed
admin               | boolean     |
editor              | boolean     |
creator             | boolean     |
full_name           | text        |
affiliation         | text        |
homepage            | text        |
created             | timestamptz |
approver            | text        |
ics_key             | text        |
location            | earth       |
timezone            | text        | time zone code, e.g. "US/Eastern"

`account_tokens`: stores tokens that provide privileges when used to create an account.  These can be sent by admins and editors when inviting people to join the site

Column  | Type        | Notes
--------|-------------|------
id      | bigint      | auto
token   | text        | randomly generated
created | timestamptz | valid for one week, after which the new user will get a suggestion to email the original issuer
used    | boolean     | tokens are one time use
issuer  | text        | username of issuer
editor  | boolean     | whether the newly created user will have editor/creator privileges (admin privileges not possible through a token)

## Institutions, seminars and talks

`institutions`: mainly universities, but some may be in other categories (e.g. MSRI/Banff)

Column   | Type   | Notes
---------|--------|------
id       | bigint | auto
name     | text   |
aliases  | text   | comma separated string of aliases
location | earth  |
homepage | text   |
timezone | text   | time zone code, e.g. "US/Eastern"
city     | text   |
type     | text   | university, institute, other
admin    | text   | username responsible for updating; should be editor/admin

`seminars`: seminars and conferences.  A coherent sequence of talks.

Column       | Type    | Notes
-------------|---------|------
id           | bigint  | auto
name         | text    |
categories   | text[]  |
keywords     | text    |
description  | text    | shown in search results and on seminar homepage, e.g. research seminar, conference, learning seminar
comments     | text    |
institutions | text[]  |
timezone     | text    | time zone code, e.g. "America/New York"
room         | text    |
is_conference| boolean |
homepage     | text    | link to external homepage
display      | boolean | allowed to show; will be true if and only if all organizers have creator privileges
archived     | boolean | seminar is no longer active (and won't show up in users' list of seminars)
online       | boolean |
access       | text    | we need to make a list of predefined access types
live_link    | text    | some seminars may have a consistent link for attending

`talks`: table for individual lectures

Column       | Type        | Notes
-------------|-------------|------
id           | bigint      | auto
title        | text        |
description  | text        |
token        | text        | give permission for speaker to edit
categories   | text[]      |
keywords     | text        |
comments     | text        |
seminar_id   | bigint      | every talk has to be part of a seminar
seminar_name | text        |
display      | boolean     | whether seminar creator has creator privileges
datetime     | timestamptz | start time
timezone     | text        | time zone code, e.g. "America/New York" (this isn't exactly the same as the tz info contained within the datetime, though it's related)
duration     | interval    |
speaker      | text        | full name, not username
speaker_id   | text        | username, may be null
affiliation  | text        | name of university, may be null
online       | boolean     |
access       | text        | we need to make a list of predefined access types
live_link    | text        |
room         | text        |
video_link   | text        | archive video link
slides_link  | text        | link to slides

`categories`: table of categories for seminars and talks

Column       | Type   |  Notes
-------------|--------|-------
id           | bigint | auto
name         | text   |
abbreviation | text   |

## Relations

These tables record various multi-multi relations between entities in the database

`seminar_subscriptions`: for users to follow seminars and add them to their calendar file

Column     | Type   | Notes
-----------|--------|------
id         | bigint | auto
email      | text   |
seminar_id | bigint |
short_name | text   |

`talk_subscriptions`: for users to add individual talks to their calendar file

Column  | Type   | Notes
--------|--------|------
id      | bigint | auto
email   | text   |
talk_id | bigint |

`seminar_organizers`: records which users are the organizers of each seminar

Column     | Type    | Notes
-----------|---------|------
id         | bigint  | auto
seminar_id | bigint  |
email      | text    |
full_name  | text    |
display    | boolean | whether to display in list of seminar organizers
contact    | boolean | whether to specify this person as a contact
