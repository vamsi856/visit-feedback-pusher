"""Visit feedback: the owner's vendor-visit reports, sent to the tracker form (ita.indivillage.com) from this server.

The owner pastes the feedback they gave (team, collector email, 1st / 2nd / 3rd visit feedback); the server matches every row to the
tracker's own lists and sends it exactly as the live form does (its fields read before every send) – video reference ID left blank
(the owner's manager's instruction), expected hours for the day 5 unless the owner sets it. Nothing is written or reworded here: the feedback text goes as typed.

A send runs as its own process (`visits.py run <job>`), so a restart of the site never cuts it off. A row counts as sent only when
the tracker answers that the data was saved to its Google Sheet; every such row is kept in sent.jsonl and never sent again.
Files under $VISITS_HOME (mode 600)."""
import hashlib, http.cookiejar, json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid

DIR = os.path.expanduser(os.environ.get('VISITS_HOME', '~/.visit-feedback'))
SENT = os.path.join(DIR, 'sent.jsonl')
BASE = 'https://ita.indivillage.com/Only_Google_Sheet_Business_Feedback/'
FORM, SUBMIT = BASE + 'index.php', BASE + 'submit.php'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
VISITS = ('1st Visit', '2nd Visit', '3rd Visit')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+')
SAVED = re.compile(r'saved to (your )?google sheet', re.I)          # the tracker's own answer: "Data has been saved to your Google Sheet"
TRIES, GAP_MAX = 4, 120


def _write(path, obj):
    os.makedirs(DIR, exist_ok=True)
    tmp = f'{path}.{os.getpid()}.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as f: json.dump(obj, f)
    os.replace(tmp, path)


def _opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'en-IN,en;q=0.9')]
    return op


# ---------------- the tracker's lists (center → project → vendor team → business [email]) ----------------
_cache = {'t': 0, 'rows': None}
def master(force=False):
    """Every business the tracker form offers, as the form builds its dropdowns (same field names, same option text)."""
    if not force and _cache['rows'] is not None and time.time() - _cache['t'] < 600: return _cache['rows']
    op = _opener()
    page = op.open(FORM, timeout=30).read().decode('utf-8', 'replace')
    m = re.search(r"SCRIPT_URL\s*=\s*['\"](https://script\.google\.com/[^'\"]+)['\"]", page)
    if not m: raise RuntimeError('The tracker form changed: the address of its lists was not found on the page.')
    data = json.loads(op.open(f'{m.group(1)}?nocache={int(time.time() * 1000)}', timeout=60).read().decode('utf-8', 'replace'))
    if isinstance(data, dict) and data.get('error'): raise RuntimeError('The tracker answered: ' + str(data['error'])[:200])
    raw = data.get('data', data) if isinstance(data, dict) else data
    rows, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict): continue
        g = lambda *ks: next((str(r[k]) for k in ks if r.get(k) not in (None, '')), '')
        center, project, vendor = g('center'), g('project name', 'project_name'), g('vendor management team', 'vendor_team')
        business, email = g('businees', 'business', 'business name'), g('emails', 'email')
        option = f'{business} [{email}]' if business and email else business or g('business name (email)')
        if not email:
            e = re.search(r'\[([^\]]+)\]', option)
            email = e.group(1) if e else ''
        if not (center and project and vendor and option): continue
        k = (center, project, vendor, option)
        if k in seen: continue
        seen.add(k)
        rows.append({'center': center, 'project': project, 'vendor': vendor, 'business': business or option, 'email': email.strip(), 'option': option})
    if not rows: raise RuntimeError('The tracker sent no businesses.')
    _cache.update(t=time.time(), rows=rows)
    return rows


NEW_DAYS = 3
def new_fos(rows):
    """Field officers (center|project|team) the tracker added lately: each one's first Fetch is kept in fos_seen.json, and an FO
    first seen in the last 3 days counts as new. The very first Fetch only takes note – nothing is new then."""
    path = os.path.join(DIR, 'fos_seen.json')
    try:
        with open(path, encoding='utf-8') as f: seen = json.load(f)
    except (OSError, ValueError): seen = {}
    now, first = time.time(), not seen
    for r in rows: seen.setdefault('|'.join((r['center'], r['project'], r['vendor'])), 0 if first else now)
    _write(path, seen)
    return sorted(k for k, t in seen.items() if t and now - t < NEW_DAYS * 86400)


