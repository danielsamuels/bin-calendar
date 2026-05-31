from datetime import date, datetime, timedelta
from functools import reduce

import requests
from ics import Calendar, Event


BASE_URL = "https://eastcambs-self.achieveservice.com"
LOOKUP_ID = "6784e74793b68"
STAGE_ID = "AF-Stage-94ee5097-94db-474d-bc7a-d1796e3ab83a"
FORM_ID = "AF-Form-b10c1e46-e09b-4c18-a31f-b1113609860a"


def fetch_collections(uprn: str, auth_token: str) -> list[dict]:
    """Fetch bin collection data from the East Cambs API.

    Returns a list of dicts with 'name' and 'date' keys.
    """
    session = requests.Session()

    # Establish a PHP session
    session.get(BASE_URL)
    sid = session.cookies["PHPSESSID"]

    today = date.today()
    min_date = today.strftime("%Y-%m-%d")
    max_date = (today + timedelta(days=42)).strftime("%Y-%m-%d")

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

    resp = session.post(api_url, json=payload, headers=headers)
    resp.raise_for_status()

    data = resp.json()
    if data.get("status") != "done":
        raise RuntimeError(f"API returned unexpected status: {data.get('status')}")

    select_data = data["integration"]["transformed"]["select_data"]

    collections = []
    for entry in select_data:
        label = entry["label"]  # e.g. "RECYCLING BIN - 240L - 05/06/2026"
        name = entry["value"]   # e.g. "RECYCLING BIN - 240L"
        # Extract date from the end of the label
        date_str = label.rsplit(" - ", 1)[-1]
        collection_date = datetime.strptime(date_str, "%d/%m/%Y")
        collections.append({"name": name, "date": collection_date})

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
        event.name = ' and '.join(c.type for c in self._collections)
        event.begin = self.date
        event.end = self.date.replace(hour=8, minute=10)
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
