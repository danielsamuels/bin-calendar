# Bin Calendar

Generates an `.ics` (iCalendar) file from the East Cambridgeshire District Council bin collection schedule. Subscribe to the calendar in your favourite calendar app to get reminders about upcoming collections.

## How it works

The tool queries the East Cambs "AchieveService" API to fetch upcoming bin collection dates for a given property (identified by UPRN), then generates an iCalendar file with events for each collection day.

Collections on the same date are merged into a single event (e.g. "RECYCLING BIN - 240L and OUTDOOR FOOD CADDY"). Events are set to 07:50–08:10 as a morning reminder to put the bins out.

Output is deterministic: event UIDs are derived from the collection date, `DTSTAMP` is pinned to the event start, and events are sorted by date. Regenerating from unchanged collection data produces a byte-identical file, so calendar clients update events in place rather than treating every refresh as a delete-and-recreate.

## Setup

### Requirements

- Python 3.10+
- Dependencies: `pip install -r requirements.txt`

### Environment variables

| Variable | Description |
|----------|-------------|
| `UPRN` | The Unique Property Reference Number for your address (e.g. `100090047336`) |
| `AUTH_TOKEN` | API authentication token (see below) |
| `OUTPUT_FILENAME` | (Optional) Output file path. Defaults to `bin-calendar.ics` |

### Finding your UPRN

1. Go to the [East Cambs bin collection page](https://eastcambs-self.achieveservice.com/AchieveForms/?mode=fill&consentMessage=yes&form_uri=sandbox-publish://AF-Process-2c7575a6-0139-4555-9d8a-ab504a44d989/AF-Stage-94ee5097-94db-474d-bc7a-d1796e3ab83a/definition.json&process=1&process_uri=sandbox-processes://AF-Process-2c7575a6-0139-4555-9d8a-ab504a44d989&process_id=AF-Process-2c7575a6-0139-4555-9d8a-ab504a44d989)
2. Enter your postcode and select your address
3. Open browser DevTools (F12) → Network tab
4. Look for the `runLookup` request — your UPRN is in the `formValues.Section 1.uprn.value` field of the POST body

Alternatively, search for your address on [FindMyAddress.co.uk](https://www.findmyaddress.co.uk/).

### Finding the auth token

The auth token is embedded in the form definition on the East Cambs website. To obtain it:

1. Open the bin collection page (link above) with DevTools Network tab open
2. Enter your postcode and select your address
3. Find the `runLookup` POST request in the Network tab
4. In the request body, look for `formValues["Section 1"].AuthenticateResponse.value`

This token appears to be a static API key shared across all users of the form.

## Usage

### Generate locally

```bash
export UPRN="100090047336"
export AUTH_TOKEN="your_token_here"
python3 generate_ics.py
```

### Deploy via GitHub Actions

The included workflow (`.github/workflows/build.yml`) runs every 5 days and on push to `master`. It generates the calendar and deploys it to GitHub Pages.

Configure these repository secrets in the `bin-calendar` environment:

- `UPRN` — Your property's UPRN
- `AUTH_TOKEN` — The API authentication token

The deployed calendar is served as `index.html` (with `text/calendar` content) at your GitHub Pages URL. Subscribe to this URL in your calendar app.

#### Keeping the schedule alive

GitHub automatically disables scheduled workflows in public repositories after 60 days with no repository activity. To avoid that, the workflow commits the generated calendar back to the repo as `bin-calendar.ics`, which counts as activity and resets the timer.

Because the output is deterministic, a commit only happens when the collection dates actually change. If nothing has changed and the last commit is more than 45 days old, an empty keepalive commit is pushed instead. The job needs `permissions: contents: write`; pushes made with `GITHUB_TOKEN` don't trigger workflows, so this doesn't cause a run loop despite the `push` trigger.

### AWS Lambda

The `lambda_function.py` provides a Lambda handler that returns the calendar as an HTTP response. Set the `UPRN` and `AUTH_TOKEN` environment variables in your Lambda configuration.

## API details

The East Cambs bin collection service uses the AchieveService platform. The data flow is:

1. **Establish session** — `GET https://eastcambs-self.achieveservice.com/` to obtain a `PHPSESSID` cookie
2. **Query collections** — `POST https://eastcambs-self.achieveservice.com/apibroker/runLookup?id=6784e74793b68&...&sid={PHPSESSID}` with a JSON body containing the auth token, UPRN, and date range

The response contains collection data in `integration.transformed.select_data` — an array of objects with:
- `label`: Display string (e.g. `"RECYCLING BIN - 240L - 05/06/2026"`)
- `value`: Bin type (e.g. `"RECYCLING BIN - 240L"`)

The date range defaults to today + 42 days (6 weeks) of upcoming collections.