# ---------------- the pasted table ----------------
def parse(text):
    """Team, collector email, 1st / 2nd / 3rd visit feedback – tab-separated (straight from a sheet), or split by | or 2+ spaces.
    With a header row the columns are found by name (Vendor Team / FO, 1st / 2nd / 3rd visit …), so extra columns such as Center,
    Project or Business may come first. Without one: the first cell before the email is the team, the three after it the feedback.
    A row without a team takes the one above it. Lines without an email (headers, notes) are skipped."""
    out, errors, team, cols = [], [], '', None
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip() or re.fullmatch(r'\s*\|?[\s:|-]+\|?\s*', line): continue
        if '\t' in line: cells = line.split('\t')
        elif '|' in line: cells = line.strip().strip('|').split('|')
        else: cells = re.split(r' {2,}', line)
        cells = [c.strip() for c in cells]
        at = next((i for i, c in enumerate(cells) if EMAIL.fullmatch(c)), None)
        if at is None:
            if EMAIL.search(line): errors.append(f'Line {ln}: the email is not in a cell of its own.')
            elif any(re.search(r'e-?mail', c, re.I) for c in cells):          # a header row: remember where things are
                find = lambda pat: next((i for i, c in enumerate(cells) if re.search(pat, c, re.I)), None)
                cols = {'team': find(r'vendor|team|\bfo\b|field officer'),
                        'v': [find(r'\b(1st|first)\b'), find(r'\b(2nd|second)\b'), find(r'\b(3rd|third)\b')]}
            continue
        get = lambda i: cells[i] if i is not None and i < len(cells) else ''
        if cols and cols['team'] is not None: team = get(cols['team']) or team
        else: team = next((c for c in cells[:at] if c), team)
        if not team: errors.append(f'Line {ln}: no vendor team before {cells[at]}.'); continue
        fb = [get(i) for i in cols['v']] if cols and any(i is not None for i in cols['v']) else (cells[at + 1:] + ['', '', ''])[:3]
        out.append({'line': ln, 'team': team, 'email': cells[at], 'feedback': fb})
    return out, errors


def plan(text, center, project, videos, visits):
    """Each submission the table makes, matched to the tracker's own option – or why it can't be sent."""
    rows, errors = parse(text)
    norm = lambda s: re.sub(r'\s+', ' ', s or '').strip().lower()
    here = [r for r in master() if norm(r['center']) == norm(center) and norm(r['project']) == norm(project)]
    if not here: errors.insert(0, f'The tracker has no project "{project}" at center "{center}". Press Fetch to see what it has.')
    by_email = {}
    for r in here: by_email.setdefault(norm(r['email']), []).append(r)
    sent = sent_keys()
    items = []
    for r in rows:
        hits = by_email.get(norm(r['email']), [])
        pick = [h for h in hits if norm(h['vendor']) == norm(r['team'])] or (hits if len(hits) == 1 else [])
        for i, visit in enumerate(VISITS):
            fb = r['feedback'][i]
            if visit not in visits or not fb: continue
            it = {'line': r['line'], 'team': r['team'], 'email': r['email'], 'visit': visit, 'feedback': fb, 'state': 'ready', 'note': ''}
            if not pick:
                it.update(state='problem', note='not in the tracker under this team' if hits else 'email not in the tracker for this project')
            else:
                h = pick[0]
                it.update(center=h['center'], project=h['project'], vendor=h['vendor'], option=h['option'])
                if h['vendor'] != r['team'] and norm(h['vendor']) != norm(r['team']): it['note'] = f"team in the tracker: {h['vendor']}"
                if key(it, videos) in sent: it.update(state='done', note='already sent before')
            items.append(it)
    return items, errors


def key(it, videos):
    return hashlib.sha256('|'.join([it['center'], it['project'], it['vendor'], it['option'], it['visit'], videos, it['feedback']]).encode()).hexdigest()[:24]


def sent_keys():
    try:
        with open(SENT, encoding='utf-8') as f: return {json.loads(l)['key'] for l in f if l.strip()}
    except (OSError, ValueError, KeyError): return set()


# ---------------- jobs ----------------
def job_path(jid): return os.path.join(DIR, f'job-{jid}.json')


