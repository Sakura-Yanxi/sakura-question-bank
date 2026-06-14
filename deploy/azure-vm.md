# Azure VM Deployment

This profile is for a more reliable Sakura deployment on Azure for Students.

## Recommended VM

- Ubuntu Server 24.04 LTS
- B1ms for light personal/demo use
- Standard SSD, 30 GB
- Open inbound ports: 22, 80, 443
- Set Azure budget alerts early

## Install Runtime

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip nginx git
sudo python3 -m pip install --break-system-packages --no-cache-dir -r requirements.txt
```

## App Directory

```bash
sudo mkdir -p /opt/sakura/app
sudo chown -R "$USER:$USER" /opt/sakura
cd /opt/sakura/app
```

Copy or clone the project, then create `.env` from `.env.example`.

For a private instance:

```env
SAKURA_DEMO_MODE=0
SAKURA_ADMIN_PASSWORD=replace-with-a-strong-password
SAKURA_AUTH_SECRET=replace-with-a-long-random-secret
APP_PUBLIC_URL=https://your-domain.example
```

Start:

```bash
bash scripts/start_sakura.sh
python3 scripts/health_check.py
```

## Nginx

Use the same reverse proxy pattern as `deploy/novm-mini.md`, then point your domain to the VM public IP.

For HTTPS, use either Cloudflare proxy or Caddy/Nginx with certificates.

## Data Migration

Use Sakura's backup export/import in the web UI. Keep the generated ZIP until you verify:

- documents list
- questions
- page images
- textbooks
- teacher memory
- reflection history

Do not manually copy only the SQLite file unless you also copy `data/uploads` and `data/pages`.
