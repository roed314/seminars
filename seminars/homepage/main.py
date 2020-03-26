
from seminars.app import app
from seminars import db
from sage.misc.cachefunc import cached_function

from flask import render_template, request
import datetime

from lmfdb.utils import (
    SearchArray, TextBox, SelectBox, YesNoBox,
    to_dict, search_wrap,
)

@cached_function
def categories():
    return sorted(((rec["abbreviation"], rec["name"]) for rec in db.categories.search()), key=lambda x: x[1].lower())

class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"
    def __init__(self):
        category = SelectBox(
            name="category",
            label="Category",
            options=[("", "")] + categories())
        keywords = TextBox(
            name="keywords",
            label="Keywords")
        speaker = TextBox(
            name="speaker",
            label="Speaker")
        affiliation = TextBox(
            name="affiliation",
            label="Affiliation")
        institution = TextBox(
            name="institution",
            label="Institution")
        title = TextBox(
            name="title",
            label="Title")
        online = SelectBox(
            name="online",
            label="Online",
            options=[("", "only"),
                     ("all", "and offline"),
                     ("exclude", "exclude")])
        when = SelectBox(
            name="when",
            label="Occuring in",
            options=[("", ""),
                     ("future", "the future"),
                     ("past", "the past")])
        date = TextBox( # should have date widget?
            name="date",
            label="Date")
        video = YesNoBox(
            name="video",
            label="Has video")
        avail = SelectBox(
            name="access",
            label="Access",
            options=[("", ""),
                     ("open", "open only")])
        count = TextBox(
            name="count",
            label="Results to display",
            example=50)
        self.browse_array = [[category, keywords], [speaker, affiliation], [title, institution], [when, date], [online], [video, avail], [count]]

@app.route("/")
def index():
    # Eventually want some kind of cutoff on which talks are included.
    talks = list(db.talks.search({'display':True}, projection=["id", "categories", "datetime", "seminar_id", "seminar_name", "speaker", "title"])) # include id
    print(talks)
    return render_template(
        'browse.html',
        title="Math Seminars",
        info={},
        categories=categories(),
        talks=talks,
        bread=None)

@app.route("/search")
def search():
    info = to_dict(request.args, search_array=SemSearchArray())
    if len(request.args) > 0:
        st = info.get("search_type", info.get("hst", "talks"))
        if st == "talks":
            return search_talks(info)
        elif st == "seminars":
            return search_seminars(info)
    return render_template(
        "search.html",
        title="Search seminars",
        info=info,
        categories=categories(),
        bread=None)

@app.route("/seminar/<semid>")
def show_sem(semid):
    pass

@app.route("/talk/<talkid>")
def show_talk(talkid):
    pass

@app.route("/subscribe")
def subscribe():
    # redirect to login page if not logged in, with message about what subscription is
    # If logged in, give a link to download the .ics file, the list of seminars/talks currently followed, and instructions on adding more
    raise NotImplementedError

@app.route("/<category>")
def by_category(category):
    # raise error if not existing category?
    return search({"category":category})

@search_wrap(template="seminar_search_results.html",
             table=db.seminars,
             title="Seminar Search Results",
             err_title="Seminar Search Input Error",
             bread=lambda:[("Search results", " ")])
def search_seminars(info, query):
    # For now, just ignore the info and return all results
    pass

