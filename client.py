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


def _search_for_auth_token(obj) -> str | None:
    """Recursively search a parsed JSON structure for an AuthenticateResponse value."""
    if isinstance(obj, dict):
        if obj.get("name") == "AuthenticateResponse" and "value" in obj:
            return obj["value"]
        if "AuthenticateResponse" in obj:
            val = obj["AuthenticateResponse"]
            if isinstance(val, dict) and "value" in val:
                return val["value"]
            if isinstance(val, str):
                return val
        for v in obj.values():
            result = _search_for_auth_token(v)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _search_for_auth_token(item)
            if result:
                return result
    return None


def fetch_auth_token(session: requests.Session) -> str | None:
    """Attempt to fetch the auth token from the East Cambs form definition.

    The token is a static API key embedded in the form definition JSON.
    Returns None if it cannot be fetched automatically.
    """
    candidate_urls = [
        f"{BASE_URL}/api/published/{PROCESS_ID}/{STAGE_ID}/definition.json",
        f"{BASE_URL}/AchieveForms/api/published/{PROCESS_ID}/{STAGE_ID}/definition.json",
        f"{BASE_URL}/apibroker/getdefinition?id={LOOKUP_ID}",
    ]

    for url in candidate_urls:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                token = _search_for_auth_token(data)
                if token:
                    print(f"Auto-fetched auth token from: {url}")
                    return token
                else:
                    print(f"Fetched {url} (200 OK) but no AuthenticateResponse found in response")
        except Exception as e:
            print(f"Could not fetch {url}: {e}")

    return None


def fetch_collections(uprn: str, auth_token: str) -> list[dict]:
    """Fetch bin collection data from the East Cambs API.

    Returns a list of dicts with 'name' and 'date' keys.
    """
    session = requests.Session()

    # Establish a PHP session
    print("Establishing PHP session...")
    session.get(BASE_URL)
    sid = session.cookies["PHPSESSID"]
    print(f"Session established (sid={sid[:8]}...)")

    # Try to auto-fetch the token in case the provided one has expired
    fetched_token = fetch_auth_token(session)
    if fetched_token:
        auth_token = fetched_token
    else:
        print("Using provided AUTH_TOKEN (auto-fetch not available)")

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

    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    print("Posting to API...")
    resp = session.post(api_url, json=payload, headers=headers)
    print(f"API response: HTTP {resp.status_code}")
    resp.raise_for_status()

    data = resp.json()
    status = data.get("status")
    print(f"API status: {status}")

    if status != "done":
        print(f"Full API response: {json.dumps(data, indent=2)}")
        raise RuntimeError(f"API returned unexpected status: {status!r}")

    try:
        select_data = data["integration"]["transformed"]["select_data"]
    except KeyError as e:
        print(f"Full API response: {json.dumps(data, indent=2)}")
        raise RuntimeError(f"Unexpected API response structure (missing key {e})")

    print(f"Raw entries returned: {len(select_data)}")

    if not select_data:
        print(f"Full API response: {json.dumps(data, indent=2)}")
        raise RuntimeError(
            "API returned 0 collection entries. The AUTH_TOKEN has likely expired — "
            "see README.md for instructions on obtaining a fresh token."
        )

    collections = []
    for entry in select_data:
        label = entry["label"]  # e.g. "RECYCLING BIN - 240L - 05/06/2026"
        name = entry["value"]   # e.g. "RECYCLING BIN - 240L"
        # Extract date from the end of the label
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


def generate_calendar(uprn: str, auth_token: str) -> Calendar:
    """Fetch collection data and generate an iCal calendar."""
    raw_collections = fetch_collections(uprn, auth_token)

    collections = [
        Collection(entry["name"], entry["date"])
        for entry in raw_collections
    ]

    # Group by date
    def date_reducer(output, collection):
        d = collection.date.date()
        if d not in output:
            output[d] = [collection]
        else:
            output[d].append(collection)
        return output

    grouped = reduce(date_reducer, collections, {})
    collection_dates = [CollectionDate(colls) for colls in grouped.values()]

    ical = Calendar()
    for cd in collection_dates:
        ical.events.add(cd.as_ical)

    return ical
