# Visit Feedback Pusher

A static tool for pushing vendor visit feedback to the IndiVillage tracker.

## Usage

Open the hosted page and paste the feedback table (team, collector email, 1st / 2nd / 3rd visit feedback). With **Push automatically** on, the page:

1. Checks every row against the tracker's business list (the same public Google Sheet data the tracker form loads), matching team and collector email.
2. Counts down 5 seconds (click **Cancel** to stop), then submits each matched row straight to the tracker, following the gap and any scheduled visit times.
3. Remembers which rows it has sent from this browser, so pasting the same table again skips them.

Rows whose team or email isn't on the tracker are listed in the preview and skipped. Keep the page open until the status says **Done**.

## How it submits

The tracker doesn't send CORS headers, so the page submits with `fetch(..., { mode: 'no-cors' })`. The request reaches the tracker, but the browser hides the response, so a row is marked sent once the request goes out without a network error. Check the tracker sheet after your first push.

## Fallbacks

If direct submission ever stops working, the **Fallback** section on the page has two other ways to send from the tracker's own tab, where the browser allows it:

- **One-click bookmark.** Drag the **Send feedback** button to your bookmarks bar once. Press **Send now** (the tracker form opens with your rows) and click the bookmark in that tab. It sends every row straight away, shows progress in a small panel, and skips rows that browser already sent. Scheduled times are ignored. `send.js` is the code the bookmark runs.
- **Console script.** Copy the script and run it in the tracker tab's browser console. It follows the gap and scheduled times.

## Playwright version

`playwright/` has a script that fills the tracker form in a real browser, one row per real visit, from a CSV. It does a dry run by default and only sends with `--submit`. Photo, location and video ID are left blank. See [playwright/README.md](playwright/README.md).
