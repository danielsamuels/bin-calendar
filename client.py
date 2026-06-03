import base64
import json
from datetime import date, datetime, timedelta
from functools import reduce

import arrow
import requests
from ics import Calendar, Event


BASE_URL = "https://eastcambs-self.achieveservice.com"
LOOKUP_ID = "6784e74793b68"
STAGE_ID = "AF-Stage-94ee5097-94db-474d-bc7a-d1796e3ab83a"
FORM_ID = "AF-Form-b10c1e46-e09b-4c18-a31f-b1113609860a"
PROCESS_ID = "AF-Process-2c7575a6-0139-4555-9d8a-ab504a44d989"
AUTH_LOOKUP_ID = "69d8f92eea3cf"


def _find_auth_lookup_id(obj) -> str | None:
    """Recursively search a form definition for the getauthentication lookup ID."""
    if isinstance(obj, dict):
        props = obj.get("props", {}) if isinstance(obj.get("props"), dict) else {}
        if obj.get("dataName") == "getauthentication":
            return obj.get("lookup") or props.get("lookup")
        if props.get("dataName") == "getauthentication":
            return props.get("lookup")
        for v in obj.values():
            result = _find_auth_lookup_id(v)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_auth_lookup_id(item)
            if result:
                return result
    return None


def _find_token_in_response(obj) -> str | None:
    """Recursively search an API response for an AuthenticateResponse value."""
    if isinstance(obj, dict):
        if "AuthenticateResponse" in obj:
            val = obj["AuthenticateResponse"]
            return val if isinstance(val, str) else val.get("value")
        if obj.get("name") == "AuthenticateResponse" and "value" in obj:
            return obj["value"]
        for v in obj.values():
            result = _find_token_in_response(v)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_token_in_response(item)
            if result:
                return result
    return None


