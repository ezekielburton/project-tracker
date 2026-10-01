# Server setup — rebuilding from zero

> ⚠️ KEEP THIS FILE PRIVATE — do not commit to GitHub. Add `Helix Setup.md` to .gitignore.
>
> **When to use this doc:** the server hardware died, or you're building Helix on a brand-new box. If you just need to deploy a code update to a working server, use [DEPLOYMENT.md](DEPLOYMENT.md) instead. All credentials referenced below live in the password manager (OVP entries) — keep it open the whole time.

---

## 0. What you need before you start

- **Hardware:** a mini-PC or equivalent, wired ethernet, with **Ubuntu Server 26.04 LTS** freshly installed (the installer's default choices are fine).
- **Physical access** to the machine (screen + keyboard) for the first boot and network setup.
- **On the office LAN** — the machine must be plugged into the office network (router at Vitamin Dubai).
- **The password manager**, open on your laptop. Every password / key referenced below is in its OVP entries.
- **Router admin access** — to reserve the static IP by MAC address. Get someone from IT if you don't have it.
- **Latest DB backup** from the NAS at `Admin/Database/daily/backup_YYYY-MM-DD.dump` — grab the newest one before starting.
- **A GitHub account** with read access to the private `project-tracker` repo (either an SSH key set up, or a Personal Access Token).
- **On your laptop:** SSH, git, and (for the Cloudflare Zero Trust backup path later) cloudflared installed.

Plan on ~2–3 hours end-to-end for someone who has done Linux server work before. First time, budget half a day.

---

## 1. First boot: hostname, timezone, admin user

At the console:

```bash
sudo hostnamectl set-hostname vitamine
sudo timedatectl set-timezone Asia/Dubai
```

The installer should already have created the admin user. If not:

```bash
sudo adduser helixadmin
sudo usermod -aG sudo helixadmin
```

Password: from vault (`vitaminhelix@2026`). Log out and log back in as `helixadmin` for the rest of this doc.

Then update the system:

```bash
sudo apt update && sudo apt upgrade -y
```

Reboot if the kernel changed.

---

## 2. Reserve the static IP: `10.101.20.149`

This is a **two-part** step. Do both, otherwise you'll get a duplicate-IP conflict on the LAN the first time a Windows laptop connects.

### 2a. On the server (netplan)

Find the primary ethernet interface:

```bash
ip -brief addr show
```

It will look something like `enp3s0` (the exact name depends on the hardware). Note it.

Edit the netplan config:

```bash
sudo nano /etc/netplan/50-cloud-init.yaml
```

Set it to (replace `enp3s0` with your actual interface name):

```yaml
network:
  version: 2
  ethernets:
    enp3s0:
      dhcp4: no
      addresses: [10.101.20.149/23]
      routes:
        - to: default
          via: 10.101.20.1
      nameservers:
        addresses: [1.1.1.1, 4.2.2.2]
```

Apply:

```bash
sudo netplan apply
ip -brief addr show   # confirm 10.101.20.149/23 is on the interface
ping -c 3 1.1.1.1     # confirm internet
```

If SSH drops here, that's expected — reconnect at the new IP.

### 2b. On the router

Log in to the office router. Reserve the server's **MAC address** (get it from `ip link show enp3s0`) → `10.101.20.149`. This stops DHCP ever handing that IP out to any other device.

---

## 3. Install core dependencies

```bash
sudo apt install -y \
  git curl \
  python3 python3-venv python3-pip \
  postgresql postgresql-contrib \
  nginx \
  ufw
```

Versions this doc was written against (newer is fine unless noted):
- Python **3.14.4**
- PostgreSQL **18.6**
- nginx **1.28.3**

---

## 4. PostgreSQL: create the `project_tracker` database

```bash
sudo -u postgres psql
```

Inside psql:

```sql
CREATE ROLE helixadmin WITH LOGIN PASSWORD 'vitaminhelix@2026';
CREATE DATABASE project_tracker OWNER helixadmin;
\q
```

Verify:

```bash
sudo -u postgres psql -c "\l" -c "\du"
```

You should see the `project_tracker` DB owned by `helixadmin`, and a `helixadmin` role listed alongside `postgres`.

---

## 5. Clone the repo and set up the Python environment

```bash
cd /home/helixadmin
git clone git@github.com:<org>/project-tracker.git    # or https + PAT
cd project-tracker
git checkout main

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Note: the venv is always named `venv` (not `.venv`) and lives at `/home/helixadmin/project-tracker/venv/`. The systemd service and cron job both point at this exact path.

---

## 6. Recreate the `.env` file

Copy the full `.env` block from **the password manager's OVP `.env` entry** to `/home/helixadmin/project-tracker/.env` verbatim. It contains:

- `SECRET_KEY` — Flask session/CSRF secret
- `DATABASE_URL` — Postgres connection string. **Important:** the password contains `@`, URL-encoded as `%40`. Do not paste a raw `@` here — the URL parser will break.
- `FLASK_DEBUG`, `FLASK_ENV`, `DEV_TOOLS_ENABLED`
- Mail settings (Resend SMTP)
- NAS settings (host, username, password, project root, web URL)

Lock permissions so only `helixadmin` can read it:

```bash
chmod 600 /home/helixadmin/project-tracker/.env
```

---

## 7. Restore the database from the NAS backup

Get the newest daily backup off the NAS (`Admin/Database/daily/`) onto the server. Quickest path when nothing else is set up yet: SFTP from the NAS.

```bash
# Example — pick the newest date
scp helix@10.101.21.76:/volume1/Admin/Database/daily/backup_YYYY-MM-DD.dump ~/
```

Restore into the empty `project_tracker` DB:

```bash
pg_restore -U helixadmin -d project_tracker --no-owner ~/backup_YYYY-MM-DD.dump
```

Verify a few tables landed:

```bash
psql -U helixadmin -d project_tracker -c "\dt" | head -20
```

**Order matters:** restore the dump **before** running migrations. A fresh dump already contains the schema it was taken against; running migrate.py first would only fight the restore.

---

## 8. Run any missing migrations

Only relevant if the code on `main` is newer than the dump. Otherwise this is a no-op.

```bash
cd ~/project-tracker
source venv/bin/activate
python3 create_tables.py       # creates any missing tables db.create_all() finds
# Then any pending migrations — `migrate.py --status` lists them.
```

---

## 9. Gunicorn + systemd service

Create `/etc/systemd/system/helix.service`:

```bash
sudo nano /etc/systemd/system/helix.service
```

Contents (this is the running production version — copy verbatim):

```ini
[Unit]
Description=VitaminE Helix
After=network.target postgresql.service

[Service]
User=helixadmin
WorkingDirectory=/home/helixadmin/project-tracker
Environment="PATH=/home/helixadmin/project-tracker/venv/bin"
Environment="GEVENT_WORKER=1"
Environment="FLASK_DEBUG=0"
Environment="PYTHONOPTIMIZE=1"
ExecStart=/home/helixadmin/project-tracker/venv/bin/gunicorn -k gevent -w 9 --worker-connections 1000 --graceful-timeout 5 -b 127.0.0.1:5000 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now helix
sudo systemctl status helix
```

You should see `active (running)`. If not:

```bash
sudo journalctl -u helix -n 100 --no-pager
```

Gunicorn version this was written against: **26.0.0** (installed via `requirements.txt`).

---

## 10. NGINX

Create `/etc/nginx/sites-available/helix`:

```bash
sudo nano /etc/nginx/sites-available/helix
```

Contents (running production version — copy verbatim):

```nginx
server {
    listen 80;
    server_name app.vitamin-e.work localhost;
    client_max_body_size 900M;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/javascript application/json image/svg+xml;
    gzip_min_length 1024;

    # Static files — never hits Gunicorn
    location /static {
        alias /home/helixadmin/project-tracker/app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Uploaded files
    location /uploads {
        alias /home/helixadmin/project-tracker/uploads;
    }

    # SSE endpoints — disable buffering so events push instantly
    location /sse/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        keepalive_timeout 3600s;
        chunked_transfer_encoding on;
    }

    # Everything else
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Enable and remove the default site:

```bash
sudo ln -s /etc/nginx/sites-available/helix /etc/nginx/sites-enabled/helix
sudo rm -f /etc/nginx/sites-enabled/default   # important — see note below
sudo nginx -t
sudo systemctl reload nginx
```

**Why remove the default site:** with the default site disabled, our helix server block is the only one listening on port 80, so nginx routes *all* HTTP traffic to it regardless of the Host header. That's why hitting `http://10.101.20.149/`, `http://vitamine/` (Tailscale MagicDNS), or `http://app.vitamin-e.work/` all reach the Flask app even though `server_name` only lists two hostnames. If you re-enable the default site, LAN and Tailscale hits will start returning the nginx welcome page instead of the app.

Verify:

```bash
curl -s http://10.101.20.149/ | head -3
```

Should return a Flask redirect to `/dashboard` (or `/login`).

---

## 11. Cloudflare Tunnel

### 11a. Install cloudflared

```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update
sudo apt install cloudflared -y
cloudflared --version   # should show 2026.x
```

### 11b. Authenticate

```bash
cloudflared tunnel login
```

Opens a browser link. Sign in with `ezekiel@vitamin.works` and pick the `vitamin-e.work` zone. This writes credentials to `~/.cloudflared/cert.pem`.

### 11c. Reuse or recreate the tunnel

The existing tunnel is **`vitamine`** (its ID is in the password manager).

**If you can recover the credentials file** from the old server (`/etc/cloudflared/<tunnel-id>.json`) — from an old backup, a snapshot, anywhere — copy it into `/etc/cloudflared/` on the new server. Same tunnel ID means the existing DNS records at Cloudflare keep pointing right; no DNS changes needed.

**Otherwise, create a new tunnel:**

```bash
sudo cloudflared tunnel create vitamine
```

That creates a fresh tunnel ID and drops the credentials JSON at `~/.cloudflared/<new-tunnel-id>.json`. Move it into `/etc/cloudflared/`:

```bash
sudo mv ~/.cloudflared/*.json /etc/cloudflared/
```

Then re-point the DNS records at Cloudflare (these now target the new tunnel ID):

```bash
sudo cloudflared tunnel route dns vitamine app.vitamin-e.work
sudo cloudflared tunnel route dns vitamine nas.vitamin-e.work
sudo cloudflared tunnel route dns vitamine ssh.vitamin-e.work
```

**Update `the password manager`** with the new tunnel ID before continuing.

### 11d. Config file

Create `/etc/cloudflared/config.yml`:

```bash
sudo nano /etc/cloudflared/config.yml
```

Contents (running production version + SSH backup path added — see step 13):

```yaml
tunnel: vitamine
credentials-file: /etc/cloudflared/<tunnel-id>.json

ingress:
  - hostname: nas.vitamin-e.work
    service: https://10.101.21.76:5001
    originRequest:
      noTLSVerify: true

  - hostname: app.vitamin-e.work
    service: http://localhost:5000

  - hostname: ssh.vitamin-e.work
    service: ssh://localhost:22

  - service: http_status:404
```

Replace `<tunnel-id>` with the actual JSON filename.

### 11e. Install as a service

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared
```

Verify:

```bash
curl -s https://app.vitamin-e.work/ -o /dev/null -w "%{http_code}\n"
```

Should return `302` (Flask redirect) — confirms the tunnel is up and reaching the app.

---

## 12. Tailscale (primary remote access)

Install:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Bring the tunnel up with a fixed hostname so `ssh helixadmin@vitamine` works from any tailnet node (MagicDNS):

```bash
sudo tailscale up --hostname=vitamine --ssh
```

Open the browser link and authenticate with the **Vitamin** tailnet (same tailnet as `hpomen15` and `vitamin-nas`). The `--ssh` flag lets Tailscale act as an SSH gateway (optional but nice — auth via tailnet identity instead of password).

Confirm:

```bash
tailscale ip -4          # note this IP — will be a 100.x.x.x
tailscale status
```

Update **`the password manager` → SSH Access → Tailscale** with the new IP if it differs from the previous one (recorded in the password manager).

Verify from your laptop (also on the tailnet):

```bash
ssh helixadmin@vitamine
```

---

## 13. Cloudflare Zero Trust SSH (backup access)

Already half-configured by step 11d (the `ssh.vitamin-e.work` ingress line). Two more steps to make it actually authenticate:

### 13a. Zero Trust app

Go to [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) → Access → Applications → Add application:

- **Type:** Self-hosted
- **Application name:** `Helix SSH`
- **Session duration:** 24 hours
- **Application domain:** `ssh.vitamin-e.work`

Add a policy:

- **Policy name:** `Ezekiel Access`
- **Action:** Allow
- **Include:** Emails → `ezekiel@vitamin.works` (add other engineers here as needed)

Save. Restart cloudflared to pick up the ingress change:

```bash
sudo systemctl restart cloudflared
```

### 13b. Verify from your laptop

Requires cloudflared installed locally (from `cloudflared.exe` on Windows, or `brew install cloudflare/cloudflare/cloudflared` on Mac). Ensure `~/.ssh/config` has the entry documented in `the password manager`, then:

```bash
ssh ssh.vitamin-e.work
```

A browser opens for Cloudflare Access auth on first use.

This path is **backup only** — day-to-day, Tailscale is faster.

---

## 14. Cron: daily database backup to the NAS

The daily backup runs from `helixadmin`'s crontab and calls `backup_db.py`, which pushes to the NAS using the credentials in `.env`.

```bash
crontab -e
```

Add:

```cron
0 23 * * * cd /home/helixadmin/project-tracker && /home/helixadmin/project-tracker/venv/bin/python backup_db.py >> /var/log/vitamin-backup.log 2>&1
```

Make sure the log file is writable:

```bash
sudo touch /var/log/vitamin-backup.log
sudo chown helixadmin:helixadmin /var/log/vitamin-backup.log
```

Verify tomorrow at 23:00 (Asia/Dubai) that a new dump lands in `Admin/Database/daily/` on the NAS. You can force a run now to sanity-check:

```bash
cd ~/project-tracker && venv/bin/python backup_db.py
```

---

## 15. Firewall (ufw)

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (needed for local LAN + tunnel origin)
sudo ufw enable
sudo ufw status
```

No need to open 5000 (gunicorn binds to `127.0.0.1` only), no need to open 5432 (postgres is localhost-only).

---

## 16. Verification checklist

Run through this end-to-end before calling it done:

- [ ] `systemctl status helix` — active, running
- [ ] `systemctl status nginx` — active, running
- [ ] `systemctl status postgresql` — active, running
- [ ] `systemctl status cloudflared` — active, running
- [ ] `systemctl status tailscaled` — active, running
- [ ] `curl -s http://10.101.20.149/ | head -3` — Flask redirect (LAN works)
- [ ] `curl -s https://app.vitamin-e.work/ -o /dev/null -w "%{http_code}\n"` — `302` (tunnel works)
- [ ] `ssh helixadmin@vitamine` from a tailnet node — works (Tailscale)
- [ ] `ssh ssh.vitamin-e.work` from your laptop — works (Cloudflare SSH backup)
- [ ] Log in to the app in a browser via `https://app.vitamin-e.work` — works
- [ ] Open a project, load its detail page — no errors
- [ ] Upload a file on a project — lands in `~/project-tracker/uploads/`
- [ ] Trigger an action that hits the NAS (create a project reference folder) — folder appears on NAS
- [ ] Wait for 23:00 backup, or run `backup_db.py` manually — dump appears in `Admin/Database/daily/` on NAS

---

## 17. After it's up

- **Update `the password manager`** with anything that changed on this rebuild: Tailscale IP, tunnel ID (if fresh), any new nginx or systemd changes you made.
- **Update `DEPLOYMENT.md`** if you bumped OS version, changed the systemd unit, or altered the nginx config.
- **Rotate credentials** if there's any chance the old machine was compromised: `SECRET_KEY`, `helixadmin` password (server + Postgres), `MAIL_PASSWORD` (Resend), `NAS_PASSWORD`. Update `.env` and the password manager in the same pass.
- **Test the disaster path itself:** the moment this is done, try `ssh ssh.vitamin-e.work` — that's the *backup* path, which almost never gets exercised. Now is the only time it's guaranteed to be tested. If it doesn't work, fix it now.

---

## Known gotchas future-you will hit

1. **`DATABASE_URL` and the `@` in the password.** `postgresql://helixadmin:vitaminhelix@2026@localhost/...` will fail with a cryptic parse error. Always encode `@` as `%40`.
2. **The default nginx site.** If you (or an installer, or an update) re-symlinks `/etc/nginx/sites-enabled/default` back in, LAN IP access silently starts returning the nginx welcome page instead of the app. Delete the symlink; leave the file in `sites-available/` alone.
3. **Interface name is not always `enp3s0`.** Different hardware gets different names (`eno1`, `ens160`, `enp2s0`, whatever). Always confirm with `ip -brief addr show` before editing netplan.
4. **Cloudflare tunnel DNS records live at Cloudflare, not on your server.** If you create a fresh tunnel with a new ID, the DNS CNAMEs at `app.vitamin-e.work`, `nas.vitamin-e.work`, and `ssh.vitamin-e.work` are still pointing at the old tunnel — `cloudflared tunnel route dns` overwrites them.
5. **Static-file caching after a deploy.** Once this box is up and you start deploying updates via `DEPLOYMENT.md`, don't forget the Cloudflare cache purge step whenever anything under `app/static/` changes.
