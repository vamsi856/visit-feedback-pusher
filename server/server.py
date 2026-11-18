#!/usr/bin/env python3
"""Visit feedback site – a small server of its own (stdlib only), behind Caddy on its own address.

Opening the private link (/?k=<key>) once sets a session cookie on that device; without it the site shows nothing. Only the key's
SHA-256 is kept on the server (key.sha256). Every action is a JSON POST with the page's token (X-CSRF) from the same origin.
Logic and sending: visits.py. Data: $VISITS_HOME."""
import hashlib, hmac, html, http.server, json, os, re, secrets, sys, threading, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visits as VF

HERE = os.path.dirname(os.path.abspath(__file__))
KEYF, SESSF = os.path.join(VF.DIR, 'key.sha256'), os.path.join(VF.DIR, 'sessions.json')
PORT = int(os.environ.get('VISITS_PORT', '8097'))
SESSION_DAYS = 400                                        # the longest a browser keeps a cookie; renewed on every visit
PAGE = open(os.path.join(HERE, 'page.html'), encoding='utf-8').read()
LOCK = threading.Lock()
FAILS = {}                                                # ip → [count, first] wrong keys, 10 an hour


def sha(s): return hashlib.sha256(s.encode()).hexdigest()


def sessions():
    try:
        with open(SESSF, encoding='utf-8') as f: return json.load(f)
    except (OSError, ValueError): return {}


def new_session():
    tok = secrets.token_urlsafe(32)
    with LOCK:
        s = {k: v for k, v in sessions().items() if v > time.time()}
        s[sha(tok)] = time.time() + SESSION_DAYS * 86400
        VF._write(SESSF, s)
    return tok


def renew(tok):
    """Each visit pushes the sign-in out to a full 400 days again, so a browser in use is never asked twice."""
    now = time.time()
    with LOCK:
        s = sessions(); h = sha(tok)
        if s.get(h, 0) - now < (SESSION_DAYS - 1) * 86400:
            s[h] = now + SESSION_DAYS * 86400; VF._write(SESSF, s)


def cookie(tok):   # Lax: a link opened from mail or chat still arrives signed in; every action also needs the page's token
    return f'vf={tok}; Max-Age={SESSION_DAYS * 86400}; Path=/; HttpOnly; Secure; SameSite=Lax'


def key_ok(k):
    try:
        with open(KEYF, encoding='utf-8') as f: want = f.read().strip()
    except OSError: return False
    return bool(k) and hmac.compare_digest(sha(k), want)


