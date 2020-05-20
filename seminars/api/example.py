

def authorization():
    # We suggest keeping your api token in a separate file and adding it to your .gitignore
    # so that you don't accidentlly commit it to your repository
    with open("apitoken.txt") as tokenfile:
        apitoken = tokenfile.read().strip()
    return "roed@mit.edu %s" % apitoken

def create_seminar_series():
    from requests import post
    url = "http://localhost:37778/api/0/save/series/"
    #url = "https://researchseminars.org/api/0/save/series/"
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
                               "curator": False, # curators are not responsible for scientific content
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

def create_conference():
    from requests import post
    url = "http://localhost:37778/api/0/save/series/"
    #url = "https://researchseminars.org/api/0/save/series/"
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
                               "curator": False, # curators are not responsible for scientific content
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
    url = "http://localhost:37778/api/0/save/series/"
    #url = "https://researchseminars.org/api/0/save/series/"
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
    url = "http://localhost:37778/api/0/save/series/"
    #url = "https://researchseminars.org/api/0/save/series/"
    payload = {"series_id": "test_conf"} # TODO: add more
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

def topics():
    from requests import get
    url = "http://localhost:37778/api/0/topics"
    #url = "https://researchseminars.org/api/0/topics"
    r = get(url)
    if r.status_code == 200:
        math = r.json()["math"]
        print("%s has %s subtopics" % (math["name"], len(math["children"])))

def institutions():
    from requests import get
    url = "http://localhost:37778/api/0/institutions"
    #url = "https://researchseminars.org/api/0/institutions"
    r = get(url)
    if r.status_code == 200:
        MIT = r.json()["MIT"]
        print("%s is a %s in %s" % (MIT["name"], MIT["type"], MIT["city"]))
