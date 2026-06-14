# NOVM Mini Deployment

This profile is for a tiny NOVM container used as a public demo. It is not meant for real long-term data storage.

## Recommended Limits

- Use `SAKURA_DEMO_MODE=1`.
- Do not import large PDFs.
- Keep only small sample files.
- Keep login enabled.
- Back up data before deleting the instance.

## Server Setup

```bash
apt-get update
apt-get install -y --no-install-recommends nginx-light
cd /tmp
curl -fsSLo get-pip.py https://bootstrap.pypa.io/get-pip.py
python3 get-pip.py --break-system-packages
python3 -m pip install --break-system-packages --ignore-installed --no-cache-dir \
  "typing-extensions>=4.11" "PyMuPDF>=1.24.0" "Pillow>=10.0.0" "openai>=1.0.0"
```

## App Layout

```text
/opt/sakura/app
  app.py
  sakura_*.py
  static/
  data/
```

Create `.env`:

```bash
cat > /opt/sakura/app/.env <<'EOF'
PORT=8000
APP_PUBLIC_URL=https://your-domain.example
SAKURA_ADMIN_PASSWORD=replace-with-a-strong-password
SAKURA_AUTH_SECRET=replace-with-a-long-random-secret
SAKURA_DEMO_MODE=1
REMIND_MORNING_ON=0
REMIND_NIGHT_ON=0
REMIND_WEATHER_ON=0
EOF
```

Start:

```bash
cd /opt/sakura/app
bash scripts/start_sakura.sh
python3 scripts/health_check.py
```

## Nginx Reverse Proxy

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Reload:

```bash
nginx -t
nginx -s reload || nginx
```

## Domain Notes

For NOVM shared IP routing, configure the NOVM domain binding first. If Cloudflare shows `403`, test direct origin routing and then switch Cloudflare between DNS-only and proxied mode.

For a tiny demo, start with Cloudflare DNS-only until HTTP works, then enable proxy if needed.
