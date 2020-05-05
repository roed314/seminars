# To edit knowls, edit the knowls.yaml file

import os, yaml
from markupsafe import Markup
from flask import render_template


def load_knowls():
    _curdir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(_curdir, "knowls.yaml")) as F:
        return yaml.load(F, Loader=yaml.FullLoader)


# Since we load the knowls from disk on import, note that you must restart the server when you update the knowl file
knowldb = load_knowls()


def static_knowl(name, title=None):
    knowl = knowldb.get(name)
    if knowl is None:
        if title is None:
            return ""
        else:
            return title
    if title is None:
        title = knowl.get("title", "")
    knowl["contents"]=Markup(knowl.get("contents",""))
    return r'<a title="{title}" knowl="dynamic_show" kwargs="{content}">{title}</a>'.format(
        title=title, content=Markup.escape(render_template("static-knowl.html", knowl=knowl))
    )


