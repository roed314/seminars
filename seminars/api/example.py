

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
               "topics": ["math_NT"],
               "language": "en", # iso639 code
               "timezone": "America/New_York",
               "visibility": 1, # 0=private, 1=unlisted, 2=public
               "access_control": 0, # 0=open, see schema for more
               "slots": ["Mon 15:00-16:00"],
               "organizers": [{"name": "David Roe",
                               "email": "roed@mit.edu",
                               "homepage": "https://math.mit.edu/~roed/",
                               "curator": False,
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

def topics():
    from requests import get
    url = "https://researchseminars.org/api/0/topics"
    r = get(url)
    if r.status_code == 200:
        math = r.json()["math"]
        print("%s has %s subtopics" % (math["name"], len(math["children"])))
