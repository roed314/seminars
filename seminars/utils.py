from datetime import datetime
import pytz
def pretty_timezone(tz):
    foo = pytz.timezone(tz).utcoffset(datetime.now())
    hours, remainder = divmod(int(foo.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours < 0:
        diff = '{:03d}:{:02d}'.format(hours, minutes)
    else:
        diff = '+{:02d}:{:02d}'.format(hours, minutes)
    return "(GMT {}) {}".format(diff, tz)

timezones = [(v, pretty_timezone(v)) for v in sorted(pytz.common_timezones, key=lambda tz: pytz.timezone(tz).utcoffset(datetime.now()))]

