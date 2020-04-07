Now
===

1. fix default date range

1. add feedback to subscription

1. what should we do if a user is subscribed to a seminar and tries to unsubscribe from a talk in that seminar?



Admin (Edgar)
=====

1. Add ability to request endorsement, then update public_users.html with a link.

1. Add ability to deal with spam: admins should be able to easily hide a page, which should shut down the editing ability of the user who changed it last

1. Stop connecting to the lmfdb database

1. add captcha to reset password and register

1. Use gmail's api or some other api

1. Forward back to page once you log in: https://github.com/LMFDB/lmfdb/blob/master/lmfdb/users/main.py#L251

1. Give users ability to toggle between 24 hour time and am/pm.


Content creation
================

1. **Allow multiple topics (use multi select from [select-pure](https://www.npmjs.com/package/select-pure))**

1. **Makes sure that content creators can cancel or delete talks and seminars if they want.**

1. Allow seminars to meet on multiple days.

1. Think about the model described at https://talks.cam.ac.uk/document/Adding+a+talk (notably, the ability to include others' subscription lists into your own)

1. Think about security model of how we update the display attribute when someone gets endorsed.  Does every talk/seminar that they're an organizer for get set to display=True?  Can this be taken advantage of by adding another user as an organizer who then gets endorsed, or transferring ownership?  We don't require permission to become an organizer/transfer.  Solved if we have newly endorsed users manually have to add the content they want to be displayed.  Also: if you aren't yet endorsed, you can't add other organizers or transfer ownership.

1. Interface for creating a singleton talk?

Viewing and searching
=====================

1. **Filter option to show personal calendar**

1. **Add type (conference/seminar) to seminar search.**

1. **One liner for seminars, add time and frequency.**

1. **Make future the default search.**

1. **Paginate search results.**

1. **Add search on time (rather than datetime) so that users can accomodate their local schedules**

1. **Set minimum/maximum widths for the tds in oneline (so that long speakers/titles/seminar names don't make dates break across lines)**

1. When searching, should have ability to flip sort order (default depends on whether past or future)

1. Figure out how to limit number of seminars shown on browse page for initial users (limit at a certain number per topic?)

1. Should conference homepage be different than a seminar's?

1. Add route that strips headers for inclusion into a seminar webpage

1. When logged in, there should be an option to see the site as if you weren't logged in

1. On the homepage, there should be a note at top explaining benefit of logging in

1. In seminar lists, have icon for online vs offline talk (could be both)

1. We now have a warning that javascript is required (displayed at top of every page).  Another model:  https://iacr.org/tinfoil.html

1. Editable tips

Knowls
======

1. **Update knowl code and knowl database from LMFDB to give the ability to provide explanations (e.g. advertise that they can use latex, explain how to type a dollar sign, have placeholders with examples)**

Time zones
==========

1. **Default seminar time zone come from user time zone.**

1. **Localize time zones in search results.**

1. **When creating things, default to user's time zone.**

1. Add checkbox for use institution time when creating seminar.

Localization
============

1. **Add a language column for talks and seminars.**

1. Django has built in internationalization system (google Zulip internationalization)

Onboarding
==========

1. Write the About page

1. Add to the FAQ page

1. Create a message shown to a user when they first visit the site (detected by absence of the timezone cookie); make sure that information also included in About page

Feedback
========

1. Add avenues for users to give feedback both to content creators

1. **We should create a privacy policy, discussion of cookies**

Calendars
=========

1. **Each seminar should have its own calendar so that seminar organizers can use it as the primary source for their own front-end.**

Email
=====

1. Tim suggest mailgun (cheapest low tier).  Can steal email code from Zulip (they also use Django).  Look at Zulip or Django documentation.  Dedicated IP address helps against spam filtering.  Or use MIT and talk to MIT help desk.

1. Figure out how to make our emails less likely to be marked spam.

1. Customizable announcement emails for seminar organizers.

Design and branding
===================

1. **Clean up css file to remove all the old stuff, think about what we want to have.**

1. Once we're ready, think about advertising strategy (Bjorn emailing number theory list; how to reach out beyond number theory, posting on Facebook, etc)

Other
=====

1. scrape some timezones https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

1. Write tests

1. Reach out to Kiran about recruiting organizers.

1. toggle option between http and https

1. Twitter page?  Talk to someone who uses it.  Grab the username now.

1. Python-social-auth: common framework for authentication integration.  Stackexchange/mathoverflow authentication?

Examples of online seminars we might add
========================================

1. Princeton/IAS number theory

1. [LAGA](https://www.math.univ-paris13.fr/laga/index.php/fr/pm/seminaires?id=97:seminaire-d-analyse-appliquee-2&catid=76:seminaires-pm-edp)

1. [NASO](https://docs.google.com/spreadsheets/d/1MwTXrguSlEon46UKFV1ZJSeozsOECfUvSL6Othufyvs/edit#gid=0)

1. Maria Gillespie launching an algebraic combinatorics one

1. [CRAAG](https://www.daniellitt.com/crag)

Examples of online conferences we might add
===========================================

Look for more on math meetings and email organizers suggesting they add talks to our site?

1. Front Range Number Theory Day (April 25)

Links to posts about online seminars
====================================

- [aosun](http://math.mit.edu/~aosun/online_seminars.html?fbclid=IwAR12HWLaSri3aYplQ3DZNOjnOrjKy6uZmRDmLAX4jX46hkJR_O0eNVVBNWM)
- [littmath](https://www.google.com/url?q=https://twitter.com/littmath/status/1242468857975115777&sa=D&source=hangouts&ust=1585257466247000&usg=AFQjCNES39qjlCfz_icIFwOg6-8j6EF1Rw)
- [Jordan](https://twitter.com/JSEllenberg/status/1238872137588490240)
- [isaksen](https://s.wayne.edu/isaksen/echt/)
- [dermenjian](http://dermenjian.com/seminars/)
- [adams](https://www.math.colostate.edu/~adams/advising/onlineSeminars/?fbclid=IwAR10iN4GQv4jc39IcRiuohJZJbos7iJcFh9v1p2MgTtOBR6TOomWSPaPkzs)
- [Rubinstein-Salzedo](https://www.facebook.com/complexzeta/posts/10107887555517347)
- [Moeller-Williams](https://johncarlosbaez.wordpress.com/2020/03/24/actucr-seminar/?fbclid=IwAR0JUBHUs7mxdnR8ynShIt-6QCFI81mU7DZFwETYHIQCH9QvXcE5lpGALKc)
