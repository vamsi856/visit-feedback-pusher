# Visit Feedback Pusher

A static tool for pushing vendor visit feedback to the IndiVillage tracker.

## Usage

Open the hosted page, paste the feedback table, review the parsed rows, set timing if needed, then copy the generated script and run it in the tracker tab's browser console.

## Why the console paste?

Browsers block cross-origin POST requests to the tracker's endpoint. Running the script in the tracker's own console puts the fetch on the same origin, which the browser allows.

## Playwright version

`playwright/` has a script that fills the tracker form in a real browser, one row per real visit, from a CSV. It does a dry run by default and only sends with `--submit`. Photo, location and video ID are left blank. See [playwright/README.md](playwright/README.md).
