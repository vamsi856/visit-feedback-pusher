# Visit Feedback Pusher

A static tool for pushing vendor visit feedback to the IndiVillage tracker.

## Usage

1. **One time:** drag the **Send feedback** button on the page to your bookmarks bar.
2. Paste the feedback table (team, collector email, 1st / 2nd / 3rd visit feedback). The page checks every row against the tracker's business list (the same public Google Sheet data the tracker form loads) and opens the tracker form in a new tab with the matched rows. If you turn off **Open tracker automatically**, press **Send now** instead.
3. In the tracker tab, click the **Send feedback** bookmark. It sends each row from the tracker's own page, waiting the gap between rows, and shows progress in a small panel until it says **Done**. The tracker confirms each row with "Data has been saved to your Google Sheet".

Rows whose team or email isn't on the tracker are shown in the preview and left out. Rows already sent from that browser are skipped, so clicking the bookmark twice never double-submits. `send.js` is the code the bookmark runs.

## Fallbacks

- **Push directly from this page.** Sends with `fetch(..., { mode: 'no-cors' })` and follows the run-at times. The tracker doesn't send CORS headers, so the page can't read its reply; a row counts as sent once the request goes out. Check the sheet after using it.
- **Console script.** Copy the script and run it in the tracker tab's browser console. It follows the gap and run-at times.

## Playwright version

`playwright/` has a script that fills the tracker form in a real browser, one row per real visit, from a CSV. It does a dry run by default and only sends with `--submit`. Photo, location and video ID are left blank. See [playwright/README.md](playwright/README.md).
