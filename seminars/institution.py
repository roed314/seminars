from flask import redirect, url_for
from flask_login import current_user
from seminars import db
from seminars.utils import allowed_shortname
from seminars.users.pwdmanager import userdb
from lmfdb.utils import flash_error
from collections.abc import Iterable
from lmfdb.logger import critical
import datetime, pytz

institution_types = [
    ("university", "University"),
    ("institute", "Research institute"),
    ("company", "Company"),
    ("other", "Other"),
]


def institutions():
    return sorted(
        (
            (rec["shortname"], rec["name"])
            for rec in db.institutions.search({}, ["shortname", "name"])
        ),
        key=lambda x: x[1].lower(),
    )


def clean_institutions(inp):
    if inp is None:
        return []
    if isinstance(inp, str):
        inp = inp.strip()
        if not inp:
            # User might not have interacted with the institutions selector at all
            return []
        elif inp[0] == "[" and inp[-1] == "]":
            inp = [elt.strip().strip("'") for elt in inp[1:-1].split(",")]
            if inp == [""]:  # was an empty array
                return []
        else:
            inp = [inp]
    if isinstance(inp, Iterable):
        inp = [elt for elt in inp if elt in dict(institutions())]
    return inp


def institution_known(institution):
    matcher = {"$like": "%{0}%".format(institution)}
    return db.institutions.count({"$or": [{"shortname": matcher}, {"name": matcher}, {"aliases": matcher}]}) > 0


class WebInstitution(object):
    def __init__(self, shortname, data=None, editing=False, showing=False, saving=False):
        if data is None and not editing:
            data = db.institutions.lookup(shortname, projection=3)
            if data is None:
                raise ValueError("Institution %s does not exist" % shortname)
        self.new = data is None
        if self.new:
            self.shortname = shortname
            self.type = "university"
            self.timezone = "US/Eastern"
            self.admin = current_user.email
            for key, typ in db.institutions.col_type.items():
                if key == "id" or hasattr(self, key):
                    continue
                elif typ == "text":
                    setattr(self, key, "")
                elif typ == "text[]":
                    setattr(self, key, [])
                else:
                    critical(
                        "Need to update institution code to account for schema change key=%s" % key
                    )
                    setattr(self, key, None)
        else:
            self.__dict__.update(data)

    def __repr__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, WebInstitution) and all(
            getattr(self, key, None) == getattr(other, key, None)
            for key in db.institutions.search_cols
            if key not in ["edited_at", "edited_by"]
        )

    def __ne__(self, other):
        return not (self == other)

    def save(self):
        data = {col: getattr(self, col, None) for col in db.institutions.search_cols}
        data["edited_by"] = int(current_user.id)
        data["edited_at"] = datetime.datetime.now(tz=pytz.UTC)
        if self.new:
            db.institutions.insert_many([data])
        else:
            assert data.get("shortname")
            db.institutions.upsert({"shortname": self.shortname}, data)

    def admin_link(self):
        rec = userdb.lookup(self.admin)
        link = rec["homepage"] if rec["homepage"] else "mailto:%s" % rec["email"]
        return '<a href="%s"><i>%s</i></a>' % (link, "Contact this page's maintainer.")

def can_edit_institution(shortname, new):
    if not allowed_shortname(shortname) or len(shortname) < 2 or len(shortname) > 32:
        flash_error(
            "The identifier must be 2 to 32 characters in length and can include only letters, numbers, hyphens and underscores."
        )
        return redirect(url_for("list_institutions"), 302), None
    institution = db.institutions.lookup(shortname)
    # Check if institution exists
    if new != (institution is None):
        flash_error("Identifier %s %s" % (shortname, "already exists" if new else "does not exist"))
        return redirect(url_for(".index"), 302), None
    if not new and not current_user.is_admin:
        # Make sure user has permission to edit
        if institution["admin"].lower() != current_user.email.lower():
            rec = userdb.lookup(institution["admin"], "full_name")
            link = rec["homepage"] if rec["homepage"] else "mailto:%s" % rec["email"]
            owner = "%s (%s)" % (rec['name'], link)
            flash_error(
                "You do not have permission to edit %s.  Contact the institution admin, %s, and ask them to fix any errors."
                % (institution["name"], owner)
            )
            return redirect(url_for(".index"), 302), None
    institution = WebInstitution(shortname, data=None, editing=new)
    return None, institution