def hours_text(h):
    """Expected hours for the day as the form takes it (0–24, steps of 0.5); 5 when not given."""
    try: x = float(h)
    except (TypeError, ValueError): x = 5.0
    x = round(max(0.0, min(24.0, x)) * 2) / 2
    return str(int(x)) if x == int(x) else str(x)


def start(items, videos, gap, who, hours='5'):
    """Save the job and run it in a process of its own; returns its id."""
    jid = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
    todo = [dict(it, state='waiting') if it['state'] == 'ready' else it for it in items]
    _write(job_path(jid), {'id': jid, 'by': who, 'created': time.time(), 'videos': videos, 'gap': max(0, min(GAP_MAX, int(gap))),
                           'hours': hours_text(hours), 'state': 'starting', 'items': todo})
    log = open(os.path.join(DIR, f'job-{jid}.log'), 'ab')
    subprocess.Popen([sys.executable, os.path.abspath(__file__), 'run', jid], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True, cwd=os.path.dirname(os.path.abspath(__file__)))
    return jid


def job(jid):
    if not re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}', jid or ''): return None
    try:
        with open(job_path(jid), encoding='utf-8') as f: j = json.load(f)
    except (OSError, ValueError): return None
    if j['state'] in ('starting', 'sending') and time.time() - j.get('beat', j['created']) > 300:
        j['state'] = 'stopped'; j['why'] = 'the sender stopped unexpectedly – press Send again; rows already sent are skipped'
    return j


def jobs(n=8):
    try: names = sorted((f for f in os.listdir(DIR) if f.startswith('job-') and f.endswith('.json')), reverse=True)[:n]
    except OSError: return []
    out = []
    for f in names:
        j = job(f[4:-5])
        if j: out.append({'id': j['id'], 'created': j['created'], 'state': j['state'], 'counts': counts(j)})
    return out


def counts(j):
    c = {}
    for it in j['items']: c[it['state']] = c.get(it['state'], 0) + 1
    return c


def stop(jid):
    if job(jid): open(job_path(jid) + '.stop', 'w').close()


# The form as it was on 17 Nov 2026 (POST, urlencoded) – used only when the live page can't be read
FALLBACK_FORM = (False, [('center', 'select', ''), ('project_name', 'select', ''), ('vendor_team', 'select', ''), ('business_name_email', 'select', ''),
                         ('visit_type', 'select', ''), ('videos_checked', 'select', ''), ('video_ref_id', 'text', ''), ('feedback', 'textarea', ''),
                         ('expected_hours', 'number', '')])


def form_spec(page):
    """The tracker form's fields in page order, as a browser would send them: (multipart?, [(name, type, default value)])."""
    m = re.search(r'(?is)<form\b[^>]*id=["\']visitForm["\'][^>]*>.*?</form>', page) or re.search(r'(?is)<form\b[^>]*>.*?</form>', page)
    if not m: raise ValueError('no form on the page')
    multipart = 'multipart/form-data' in re.match(r'(?is)<form\b[^>]*>', m.group(0)).group(0).lower()
    fields = []
    for f in re.finditer(r'(?is)<(input|select|textarea)\b([^>]*)>', m.group(0)):
        a = f.group(2)
        n = re.search(r'\bname=["\']([^"\']+)', a)
        if not n: continue
        t = f.group(1).lower()
        if t == 'input': t = (re.search(r'\btype=["\']([^"\']+)', a) or [None, 'text'])[1].lower()
        if t in ('submit', 'button', 'image', 'reset'): continue
        v = re.search(r'\bvalue=["\']([^"\']*)', a)
        fields.append((n.group(1), t, v.group(1) if v and t in ('hidden', 'text', 'number') else ''))
    if not any(n == 'feedback' for n, _, _ in fields): raise ValueError('the form has no feedback field')
    return multipart, fields


