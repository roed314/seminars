Admin (Edgar)
=====

1. Add pages for user management (inviting and approving users, user-add tokens)

1. Add institution page for changing info (e.g. homepage, time zone, aliases)

1. Create login page, mechanisms for resetting password

1. Add ability to deal with spam: admins should be able to easily hide a page, which should shut down the editing ability of the user who changed it last

1. Start a test server, link to mathseminars.org DNS record

1. Stop connecting to the lmfdb database

1. Improve password reset process

1. (Done) Add user page for changing info (e.g. homepage, time zone, affiliation)

1. rename /users

Content creation
================

1. Add pages for creating a seminar and for editing it (overall attributes and adding talks)

1. Add page for speaker/organizer to update the info on a talk

1. Makes sure that content creators can delete things if they want

1. Adapt knowl editing code for content creation and saving.  In particular, this gives us versioning for abstracts.

1. Show help on what input is allowed (advertise that they can use latex, explain how to type a dollar sign, have a placeholder explaining what to do)

1. Include other as a category, handle specially

1. Allow multiple categories

1. Interface for creating a singleton talk

1. Mechanism for canceling talks, archiving seminars

1. Think about the model described at https://talks.cam.ac.uk/document/Adding+a+talk (notably, the ability to include others' subscription lists into your own)

Viewing and searching
=====================

1. Design and implement front page view, both for logged in and new users

1. Adapt search results pages from LMFDB to viewing seminars and talks

1. Create seminar homepage.  Should it be different for a conference?  Either has the capacity to include a link to an external page.

1. Create talk homepage.  Different versions for when talk is in the future, ongoing, or in the past.

1. Top menu: Filter, Search, Calendar, About (includes feedback), Login/Account

1. Only show zoom link if logged in

1. Add route that strips headers for inclusion into a seminar webpage

1. When logged in, there should be an option to see the site as if you weren't logged in

1. When displaying list of seminars, show date, time, name of seminar, speaker, title

1. When searching, should have ability to flip sort order (default depends on whether past or future)

1. On the homepage, there should be a note at top explaining benefit of logging in

1. In seminar lists, have icon for online vs offline talk (could be both)

1. Include counts of how many talks are in each category in the Filter dropdown, only include categories with at least 1

1. Add search on time (rather than datetime) so that users can accomodate their local schedules

Time zones
==========

1. Should get the time zone from the browser when user not logged in (https://stackoverflow.com/questions/6939685/get-client-time-zone-from-browser and https://github.com/iamkun/dayjs)

1. Configure server time zone, rather than hard coding it as Eastern in the source

Feedback
========

1. Add avenues for users to give feedback both to admins and to content creators

1. We should create a privacy policy, discussion of cookies

Calendars
=========

1. Write code for dynamically generating .ics files

Email
=====

1. The system needs to be able to send emails.  Figure out how to make that work.

Design and branding
===================

1. Clean up css file to remove all the old stuff, think about what we want to have.

1. Come up with a logo and favicon

1. Think of a good name and register it

1. Once we're ready, think about advertising strategy (Bjorn emailing number theory list; how to reach out beyond number theory, posting on Facebook, etc)

Links to posts about online seminars
====================================

- [aosun](http://math.mit.edu/~aosun/online_seminars.html?fbclid=IwAR12HWLaSri3aYplQ3DZNOjnOrjKy6uZmRDmLAX4jX46hkJR_O0eNVVBNWM)
- [littmath](https://www.google.com/url?q=https://twitter.com/littmath/status/1242468857975115777&sa=D&source=hangouts&ust=1585257466247000&usg=AFQjCNES39qjlCfz_icIFwOg6-8j6EF1Rw)
- [Jordan](https://twitter.com/JSEllenberg/status/1238872137588490240)
- [isaksen](https://s.wayne.edu/isaksen/echt/)
