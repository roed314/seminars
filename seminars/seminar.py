
from seminars import db

class WebSeminar(object):
    def __init__(self, semid, data=None, editing=False, showing=False, saving=False):
        if data is None:
            data = db.lucky({'id': semid})
            if data is None:
                raise ValueError("Seminar %s does not exist" % semid)
        self.__dict__.update(data)
