
from datetime import timedelta
from flask import url_for
from seminars import db

class WebTalk(object):
    def __init__(self, semid=None, semctr=None, data=None, editing=False, showing=False, saving=False):
        if data is None:
            data = db.talks.lucky({'seminar_id': semid, 'seminar_ctr': semctr})
            if data is None:
                raise ValueError("Seminar %s/%s does not exist" % (semid, semctr))
        self.__dict__.update(data)

    def __repr__(self):
        title = self.title if self.title else "TBA"
        return "%s (%s) - %s" % (title, self.speaker, self.show_time())

    def start(self):
        return self.datetime

    def end(self):
        # Assume duration 1 hour if not listed
        duration = self.duration if self.duration else timedelta(hours=1)
        return self.datetime + duration

    def show_time(self):
        return self.datetime.strftime("%a %b %-d, %-H:%M")

    def show_seminar(self):
        return '<a href="%s">%s</a>' % (url_for("show_seminar", semid=self.seminar_id), self.seminar_name)

    def show_speaker(self):
        return '<a href="%s">%s</a>' % (url_for("show_talk", semid=self.seminar_id, talkid=self.seminar_ctr), self.speaker)

    def oneline(self, include_seminar=True):
        cols = [self.show_time()]
        if include_seminar:
            cols.append(self.show_seminar())
        cols.append(self.show_speaker())
        cols.append(self.title)
        return "".join("<td>%s</td>" % c for c in cols)
