

def lookup_series():
    from requests import get
    url = 'https://researchseminars.org/api/0/lookup/series?series_id="MITNT"'
    r = get(url)
    if r.status_code == 200:
        J = r.json()
        props = J["properties"]
        talks = J["talks"]
        print("There are %s talks in the %s" % (len(talks), props["name"]))

def lookup_talk():
    from requests import get
    url = 'https://researchseminars.org/api/0/lookup/series?series_id="MathOnlineHostingEvents"&series_ctr=1'
    r = get(url)
    if r.status_code == 200:
        J = r.json()
        props = J["properties"]
        print("%s occurred at %s" % (props["title"], props["start_time"]))

def search_series_get():
    from requests import get
    # Note that America/Los_Angeles is considered different than US/Pacific
    url = 'https://researchseminars.org/api/0/search/series?timezone="US/Pacific"'
    r = get(url)
    if r.status_code == 200:
        J = r.json()
        results = J["results"]
        print("There are %s series in the US/Pacific time zone" % len(results))

def search_series_post():
    url = "https://researchseminars.org/api/0/search/series"
    #FIXME: pyflakes is not happy because url is not referenced
    assert url
    #FIXME: not clear what is supposed to happen here, if anything...

def authorization():
    # We suggest keeping your api token in a separate file and adding it to your .gitignore
    # so that you don't accidentally commit it to your repository
    with open("apitoken.txt") as tokenfile:
        apitoken = tokenfile.read().strip()
    return "roed@mit.edu %s" % apitoken

def create_seminar_series():
    from requests import post
    url = "https://researchseminars.org/api/0/save/series/"
    payload = {"series_id": "test_create",
               "name": "creation test",
               "is_conference": False,
               "topics": ["math_NT"],
               "language": "en", # iso639 code
               "institutions": ["MIT"],
               "timezone": "America/New_York",
               "visibility": 1, # 0=private, 1=unlisted, 2=public
               "access_control": 0, # 0=open, see schema for more
               "slots": ["Mon 15:00-16:00"],
               "organizers": [{"name": "Example User",
                               "email": "user@example.org",
                               "homepage": "https://example.org/~user/",
                               "organizer": True, # False for curators, who are not responsible for scientific content
                               "order": 0,
                               "display": True}]} # True by default
    r = post(url, json=payload, headers={"authorization": authorization()})
    J = r.json()
    code = J.get("code")
    if r.status_code == 200:
        if code == "warning":
            print("Created with warnings", J["warnings"])
        else:
            print("Created successfully")
    else:
        print("Creation failed")
        print(J)

def create_conference():
    from requests import post
    url = "https://researchseminars.org/api/0/save/series/"
    payload = {"series_id": "test_conf",
               "name": "Test conference",
               "is_conference": True,
               "topics": ["math_NT"],
               "language": "en", # iso639 code
               "institutions": ["MIT"],
               "timezone": "America/New_York",
               "visibility": 1, # 0=private, 1=unlisted, 2=public
               "access_control": 0, # 0=open, see schema for more
               "start_date": "June 20, 2020", # we use Python's dateutil.parser
               "end_date": "June 23, 2020",
               "organizers": [{"name": "Example User",
                               "email": "user@example.org",
                               "homepage": "https://example.org/~user/",
                               "order": 0,
                               "organizer": True, # False for curators, who are not responsible for scientific content
                               "display": True}]}
    r = post(url, json=payload, headers={"authorization": authorization()})
    J = r.json()
    code = J.get("code")
    if r.status_code == 200:
        if code == "warning":
            print("Created with warnings", J["warnings"])
        else:
            print("Created successfully")
    else:
        print("Creation failed")
        print(J)

def edit_series():
    from requests import post
    url = "https://researchseminars.org/api/0/save/series/"
    payload = {"series_id": "test_conf",
               "end_date": "June 25, 2020"}
    r = post(url, json=payload, headers={"authorization": authorization()})
    J = r.json()
    code = J.get("code")
    if r.status_code == 200:
        if code == "warning":
            print("Edited with warnings", J["warnings"])
        else:
            print("Edited successfully")
    else:
        print("Editing failed")
        print(J)

def create_talk():
    from requests import post
    from datetime import now, timedelta
    url = "https://researchseminars.org/api/0/save/talk/"
    
    # See https://github.com/roed314/seminars/blob/master/Schema.md for more details
    payload = {
        "series_id": "test_conf",
        
        # Speaker info
        "speaker":"Example Speaker",
        "speaker_email":"Speaker@Talk.ing", # Only visible to organizers
        "speaker_affiliation":"Example Affiliation",

        # Talk info
        "title":"Talk Title",
        "abstract":"Abstract that supports LaTeX",
        "start_time":now().strftime('%Y-%m-%dT%H:%M:%S'),
        "end_time":(now() + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S'),
        "timezone":"UTC", # Not required per se, copied from seminar series

        # Extra info
        "online": True,
        "access_control":5, # Manual registration
        "access_registration":"https://registerehere.doesnotexist",

        # !! Leave these out if unavailable
        #"slides_link":"http://Unavailable.org",
        #"video_link":"http://ToBeUpdated",
        #"paper_link":"https://arxiv.org/abs/test"
    }
        
    r = post(url, json=payload, headers={"authorization": authorization()})
    J = r.json()
    code = J.get("code")
    if r.status_code == 200:
        if code == "warning":
            print("Created talk with series_ctr=%s, warned with %s" % (J["series_ctr"], J["warnings"]))
        else:
            print("Created talk with series_ctr=%s successfully" % (J["series_ctr"]))
    else:
        print("Creation failed")
        print(J)
        
def search_talks_query_language():
    from requests import get
    url = '''https://researchseminars.org/api/0/search/talks?topics={"$contains": "math_NT"}&abstract={"$ilike": "%p-adic%"}'''
    r = get(url)
    if r.status_code == 200:
        J = r.json()
        results = J["results"]
        print("There are %s p-adic number theory talks" % len(results))

def topics():
    from requests import get
    url = "https://researchseminars.org/api/0/topics"
    r = get(url)
    if r.status_code == 200:
        math = r.json()["math"]
        print("%s has %s subtopics" % (math["name"], len(math["children"])))

def institutions():
    from requests import get
    url = "https://researchseminars.org/api/0/institutions"
    r = get(url)
    if r.status_code == 200:
        MIT = r.json()["MIT"]
        print("%s is a %s in %s" % (MIT["name"], MIT["type"], MIT["city"]))
