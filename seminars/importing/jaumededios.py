"""
Import data from the csv file backing http://jaume.dedios.cat/math-seminars/
"""
from csv import reader
from dateutil.parser import parse
from seminars.seminar import seminars_lookup
from seminars.talk import talks_lucky, talks_max
import datetime, pytz, random


def import_talks(csv_file):
    talks = []
    ctr = {}
    with open(csv_file) as F:
        for i, line in enumerate(reader(F)):
            if i == 0:
                assert line == [
                    "Timestamp",
                    "Title",
                    "Speaker",
                    "Speaker_inst",
                    "Abstract",
                    "Host",
                    "Seminar",
                    "Site",
                    "In_Charge",
                    "arXiv",
                    "Date",
                    "Start_Time",
                    "End_Time",
                    "Timezone",
                    "Approved",
                ]
                continue
            (
                timestamp,
                title,
                speaker,
                speaker_affiliation,
                abstract,
                host,
                seminar_id,
                site,
                in_charge,
                arXiv,
                date,
                start_time,
                end_time,
                timezone,
                approved,
            ) = line
            # Make sure seminar exists
            seminar = seminars_lookup(seminar_id)
            if not seminar:
                continue
            if seminar is None:
                print("Warning: seminar %s does not exist" % seminar_id)
                continue
            if seminar_id not in ctr:
                m = talks_max("seminar_ctr", {"seminar_id": seminar_id})
                if m is None:
                    m = -1
                ctr[seminar_id] = m + 1
            # This time zone info is specific to importing in early April
            # There is some broken data, where time zones were incrementing the minute.  We reset them all to zero.
            tzdict = {
                -7: "America/Los_Angeles",
                -4: "America/New_York",
                -5: "America/Chicago",
                -3: "America/Buenos_Aires",
                2: "Europe/Paris",
                1: "Europe/London",
            }
            timezone = tzdict[int(timezone[4:7])]
            tz = pytz.timezone(timezone)
            date = parse(date, dayfirst=True).date()
            start_time = tz.localize(datetime.datetime.combine(date, parse(start_time).time()))
            end_time = tz.localize(datetime.datetime.combine(date, parse(end_time).time()))
            # Check to see if a talk at this time in the seminar already exists
            curtalk = talks_lucky({"seminar_id": seminar_id, "speaker": speaker})
            if curtalk is not None:
                print(
                    "Talk with speaker %s already exists in seminar %s; continuing"
                    % (speaker, seminar_id)
                )
                continue
            curtalk = talks_lucky({"seminar_id": seminar_id, "start_time": start_time})
            if curtalk is not None:
                print(
                    "Talk at time %s (speaker %s) already exists in seminar %s; continuing"
                    % (start_time.strftime("%a %b %d %-H:%M"), speaker, seminar_id)
                )
                continue
            topics = (
                arXiv.replace(" ", "").replace("Math.", "").replace("math.", "").lower().split(",")
            )
            if not topics:
                topics = []
            talks.append(
                dict(
                    title=title,
                    speaker=speaker,
                    speaker_affiliation=speaker_affiliation,
                    abstract=abstract,
                    topics=topics,
                    timezone=timezone,
                    start_time=start_time,
                    end_time=end_time,
                    display=True,
                    token="%016x" % random.randrange(16 ** 16),
                    online=True,
                    live_link=seminar.live_link,
                    room=seminar.room,
                    access=seminar.access,
                    comments=seminar.comments,
                    seminar_id=seminar_id,
                    seminar_ctr=ctr[seminar_id],
                )
            )
            ctr[seminar_id] += 1
    return talks
