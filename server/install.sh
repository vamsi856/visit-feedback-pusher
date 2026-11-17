#!/bin/bash
# Installs or updates the visit feedback site on its own server (run as root from the folder holding these files):
#   bash install.sh <site address>       e.g. bash install.sh visits.2-28-66-226.sslip.io
# The first run also sets the machine up: web server (Caddy, its own HTTPS certificate), firewall, key-only SSH, automatic
# security updates. Later runs only update the app. The address is kept in /etc/visit-feedback/site.
set -euo pipefail
cd "$(dirname "$0")"
install -d -m 755 /etc/visit-feedback
[ -n "${1:-}" ] && echo "$1" > /etc/visit-feedback/site
SITE=$(tr -d ' \n' < /etc/visit-feedback/site)
[[ "$SITE" =~ ^[a-z0-9.-]+$ ]] || { echo "usage: bash install.sh <site address>" >&2; exit 1; }

if [ ! -f /var/lib/visit-feedback.setup ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -y -q caddy ufw fail2ban unattended-upgrades >/dev/null
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' > /etc/ssh/sshd_config.d/90-visit-feedback.conf
  systemctl reload ssh
  ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null; ufw --force enable >/dev/null
  printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades
  # updates install, but nothing is restarted under a send in progress
  install -d /etc/needrestart/conf.d && echo "\$nrconf{restart} = 'l';" > /etc/needrestart/conf.d/90-visit-feedback.conf
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
  touch /var/lib/visit-feedback.setup
fi

id visits >/dev/null 2>&1 || useradd --system --home-dir /var/lib/egocentric-visits --no-create-home --shell /usr/sbin/nologin visits
install -d -m 755 /opt/visit-feedback
install -m 644 server.py visits.py page.html /opt/visit-feedback/
/usr/bin/python3 -m py_compile /opt/visit-feedback/server.py /opt/visit-feedback/visits.py
install -m 644 visits.service /etc/systemd/system/egocentric-visits.service
systemctl daemon-reload
systemctl enable egocentric-visits >/dev/null 2>&1
systemctl restart egocentric-visits

sed "s/__SITE__/$SITE/" visits.caddy > /etc/caddy/Caddyfile.new
if caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile >/dev/null 2>&1; then
  mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile; systemctl reload caddy || systemctl restart caddy
  echo "site: https://$SITE"
else
  rm -f /etc/caddy/Caddyfile.new; echo "Caddy refused the site block – web settings left as they were" >&2; exit 1
fi
