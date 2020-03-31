
import re
from flask_login import current_user
from seminars import db

shortname_re = re.compile("^[A-Za-z0-9_-]+$")
def allowed_shortname(shortname):
    return bool(shortname_re.match(shortname))

def is_locked(shortname):
    pass

def set_locked(shortname):
    pass

class WebSeminar(object):
    def __init__(self, shortname, data=None, editing=False, showing=False, saving=False):
        if data is None and not editing:
            data = db.seminars.lucky({'shortname': shortname})
            if data is None:
                raise ValueError("Seminar %s does not exist" % shortname)
        if data is None:
            self.shortname = shortname
            self.display = current_user.is_creator()
            self.online = True # default
            self.archived = False # don't start out archived
            self.is_conference = False # seminar by default
            for key, typ in db.seminars.col_type.items():
                if key in ['id', 'shortname', 'display', 'online', 'archived', 'is_conference']:
                    continue
                elif typ == 'text':
                    setattr(self, key, '')
                elif typ == 'text[]':
                    setattr(self, key, [])
                else:
                    raise ValueError("Need to update seminar code to account for schema change")
        else:
            self.__dict__.update(data)
