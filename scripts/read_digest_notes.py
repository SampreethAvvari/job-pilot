"""Print the Run notes from the most recent JobPilot digest email."""

import base64
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

c = Credentials.from_authorized_user_file("token.json")
g = build("gmail", "v1", credentials=c, cache_discovery=False)
msgs = g.users().messages().list(
    userId="me", q='subject:"JobPilot digest"', maxResults=1
).execute().get("messages", [])
m = g.users().messages().get(userId="me", id=msgs[0]["id"], format="full").execute()


def walk(p):
    if p.get("mimeType", "").startswith("text/") and p.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", "replace")
    for sp in p.get("parts", []) or []:
        r = walk(sp)
        if r:
            return r
    return ""


html = walk(m["payload"])
subject = next(h["value"] for h in m["payload"]["headers"] if h["name"] == "Subject")
print(subject)
notes = re.search(r"Run notes</h4><ul>(.*?)</ul>", html, re.S)
if notes:
    text = re.sub(r"</li>", "\n", notes.group(1)).replace("<li>", "- ")
    print(text.encode("ascii", "replace").decode())
else:
    print("run notes not found")