class H(http.server.BaseHTTPRequestHandler):
    server_version = 'visits'
    sys_version = ''

    def log_message(self, fmt, *a):                       # path only, never the query (the key) or a body
        print(f'{self.ip()} {self.command} {self.path.split("?")[0][:80]} {a[1] if len(a) > 1 else ""}', flush=True)

    def ip(self): return (self.headers.get('X-Forwarded-For') or self.client_address[0]).split(',')[-1].strip()

    def tok(self):
        m = re.search(r'(?:^|;\s*)vf=([\w-]{20,})', self.headers.get('Cookie') or '')
        if not m: return None
        exp = sessions().get(sha(m.group(1)))
        return m.group(1) if exp and exp > time.time() else None

    def csrf(self, tok): return hmac.new(tok.encode(), b'csrf', 'sha256').hexdigest()[:32]

    def out(self, code, body, ctype='text/html; charset=utf-8', extra=None, nonce=''):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer'); self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
                         "connect-src 'self'; img-src 'self' data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def locked(self, msg='This browser is not signed in yet. Paste your private link (or just its key) once – after that this browser stays signed in.'):
        return self.out(403, "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>Visit feedback</title>"
                             "<style>body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f6f5f2;color:#1c1b19}main{max-width:520px;margin:48px auto;padding:0 16px}"
                             "input{font:inherit;width:100%;box-sizing:border-box;padding:10px;border:1px solid #ccc;border-radius:8px;min-height:44px;margin:8px 0}"
                             "button{font:inherit;font-weight:600;padding:10px 18px;min-height:44px;border:0;border-radius:8px;background:#1f5f8b;color:#fff}"
                             "@media (prefers-color-scheme:dark){body{background:#141413;color:#ecebe7}input{background:#1d1c1a;color:#ecebe7;border-color:#34322e}}</style>"
                             f"<main><h1 style='font-size:22px'>Visit feedback</h1><p>{html.escape(msg)}</p>"
                             "<form method='get' action='/'><label>Private link or key<input name='k' autocomplete='off' autocapitalize='off' spellcheck='false' required></label>"
                             "<button>Sign in</button></form></main>")

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != '/': return self.out(404, 'Not found', 'text/plain')
        k = urllib.parse.parse_qs(u.query).get('k', [''])[0].strip()
        if 'k=' in k: k = urllib.parse.parse_qs(urllib.parse.urlsplit(k).query).get('k', [''])[0].strip()   # the whole link pasted
        if k:
            f = FAILS.get(self.ip(), [0, time.time()])
            if f[0] >= 10 and time.time() - f[1] < 3600: return self.locked('Too many wrong links – try again in an hour.')
            if not key_ok(k):
                FAILS[self.ip()] = [f[0] + 1 if time.time() - f[1] < 3600 else 1, f[1] if time.time() - f[1] < 3600 else time.time()]
                time.sleep(1); return self.locked('That link is not right.')
            t = new_session()
            return self.out(302, '', 'text/plain', {'Location': '/', 'Set-Cookie': cookie(t)})
        t = self.tok()
        if not t: return self.locked()
        renew(t)
        n = secrets.token_urlsafe(16)
        data = json.dumps({'csrf': self.csrf(t), 'center': 'KNL', 'project': 'Supernova'}).replace('<', '\\u003c')
        return self.out(200, PAGE.replace('__DATA__', data).replace('<script>', f'<script nonce="{n}">'), extra={'Set-Cookie': cookie(t)}, nonce=n)

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n <= 1 << 20 else b''
        J = lambda code, d: self.out(code, json.dumps(d), 'application/json')
        m = re.fullmatch(r'/api/(master|check|send|job|jobs|stop)', self.path)
        if not m: return J(404, {'error': 'Not found.'})
        t = self.tok()
        if not t: return J(403, {'error': 'Open your private link again.'})
        host = (self.headers.get('X-Forwarded-Host') or self.headers.get('Host') or '').split(',')[0].strip()
        local = re.fullmatch(r'(localhost|127\.0\.0\.1)(:\d+)?', host)     # a test on this machine has no HTTPS
        if self.headers.get('Origin') not in (f'https://{host}', f'http://{host}' if local else None, None) or not hmac.compare_digest(self.headers.get('X-CSRF') or '', self.csrf(t)):
            return J(403, {'error': 'This page expired – reload it.'})
        try:
            q = json.loads(body or b'{}')
            if not isinstance(q, dict): raise ValueError
        except ValueError: return J(400, {'error': 'Bad request.'})
        act = m.group(1)
        if act in ('job', 'stop'):
            if act == 'stop': VF.stop(str(q.get('id') or ''))
            j = VF.job(str(q.get('id') or ''))
            return J(200, dict(j, counts=VF.counts(j)) if j else {'error': 'That send was not found.'})
        if act == 'jobs': return J(200, {'jobs': VF.jobs()})
        try:
            if act == 'master':
                rows = VF.master(force=bool(q.get('force')))
                return J(200, {'rows': rows, 'new': VF.new_fos(rows)})
            text = str(q.get('text') or '')[:400_000]
            center, project = str(q.get('center') or '').strip(), str(q.get('project') or '').strip()
            videos = 'No' if q.get('videos') == 'No' else 'Yes'
            visits = [v for v in VF.VISITS if v in (q.get('visits') or [])]
            if not (text.strip() and center and project and visits): return J(200, {'error': 'Choose the center, project and visits, and paste the feedback table.'})
            items, errors = VF.plan(text, center, project, videos, visits)
            if act == 'check': return J(200, {'items': items, 'errors': errors})
            if not any(it['state'] == 'ready' for it in items): return J(200, {'error': 'Nothing ready to send – press Check to see why.'})
            try: gap = int(q.get('gap') or 0)
            except (TypeError, ValueError): gap = 0
            jid = VF.start(items, videos, gap, self.ip(), q.get('hours'))
            print(f'send {jid}: {sum(it["state"] == "ready" for it in items)} rows', flush=True)
            return J(200, {'id': jid})
        except Exception as e:                            # the tracker unreachable or changed: say so in plain words
            print(f'{act}: {type(e).__name__}: {e}', flush=True)
            return J(200, {'error': f'Could not reach the tracker: {e}' if isinstance(e, (OSError, RuntimeError, ValueError)) else 'Something went wrong – try again.'})


def main():
    if sys.argv[1:2] == ['setkey']:                       # setkey <sha256 of the key>: the key itself never reaches this server
        h = (sys.argv[2:3] or [''])[0].strip().lower()
        if not re.fullmatch(r'[0-9a-f]{64}', h): sys.exit('usage: server.py setkey <sha256 hex>')
        VF._write(SESSF, {}); os.makedirs(VF.DIR, exist_ok=True)
        with open(os.open(KEYF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f: f.write(h + '\n')
        print('key set; every signed-in device was signed out'); return
    os.makedirs(VF.DIR, exist_ok=True)
    s = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H)
    s.daemon_threads = True
    print(f'visit feedback on 127.0.0.1:{PORT}', flush=True)
    s.serve_forever()


if __name__ == '__main__':
    main()
