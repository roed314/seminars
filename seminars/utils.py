from datetime import datetime, timedelta
import pytz
def naive_utcoffset(tz):
    for h in range(10):
        try:
            return pytz.timezone(tz).utcoffset(datetime.now() + timedelta(hours=h))
        except pytz.exceptions.NonExistentTimeError:
            pass

def pretty_timezone(tz):
    foo = naive_utcoffset(tz)
    hours, remainder = divmod(int(foo.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours < 0:
        diff = '{:03d}:{:02d}'.format(hours, minutes)
    else:
        diff = '+{:02d}:{:02d}'.format(hours, minutes)
    return "(GMT {}) {}".format(diff, tz)

timezones = [(v, pretty_timezone(v)) for v in sorted(pytz.common_timezones, key=naive_utcoffset)]


