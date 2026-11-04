/* Visit Feedback Pusher — one-click sender.
   Loaded by the "Send feedback" bookmark on the tracker's form page. Reads the rows the
   hosted page put in the URL (#vfp=...), sends each one same-origin, and shows progress
   in a small panel. Sends right away; no scheduled times. Photo, location and video ID
   are left blank, as with the console script. */
(async () => {
  if (window.__vfpRunning) return;
  window.__vfpRunning = true;

  // ---- Panel ----
  const box = document.createElement('div');
  box.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:99999;width:min(420px,calc(100vw - 32px));max-height:60vh;overflow:auto;background:#fff;color:#1a1a1a;border:1px solid #d6d6d6;border-radius:10px;box-shadow:0 8px 30px rgba(0,0,0,.18);font:13px/1.5 system-ui,sans-serif;padding:14px 16px';
  box.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><strong style="font-size:14px">Visit Feedback Pusher</strong><button id="vfp-x" style="border:0;background:none;font-size:18px;cursor:pointer;line-height:1" aria-label="Close">×</button></div><div id="vfp-sum" style="font-weight:600;margin-bottom:6px"></div><div id="vfp-log" style="font-family:ui-monospace,monospace;font-size:12px;white-space:pre-wrap"></div>';
  document.body.appendChild(box);
  const sum = box.querySelector('#vfp-sum');
  const logEl = box.querySelector('#vfp-log');
  box.querySelector('#vfp-x').onclick = () => box.remove();
  const line = (m, c) => { const d = document.createElement('div'); d.textContent = m; if (c) d.style.color = c; logEl.appendChild(d); box.scrollTop = box.scrollHeight; };
  const bad = (m) => line(m, '#b23b3b');
  const stop = (m) => { bad(m); sum.textContent = 'Stopped'; window.__vfpRunning = false; };
  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  // ---- Payload from the hosted page ----
  if (!location.hostname.endsWith('ita.indivillage.com')) return stop('Open the Vendor Visit Tracker form first, then click the bookmark.');
  const m = location.hash.match(/vfp=([A-Za-z0-9_-]+)/);
  if (!m) return stop('No feedback found in this tab. On the Pusher page, paste your table and press "Send now", then click the bookmark in the tab it opens.');
  let D;
  try {
    const b64 = m[1].replace(/-/g, '+').replace(/_/g, '/');
    D = JSON.parse(decodeURIComponent(escape(atob(b64))));
  } catch (e) { return stop('Could not read the feedback in this link. Press "Send now" on the Pusher page again.'); }
  history.replaceState(null, '', location.pathname + location.search); // clicking again won't resend

  // Rows already sent from this browser are skipped, so a double click never double-submits.
  const SENT_KEY = 'vfp-sent';
  let sent = {};
  try { sent = JSON.parse(localStorage.getItem(SENT_KEY) || '{}'); } catch (e) {}
  const keyOf = (r) => [D.center, D.project, r[0], r[1], r[2], r[3]].join('|').toLowerCase();
  const markSent = (r) => { sent[keyOf(r)] = Date.now(); try { localStorage.setItem(SENT_KEY, JSON.stringify(sent)); } catch (e) {} };

  // ---- Wait for the form's own dropdown data ----
  const centerEl = document.getElementById('center');
  if (!centerEl) return stop('Center dropdown not found. Open the form page (index.php) first.');
  for (let i = 0; i < 40 && centerEl.options.length < 2; i++) await wait(500);
  if (centerEl.options.length < 2) return stop('The form did not load its lists. Reload the page and try again.');

  const setSel = (name, value) => {
    const el = document.querySelector('select[name="' + name + '"]');
    if (!el || ![...el.options].some(o => o.value === value)) return false;
    el.value = value;
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  };

  sum.textContent = 'Preparing ' + D.rows.length + ' submissions…';
  if (!setSel('center', D.center)) return stop('Center "' + D.center + '" is not in the form.');
  await wait(600);
  if (!setSel('project_name', D.project)) return stop('Project "' + D.project + '" is not listed for ' + D.center + '.');
  await wait(600);

  // ---- Business list per vendor team: email → exact option text ----
  const bizByEmail = {};
  for (const team of [...new Set(D.rows.map(r => r[0]))]) {
    if (!setSel('vendor_team', team)) { bad('Vendor team "' + team + '" not in the form; its rows are skipped'); continue; }
    await wait(600);
    let n = 0;
    for (const o of document.querySelector('select[name="business_name_email"]').options) {
      const e = o.value.match(/\[([^\]]+)\]/);
      if (e) { bizByEmail[e[1].trim().toLowerCase()] = o.value; n++; }
    }
    line(team + ': ' + n + ' businesses');
  }

  const submitOne = async (vendor, business, visit, feedback) => {
    const fd = new FormData();
    fd.append('center', D.center);
    fd.append('project_name', D.project);
    fd.append('vendor_team', vendor);
    fd.append('business_name_email', business);
    fd.append('visit_type', visit);
    fd.append('videos_checked', D.videos);
    fd.append('video_ref_id', '');
    fd.append('feedback', feedback);
    fd.append('photo', new File([], ''));  // empty file, exactly like the tracker form
    fd.append('location_address', '');
    fd.append('latitude', '');
    fd.append('longitude', '');
    const res = await fetch('/Only_Google_Sheet_Business_Feedback/submit.php', { method: 'POST', body: fd });
    const text = await res.text();
    if (res.status !== 200) throw new Error('status ' + res.status);
    if (/\b(error|failed|invalid)\b/i.test(text.replace(/<[^>]*>/g, ' '))) throw new Error('tracker replied with an error');
  };

  // ---- Send ----
  let ok = 0, fail = 0, skipped = 0;
  const total = D.rows.length;
  const gapMs = Math.max(0, Math.round((D.gap || 0) * 1000));
  for (let i = 0; i < total; i++) {
    const r = D.rows[i];
    const [vendor, email, visit, feedback] = r;
    const tag = '[' + (i + 1) + '/' + total + '] ' + email + ' · ' + visit;
    sum.textContent = 'Sending ' + (i + 1) + ' of ' + total + '… keep this tab open';
    if (sent[keyOf(r)]) { skipped++; line(tag + ' already sent, skipped', '#8a6d00'); continue; }
    const biz = bizByEmail[email.trim().toLowerCase()];
    if (!biz) { fail++; bad(tag + ': business not found on tracker'); continue; }
    try {
      await submitOne(vendor, biz, visit, feedback);
      markSent(r);
      ok++;
      line('✓ ' + tag, '#0d8449');
    } catch (e) {
      fail++;
      bad('✗ ' + tag + ': ' + e.message);
    }
    if (i < total - 1 && gapMs) await wait(gapMs);
  }

  sum.textContent = 'Done: ' + ok + ' sent' + (skipped ? ', ' + skipped + ' already sent' : '') + (fail ? ', ' + fail + ' failed' : '');
  sum.style.color = fail ? '#b23b3b' : '#0d8449';
  window.__vfpRunning = false;
})();
