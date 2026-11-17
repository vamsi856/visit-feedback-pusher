#!/bin/bash
# Installs or updates the visit feedback site on the server (run as root from the folder holding these files).
# Its own user, folder, service and Caddy block – nothing of the portal's is changed. The portal's install keeps importing
# /etc/caddy/sites.d/*.caddy when Caddy accepts it; until its next deploy the import line is added here.
set -euo pipefail
cd "$(dirname "$0")"
id visits >/dev/null 2>&1 || useradd --system --home-dir /var/lib/egocentric-visits --no-create-home --shell /usr/sbin/nologin visits
install -d -m 755 /opt/visit-feedback
install -m 644 server.py visits.py page.html /opt/visit-feedback/
/usr/bin/python3 -m py_compile /opt/visit-feedback/server.py /opt/visit-feedback/visits.py
install -m 644 visits.service /etc/systemd/system/egocentric-visits.service
systemctl daemon-reload
systemctl enable egocentric-visits >/dev/null 2>&1
systemctl restart egocentric-visits

install -d -m 755 /etc/caddy/sites.d
install -m 644 visits.caddy /etc/caddy/sites.d/visits.caddy
cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-visits
grep -q '^import /etc/caddy/sites.d/\*.caddy' /etc/caddy/Caddyfile || printf '\nimport /etc/caddy/sites.d/*.caddy\n' >> /etc/caddy/Caddyfile
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  systemctl reload caddy && echo "site: https://visits.egocentric.duckdns.org"
else
  cp -p /etc/caddy/Caddyfile.before-visits /etc/caddy/Caddyfile; rm -f /etc/caddy/sites.d/visits.caddy
  echo "Caddy refused the site block – put back as it was" >&2; exit 1
fi
