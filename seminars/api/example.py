
#import json
from requests import post

# We suggest keeping your api token in a separate file and adding it to your .gitignore
# so that you don't accidentlly commit it to your repository
with open("apitoken.txt") as tokenfile:
    apitoken = tokenfile.read().strip()

url = "http://localhost:37778/api/0/save/series/"
payload = {"series_id": "TestSeries", "live_link": "https://zoom.us/j/456789"}

#r = post(url, json=payload, headers={"authorization": "roed@mit.edu %s" % apitoken})
#print(r)
