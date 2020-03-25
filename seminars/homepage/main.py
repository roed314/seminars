
from seminars.app import app
from seminars import db

from flask import render_template

from lmfdb.utils import (
    SearchArray, TextBox, SelectBox, YesNoBox,
    to_dict, search_wrap,
)

class SemSearchArray(SearchArray):
    noun = "seminar"
    plural_noun = "seminars"
    def __init__(self):
        category = SelectBox(
            name="category",
            label="Category",
            options=[("", "")] + categories)
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
    print("starting index")
    info = to_dict(request.args, search_array=SemSearchArray())
    if len(request.args) > 0:
        return search(info)
    today = datetime.datetime.today().weekday() # account for time zone....
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    if today not in [5, 6]: # weekday
        days = days[today:] + days[:today]
        days[0] = "Today"
        if today !=  4:
            days[1] = "Tomorrow"

    return render_template(
        'browse.html',
        title="Math Seminars",
        info=info,
        categories=categories,
        days=days,
        bread=None)

@app.route("/<category>")
def by_category(category):
    # raise error if not existing category?
    return search({"category":category})

@search_wrap(template="seminar_search_results.html",
             table=db.seminars,
             title="Seminar Search Results",
             err_title="Seminar Search Input Error",
             bread=lambda:[("Search results", " ")])
def seminar_search(info, query):
    # For now, just ignore the info and return all results
    pass

