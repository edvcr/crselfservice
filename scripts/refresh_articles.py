"""Rebuild dist/help-articles.json from the published Zendesk Help Center articles.

The Help Center is not public, so the widget reads this snapshot instead of the live API.
Credentials (GitHub secrets): ZENDESK_CLIENT_ID and ZENDESK_CLIENT_SECRET of a dedicated
Zendesk OAuth client. Each run requests a fresh, short-lived token limited to hc:read
(Help Center read-only), so nothing expires. ZENDESK_HC_TOKEN (a fixed hc:read token) also works.
The file is rewritten only when an article or section changed, so unchanged runs make no commit.
"""
import datetime
import json
import os
import sys
import urllib.request

BASE = "https://coinsraidcom.zendesk.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "dist", "help-articles.json")


def get_token():
    cid, secret = os.environ.get("ZENDESK_CLIENT_ID"), os.environ.get("ZENDESK_CLIENT_SECRET")
    if cid and secret:
        body = json.dumps({"grant_type": "client_credentials", "client_id": cid,
                           "client_secret": secret, "scope": "hc:read"}).encode()
        req = urllib.request.Request(BASE + "/oauth/tokens", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.load(res)["access_token"]
    if os.environ.get("ZENDESK_HC_TOKEN"):
        return os.environ["ZENDESK_HC_TOKEN"]
    sys.exit("Set ZENDESK_CLIENT_ID and ZENDESK_CLIENT_SECRET under Settings > Secrets and variables > Actions")


def fetch_all(path, key, token):
    items, url = [], BASE + path
    while url:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.load(res)
        items += data[key]
        url = data.get("next_page")
    return items


def main():
    token = get_token()
    sections = fetch_all("/api/v2/help_center/en-us/sections.json?per_page=100", "sections", token)
    articles = [a for a in fetch_all("/api/v2/help_center/en-us/articles.json?per_page=100", "articles", token)
                if not a["draft"]]
    if not sections or not articles:
        sys.exit("Refusing to write an empty snapshot")

    content = {
        "sections": [{"id": s["id"], "name": s["name"], "description": s.get("description") or "", "position": s["position"]}
                     for s in sorted(sections, key=lambda s: (s["position"], s["id"]))],
        "articles": [{"id": a["id"], "section_id": a["section_id"], "title": a["title"], "position": a["position"], "body": a["body"]}
                     for a in sorted(articles, key=lambda a: (a["section_id"], a["position"], a["id"]))],
    }
    try:
        with open(OUT) as f:
            current = json.load(f)
        if current.get("sections") == content["sections"] and current.get("articles") == content["articles"]:
            print(f"No changes ({len(content['articles'])} articles)")
            return
    except FileNotFoundError:
        pass

    snapshot = {"generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **content}
    with open(OUT, "w") as f:
        json.dump(snapshot, f)
    print(f"Updated snapshot: {len(content['sections'])} sections, {len(content['articles'])} articles")


if __name__ == "__main__":
    main()
