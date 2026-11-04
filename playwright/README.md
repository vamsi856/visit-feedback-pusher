# visit-feedback-pusher

Fills the Vendor / Project Visit Form once for every row of a CSV, using Playwright.
Each row is a real visit and the feedback that was actually given. The script only types it in.

Live photo, location and video reference ID are left blank (per manager's instruction).

## Setup (once)

Install Node.js LTS from https://nodejs.org, then:

```bash
npm install
npm run setup
```

## Fill in your visits

Copy `feedback.example.csv` to `feedback.csv` and add one row per visit:

| column | what goes in it |
|---|---|
| center | exactly as in the Center dropdown |
| project_name | exactly as in the Project dropdown |
| vendor_team | exactly as in the Vendor Team dropdown |
| business_name_email | the business name or just its email (must match one option) |
| visit_type | `1st Visit`, `2nd Visit`, `3rd Visit` or `Business off` |
| videos_checked | `Yes` or `No` |
| feedback | the feedback you gave |

`feedback.csv`, `done.json` and `screenshots/` are git-ignored, so business names and emails never reach GitHub.

## Run

The form address is passed in, not stored in the repo.

Dry run first. It fills every row and saves a screenshot, but sends nothing:

```bash
node push.js feedback.csv --url "<form url>"
```

Check `screenshots/`, then send for real:

```bash
node push.js feedback.csv --url "<form url>" --submit
```

- Add `--headed` to watch the browser.
- Rows already sent are recorded in `done.json` and skipped next time, so a re-run never double-submits.
- A row whose dropdown value isn't found fails with the list of valid options, and nothing is sent for it.