def _submit(op, it, videos, hours, spec):
    """One submission, field for field as the live tracker form sends it (its order, its encoding; a file field goes empty)."""
    multipart, fields = spec
    val = {'center': it['center'], 'project_name': it['project'], 'vendor_team': it['vendor'], 'business_name_email': it['option'],
           'visit_type': it['visit'], 'videos_checked': videos, 'video_ref_id': '', 'feedback': it['feedback'], 'expected_hours': hours,
           'location_address': '', 'latitude': '', 'longitude': ''}
    if multipart:
        b = '----WebKitFormBoundary' + uuid.uuid4().hex[:16]
        body = b''
        for n, t, d in fields:
            if t == 'file': body += f'--{b}\r\nContent-Disposition: form-data; name="{n}"; filename=""\r\nContent-Type: application/octet-stream\r\n\r\n\r\n'.encode()
            else: body += f'--{b}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{val.get(n, d)}\r\n'.encode()
        body += f'--{b}--\r\n'.encode()
        ctype = f'multipart/form-data; boundary={b}'
    else:
        body = urllib.parse.urlencode([(n, val.get(n, d)) for n, t, d in fields if t != 'file']).encode()
        ctype = 'application/x-www-form-urlencoded'
    rq = urllib.request.Request(SUBMIT, data=body, method='POST', headers={
        'Content-Type': ctype, 'Origin': 'https://ita.indivillage.com', 'Referer': FORM})
    with op.open(rq, timeout=90) as r:
        text = r.read(200_000).decode('utf-8', 'replace')
        return r.status, re.sub(r'\s+', ' ', re.sub(r'(?s)<(script|style)\b.*?</\1>|<[^>]+>', ' ', text)).strip()


def run(jid):
    """The sender: one row at a time, the gap between them, up to 4 tries a row; the job file is rewritten after every row."""
    j = job(jid)
    if not j: return
    import fcntl
    lock = open(os.path.join(DIR, 'send.lock'), 'w')
    j['state'] = 'queued'; j['beat'] = time.time(); _write(job_path(jid), j)
    while True:                                           # one sender at a time; a second job waits its turn
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
        except OSError: j['beat'] = time.time(); _write(job_path(jid), j); time.sleep(5)
    op = _opener()
    try:                                                  # the form's own cookies first, as a person opening it would get – and its fields as they are today
        spec = form_spec(op.open(FORM, timeout=30).read().decode('utf-8', 'replace'))
    except (OSError, urllib.error.URLError, ValueError) as e:
        spec = FALLBACK_FORM; print(f'form not read ({e}) – sending the 17 Nov 2026 fields', flush=True)
    j['form'] = [n for n, _, _ in spec[1]]
    j['state'] = 'sending'
    sent = sent_keys()
    first = True
    for it in j['items']:
        if it['state'] != 'waiting': continue
        if os.path.exists(job_path(jid) + '.stop'): break
        k = key(it, j['videos'])
        if k in sent: it.update(state='done', note='already sent before'); continue
        if not first and j['gap']: time.sleep(j['gap'])
        first = False
        it['state'] = 'sending'; j['beat'] = time.time(); _write(job_path(jid), j)
        for t in range(TRIES):
            try:
                code, reply = _submit(op, it, j['videos'], j.get('hours', '5'), spec)
                if code == 200 and SAVED.search(reply):
                    it.update(state='sent', note='', reply=reply[:160], at=time.time())
                    with open(os.open(SENT, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'a', encoding='utf-8') as f:
                        f.write(json.dumps({'key': k, 'at': time.time(), 'job': jid, 'email': it['email'], 'visit': it['visit']}) + '\n')
                    sent.add(k)
                    break
                if code == 200:                           # answered, but not "saved": never sent again blindly (it may be in the sheet)
                    it.update(state='unconfirmed', note='the tracker did not say it was saved – look in the sheet', reply=reply[:160]); break
                it.update(state='failed', note=f'tracker answered {code}', reply=reply[:160])
            except urllib.error.HTTPError as e:
                it.update(state='failed', note=f'tracker answered {e.code}', reply='')
            except TimeoutError:                          # sent, but no answer in time: it may be saved – sending again could double it
                it.update(state='unconfirmed', note='no answer in time – look in the sheet before sending it again'); break
            except (OSError, urllib.error.URLError) as e:
                it.update(state='failed', note=f'could not reach the tracker ({type(e).__name__})')
            if t < TRIES - 1: time.sleep((5, 15, 45)[t])
        j['beat'] = time.time(); _write(job_path(jid), j)
    stopped = os.path.exists(job_path(jid) + '.stop')
    for it in j['items']:
        if stopped and it['state'] == 'waiting': it.update(state='skipped', note='stopped before sending')
    j['state'] = 'stopped' if stopped else 'done'; j['ended'] = time.time(); j['beat'] = time.time()
    _write(job_path(jid), j)


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == 'run':
    run(sys.argv[2])
