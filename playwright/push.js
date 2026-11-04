#!/usr/bin/env node
// Fills the Vendor / Project Visit Form once per row of a CSV of real visit feedback.
// Dry run by default (fills + screenshots, never submits). Add --submit to really send.
// Live photo, location and video reference ID are left blank on purpose (manager's instruction).

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { parse } = require('csv-parse/sync');
const { chromium } = require('playwright');

const VISIT_TYPES = ['1st Visit', '2nd Visit', '3rd Visit', 'Business off'];
const YES_NO = ['Yes', 'No'];
const REQUIRED = ['center', 'project_name', 'vendor_team', 'business_name_email', 'visit_type', 'videos_checked', 'feedback'];
const DONE_FILE = path.join(__dirname, 'done.json');
const SHOTS_DIR = path.join(__dirname, 'screenshots');

function args() {
  const a = process.argv.slice(2);
  const opt = { csv: null, submit: false, headed: false, url: process.env.FORM_URL || '', delay: 3000 };
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--submit') opt.submit = true;
    else if (a[i] === '--headed') opt.headed = true;
    else if (a[i] === '--url') opt.url = a[++i];
    else if (a[i] === '--delay') opt.delay = Number(a[++i]) * 1000;
    else if (!opt.csv) opt.csv = a[i];
  }
  if (!opt.csv || !opt.url) {
    console.error('Usage: node push.js <feedback.csv> --url <form url> [--submit] [--headed] [--delay seconds]');
    console.error('       (or set FORM_URL instead of --url)');
    process.exit(1);
  }
  return opt;
}

function loadDone() {
  try { return JSON.parse(fs.readFileSync(DONE_FILE, 'utf8')); } catch { return {}; }
}

function rowKey(r) {
  return crypto.createHash('sha1')
    .update(REQUIRED.map(k => r[k].trim().toLowerCase()).join('|'))
    .digest('hex').slice(0, 16);
}

function checkRow(r) {
  const missing = REQUIRED.filter(k => !r[k] || !r[k].trim());
  if (missing.length) return `missing ${missing.join(', ')}`;
  if (!VISIT_TYPES.includes(r.visit_type.trim())) return `visit_type must be one of: ${VISIT_TYPES.join(', ')}`;
  if (!YES_NO.includes(r.videos_checked.trim())) return 'videos_checked must be Yes or No';
  return null;
}

// Waits for a dropdown to be enabled and filled, then picks the option.
// Exact text first; otherwise a single case-insensitive partial match (e.g. just the email).
async function pick(page, selector, wanted) {
  await page.waitForFunction(sel => {
    const el = document.querySelector(sel);
    return el && !el.disabled && el.options.length > 1;
  }, selector, { timeout: 15000 });
  const options = await page.$$eval(`${selector} option`, os => os.map(o => o.value).filter(Boolean));
  const w = wanted.trim();
  let value = options.find(o => o === w);
  if (!value) {
    const hits = options.filter(o => o.toLowerCase().includes(w.toLowerCase()));
    if (hits.length === 1) value = hits[0];
    else throw new Error(`"${w}" not found in ${selector}. Options: ${options.join(' | ')}`);
  }
  await page.selectOption(selector, value);
  return value;
}

async function fillRow(page, url, r) {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#visitForm', { state: 'visible', timeout: 30000 });
  const used = {
    center: await pick(page, '#center', r.center),
    project: await pick(page, '#project_name', r.project_name),
    vendor: await pick(page, '#vendor_team', r.vendor_team),
    business: await pick(page, '#business_name_email', r.business_name_email),
  };
  await page.selectOption('select[name="visit_type"]', r.visit_type.trim());
  await page.selectOption('select[name="videos_checked"]', r.videos_checked.trim());
  await page.fill('textarea[name="feedback"]', r.feedback.trim());
  return used;
}

async function main() {
  const opt = args();
  const rows = parse(fs.readFileSync(opt.csv, 'utf8'), { columns: h => h.map(c => c.trim().toLowerCase()), skip_empty_lines: true, bom: true });
  const done = loadDone();
  fs.mkdirSync(SHOTS_DIR, { recursive: true });

  console.log(`${rows.length} rows, mode: ${opt.submit ? 'SUBMIT' : 'dry run (nothing is sent)'}`);
  const browser = await chromium.launch({ headless: !opt.headed });
  const page = await browser.newPage();
  const tally = { sent: 0, checked: 0, skipped: 0, failed: 0 };

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const n = i + 2; // spreadsheet row number (header is row 1)
    const bad = checkRow(r);
    if (bad) { console.log(`row ${n}: SKIP, ${bad}`); tally.failed++; continue; }
    const key = rowKey(r);
    if (done[key]) { console.log(`row ${n}: already sent ${done[key].at}, skipping`); tally.skipped++; continue; }

    try {
      const used = await fillRow(page, opt.url, r);
      await page.screenshot({ path: path.join(SHOTS_DIR, `row-${n}-filled.png`), fullPage: true });

      if (!opt.submit) {
        console.log(`row ${n}: filled OK (${used.center} / ${used.project} / ${used.business})`);
        tally.checked++;
        continue;
      }

      await Promise.all([
        page.waitForNavigation({ timeout: 60000 }),
        page.click('#submitBtn'),
      ]);
      const text = (await page.innerText('body')).trim();
      await page.screenshot({ path: path.join(SHOTS_DIR, `row-${n}-result.png`), fullPage: true });
      if (/error|fail|invalid/i.test(text)) throw new Error(`form replied: ${text.slice(0, 200)}`);

      done[key] = { at: new Date().toISOString(), row: n, business: used.business, reply: text.slice(0, 200) };
      fs.writeFileSync(DONE_FILE, JSON.stringify(done, null, 2));
      console.log(`row ${n}: SENT (${used.business})`);
      tally.sent++;
      await page.waitForTimeout(opt.delay);
    } catch (e) {
      console.log(`row ${n}: FAILED, ${e.message}`);
      tally.failed++;
    }
  }

  await browser.close();
  console.log(`\nDone. sent ${tally.sent}, filled-only ${tally.checked}, already sent ${tally.skipped}, failed ${tally.failed}`);
  console.log(`Screenshots: ${SHOTS_DIR}`);
  if (tally.failed) process.exitCode = 1;
}

main().catch(e => { console.error(e); process.exit(1); });
