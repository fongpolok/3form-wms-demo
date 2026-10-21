# Deploying 3Form WMS (v3.5.0)

There are two ways to run it in a factory. Both use the same Docker image (`Dockerfile` at the project root).

| | A. Edge box (recommended) | B. Cloud VM + factory site box |
|---|---|---|
| Where the system runs | One box in the factory | Azure / AWS VM; a small box in the factory runs only the gateway |
| Internet down | Factory keeps working | Gateway queues scans; screens need the internet to reach the VM |
| Files | `docker-compose.edge.yml` | `docker-compose.cloud.yml` + `site/docker-compose.site.yml` |
| HTTPS | Caddy, internal or company certificate | Caddy, automatic Let's Encrypt certificate |
| Scanners / cameras → core | Docker network | WireGuard VPN (port 8008 listens only on the VPN) |

**Minimum hardware:**
- **Edge box:** x86, 8 cores, 32 GB RAM, 1 TB SSD, 2 network ports.
- **Cloud VM:** 4 vCPU, 16 GB RAM, 256 GB disk.
- **Site box (B):** any small x86 PC with 4 GB RAM.

---

## A. Edge box (Ubuntu Server 24.04 LTS)

1. Install Ubuntu Server 24.04 LTS and give the box a fixed IP on the factory network. Add a name in your DNS or router, e.g. `wms.factory.local`.
2. Copy this project onto the box, e.g. `git clone` into `/opt/3form-wms`.
3. Run `sudo ./deploy/install_edge.sh`. It installs Docker and creates `deploy/.env` with fresh random secrets.
4. Edit `deploy/.env`: set `SITE_ADDRESS`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to the box's name.
5. Run `sudo ./deploy/install_edge.sh` again. It builds and starts: databases, app, scheduler, gateway and HTTPS.
6. Create the first PIC with the command the script prints (`create_pic`). Sign in at `https://wms.factory.local/login`.
7. **HTTPS certificate:**
   - **Simplest:** Caddy's internal certificate (`tls internal`). Install Caddy's root certificate on each tablet once. It's inside the `caddydata` volume at `pki/authorities/local/root.crt`.
   - **Company certificate:** put `cert.pem` + `key.pem` in `deploy/certs/` and switch the `tls` line in `deploy/caddy/Caddyfile.edge`.
8. **Scanners and cameras:** list them in `config/settings.yaml` → `scanner_gateway.devices` with their LAN IPs. Then run `docker compose ... restart gateway`.

## B. Cloud VM (Azure first) + factory site box

### B1. Azure VM, step by step
1. Azure Portal → **Create a resource → Virtual machine**:
   - **Region:** *East Asia* (Hong Kong).
   - **Image:** *Ubuntu Server 24.04 LTS*.
   - **Size:** e.g. *Standard_D4s_v5* (4 vCPU, 16 GB).
   - **Authentication:** SSH public key.
   - **OS disk:** Premium SSD, 256 GB.
2. **Networking → Network security group, inbound rules:**
   - `22/tcp` from **your office IP only**
   - `80/tcp` and `443/tcp` from anywhere (HTTPS and certificate renewal)
   - `51820/udp` from the **factory's public IP** (WireGuard)

   Do **not** open 5432, 27017 or 8008.
3. Give the VM a static public IP. Point a DNS name at it (`wms.client.com` → VM IP).
4. SSH in, copy the project to `/opt/3form-wms`, and run `sudo ./deploy/install_edge.sh cloud`. Edit `deploy/.env` (`SITE_ADDRESS`, `ACME_EMAIL`, hosts), then run it again.
5. **WireGuard** on the VM:
   - `sudo apt install wireguard`
   - create keys (see `deploy/wireguard/wg-core.conf.example`)
   - `sudo systemctl enable --now wg-quick@wg0`
6. Create the first PIC (`create_pic`) and sign in at `https://wms.client.com/login`.
7. **Backups:** the scheduler writes daily backups into the `backups` volume. Also turn on **Azure Backup** for the VM disk, and copy `deploy/.env` somewhere safe.