def fetch_auth_token(session: requests.Session) -> str | None:
    """Fetch the auth token from the East Cambs AchieveForms API.

    The form contains an autoLookup field (dataName=getauthentication) that runs
    at page load to populate AuthenticateResponse. We replicate this by:
      1. Fetching the form definition via GetDocument to discover the lookup ID.
      2. Running that lookup to obtain the current token value.
    """
    sid = session.cookies.get("PHPSESSID", "")
    form_url = (
        f"{BASE_URL}/AchieveForms/"
        f"?mode=fill&consentMessage=yes"
        f"&form_uri=sandbox-publish://{PROCESS_ID}/{STAGE_ID}/definition.json"
        f"&process=1&process_uri=sandbox-processes://{PROCESS_ID}"
        f"&process_id={PROCESS_ID}"
    )
    xhr_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": form_url,
        "Accept": "application/json, text/plain, */*",
    }

    # Discover the getauthentication lookup ID from the form definition.
    # Fall back to the known ID if the definition can't be fetched.
    auth_lookup_id = AUTH_LOOKUP_ID
    doc_url = (
        f"{BASE_URL}/apibroker/?api=GetDocument"
        f"&uri=sandbox-publish://{PROCESS_ID}/{STAGE_ID}/definition.json"
        f"&app_name=AF-Renderer::Self&sid={sid}"
    )
    try:
        r = session.get(doc_url, timeout=15, headers=xhr_headers)
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            content_b64 = r.json().get("content", "")
            if content_b64:
                definition = json.loads(base64.b64decode(content_b64 + "==").decode())
                discovered = _find_auth_lookup_id(definition)
                if discovered:
                    auth_lookup_id = discovered
    except Exception as e:
        print(f"Warning: could not fetch form definition ({e}), using known lookup ID")

    # Run the getauthentication lookup to get the current token.
    print(f"Fetching auth token (lookup {auth_lookup_id})...")
    lookup_url = (
        f"{BASE_URL}/apibroker/runLookup"
        f"?id={auth_lookup_id}&repeat_against=&noRetry=false"
        f"&getOnlyTokens=undefined&log_id="
        f"&app_name=AF-Renderer::Self&sid={sid}"
    )
    try:
        r = session.post(lookup_url, json={
            "stopOnFailure": False,
            "usePHPIntegrations": True,
            "stage_id": STAGE_ID,
            "stage_name": "New",
            "formId": FORM_ID,
            "formValues": {"Section 1": {}},
        }, headers={**xhr_headers, "Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            token = _find_token_in_response(r.json())
            if token:
                print("Auth token fetched successfully")
                return token
        print(f"Warning: getauthentication lookup returned HTTP {r.status_code}")
    except Exception as e:
        print(f"Warning: getauthentication lookup failed ({e})")

    return None


def fetch_collections(uprn: str, auth_token: str = "") -> list[dict]:
    """Fetch bin collection data from the East Cambs API.

    Returns a list of dicts with 'name' and 'date' keys.
    """
    session = requests.Session()
    session.get(BASE_URL)
    sid = session.cookies["PHPSESSID"]

    fetched = fetch_auth_token(session)
    if fetched:
        auth_token = fetched
    else:
        print("Warning: auth token auto-fetch failed, falling back to stored value")

    today = date.today()
    min_date = today.strftime("%Y-%m-%d")
    max_date = (today + timedelta(days=42)).strftime("%Y-%m-%d")
    print(f"Querying collections from {min_date} to {max_date}")

    payload = {
        "stopOnFailure": True,
        "usePHPIntegrations": True,
        "stage_id": STAGE_ID,
        "stage_name": "New",
        "formId": FORM_ID,
        "formValues": {
            "Section 1": {
                "AuthenticateResponse": {"value": auth_token},
                "uprn": {"value": uprn},
                "selected_uprn": {"value": uprn},
                "selected_uprn_old": {"value": uprn},
                "MinimumDateForNextDates": {"value": min_date},
                "MaximumDateFormattedNext": {"value": max_date},
            }
        },
    }

    api_url = (
        f"{BASE_URL}/apibroker/runLookup"
        f"?id={LOOKUP_ID}&repeat_against=&noRetry=false"
        f"&getOnlyTokens=undefined&log_id="
        f"&app_name=AF-Renderer::Self&sid={sid}"
    )

    resp = session.post(api_url, json=payload, headers={
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    resp.raise_for_status()

    data = resp.json()
    if data.get("status") != "done":
        print(f"Unexpected API response: {json.dumps(data, indent=2)}")
        raise RuntimeError(f"API returned unexpected status: {data.get('status')!r}")

    try:
        select_data = data["integration"]["transformed"]["select_data"]
    except KeyError as e:
        print(f"Unexpected API response: {json.dumps(data, indent=2)}")
        raise RuntimeError(f"Unexpected API response structure (missing key {e})")

    if not select_data:
        print(f"Unexpected API response: {json.dumps(data, indent=2)}")
        raise RuntimeError("API returned 0 collection entries")

    print(f"Found {len(select_data)} upcoming collection(s):")
    collections = []
    for entry in select_data:
        label = entry["label"]  # e.g. "RECYCLING BIN - 240L - 05/06/2026"
        name = entry["value"]   # e.g. "RECYCLING BIN - 240L"
        date_str = label.rsplit(" - ", 1)[-1]
        collection_date = datetime.strptime(date_str, "%d/%m/%Y")
        collections.append({"name": name.title(), "date": collection_date})
        print(f"  {collection_date.strftime('%d/%m/%Y')}: {name.title()}")

    return collections


class Collection:
    def __init__(self, name: str, collection_date: datetime):
        self.type = name
        self.date = collection_date.replace(hour=7, minute=50)

    @property
    def as_ical(self):
        event = Event()
        event.name = self.type
        event.begin = self.date
        event.end = self.date.replace(hour=8, minute=10)
        event.created = arrow.now()
        return event


class CollectionDate:
    def __init__(self, collections: list[Collection]):
        self._collections = collections

    @property
    def date(self):
        return self._collections[0].date

    @property
    def as_ical(self):
        event = Event()
        names = [c.type for c in self._collections]
        if len(names) == 1:
            event.name = names[0]
        elif len(names) == 2:
            event.name = f"{names[0]} and {names[1]}"
        else:
            event.name = ', '.join(names[:-1]) + f" and {names[-1]}"
        event.begin = self.date
        event.end = self.date.replace(hour=8, minute=10)
        event.created = arrow.now()
        return event


def generate_calendar(uprn: str, auth_token: str = "") -> Calendar:
    """Fetch collection data and generate an iCal calendar."""
    raw_collections = fetch_collections(uprn, auth_token)

    collections = [Collection(entry["name"], entry["date"]) for entry in raw_collections]

    def date_reducer(output, collection):
        d = collection.date.date()
        output.setdefault(d, []).append(collection)
        return output

    grouped = reduce(date_reducer, collections, {})
    collection_dates = [CollectionDate(colls) for colls in grouped.values()]

    ical = Calendar()
    for cd in collection_dates:
        ical.events.add(cd.as_ical)

    return ical
