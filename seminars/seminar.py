
import re
from seminars import db

semid_re = re.compile("^[A-Za-z0-9_-]+$")
def allowed_semid(semid):
    return return bool(semid_re.match(semid))

def is_locked(semid):
    pass

def set_locked(semid):
    pass

class WebSeminar(object):
    def __init__(self, semid, data=None, editing=False, showing=False, saving=False):
        if data is None:
            data = db.lucky({'id': semid})
            if data is None:
                raise ValueError("Seminar %s does not exist" % semid)
        self.__dict__.update(data)