### B2. Factory site box
1. Install Ubuntu Server 24.04 LTS, then `sudo apt install docker.io docker-compose-v2 wireguard`.
2. Set up WireGuard from `deploy/wireguard/wg-site.conf.example` and start it. `ping 10.20.0.1` must work.
3. Run `cp deploy/site/site.env.example deploy/site/.env` and set `GATEWAY_TOKEN` to **the same value as on the VM**.
4. Run `docker compose --env-file deploy/site/.env -f deploy/site/docker-compose.site.yml up -d --build`.
5. Tablets open `https://wms.client.com/worker`. The PIC registers each tablet once (Devices page).

### Appendix: AWS instead of Azure
- **Region:** *Asia Pacific (Hong Kong) ap-east-1*. It's an opt-in region: enable it under Account → Regions first.
- **EC2:** *Ubuntu Server 24.04 LTS*, e.g. *m6i.xlarge*, gp3 256 GB, plus an **Elastic IP**.
- **Security group:** the same rules as the Azure NSG above.
- **Backups:** EBS snapshots (Data Lifecycle Manager) in addition to the daily backups.
- Everything else (install script, WireGuard, site box) is identical.

---

## C. Public website demo (free hosting)

Only for the public demo at demo.3formhk.com. It wipes all data every day.

| Piece | Free service | Setting |
|---|---|---|
| App | Render web service (Docker, root `Dockerfile`), Singapore | start command `/app/deploy/entrypoint.sh demo` |
| PostgreSQL | Neon, AWS Singapore | `POSTGRES_HOST/DB/USER/PASSWORD`, `POSTGRES_PORT=5432`, `POSTGRES_SSLMODE=require` |
| MongoDB | Atlas free cluster, AWS Singapore | `MONGO_URI=mongodb+srv://...` (Network Access: 0.0.0.0/0) |

Other variables: `PUBLIC_DEMO=1`, `SECRET_KEY`, `INTEGRATION_KEY`, `GATEWAY_TOKEN`, `ALLOWED_HOSTS`,
`DJANGO_BEHIND_PROXY=True`, `CSRF_TRUSTED_ORIGINS`, `WEB_WORKERS=2`, and `DEEPSEEK_API_KEY` (optional; capped at 30 calls a day).
The free app sleeps after 15 minutes without visitors and takes about a minute to wake.

## Running it

| Task | Command (from the project folder on the box) |
|---|---|
| Status | `docker compose --env-file deploy/.env -f deploy/docker-compose.edge.yml ps` |
| Logs | `... logs -f app` (also the `logs` volume: app, scanner, camera, aps, agent, audit) |
| Update to a new version | `git pull && sudo ./deploy/install_edge.sh` (rebuilds; database changes run automatically) |
| Backup now | `... exec app python manage.py backup_databases` |
| Restore MongoDB | `... exec app python manage.py restore_mongo backups/<folder> --yes` |
| Restore PostgreSQL | `... exec -T postgres pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean < postgres.dump` |
| Demo data (pitch box only) | `... exec app python manage.py seed_demo && ... seed_history` |
| New year's holidays | Add the year to `aps/holidays.py` (from gov.hk), redeploy, run `load_holidays` |

The **scheduler** container runs the jobs in `config/settings.yaml → scheduler.jobs`:
- backup 02:00
- Excel export 02:05
- daily checks 06:00
- planner watch every 5 minutes
- agent hourly, and every 5 minutes after alarms
- ERP sync every 5 minutes

## Security checklist before go-live
- [ ] Every value in `deploy/.env` is filled, random and backed up. `DJANGO_DEBUG=False`.
- [ ] Only ports 80/443 (+ 51820/udp in the cloud) are reachable from outside.
- [ ] Demo accounts are **not** created on client systems (don't run `seed_demo`).
- [ ] The PIC has registered each workstation tablet. Old tablets are revoked.
- [ ] The AI provider key is entered in Settings → Integrations (or AI is switched off). The anonymisation rule is confirmed.
- [ ] ERP connections are tested with the client's IT, and the field mapping is checked (`config/settings.yaml → erp`).
