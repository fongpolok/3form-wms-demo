# 3Form WMS: start, test and troubleshoot (v3.3.0)

## 1. First-time setup (once per computer)

| Step | Command (run in the project folder) |
|---|---|
| Install Docker Desktop and Miniconda | (download from their websites) |
| Create the Python environment | `conda env create -f environment.yml` |
| Create your secrets file | `cp .env.example .env`, then change every `change-me` value |
| Start the databases + create tables | `./scripts/dev_start.sh` |
| Create the demo accounts and 2 sample orders | `conda run -n 3form_WMS python manage.py seed_demo` |
| Load Hong Kong public holidays (planner calendar) | `conda run -n 3form_WMS python manage.py load_holidays` |
| Upgrading from v3.1.0? Run once | `conda run -n 3form_WMS python manage.py migrate && conda run -n 3form_WMS python manage.py upgrade_v32` |
| 3 months of demo history (for pitching) | `conda run -n 3form_WMS python manage.py seed_history` (remove: `--clear`) |

## 2. Every day

```bash
./scripts/dev_start.sh          # start databases, server, scanner gateway
./scripts/dev_start.sh stop     # stop server + gateway
```

- PIC / Engineering Manager: <http://127.0.0.1:8008/login>
- Workstation tablet: <http://127.0.0.1:8008/worker>
- API documentation (for the AI agent / integrators): <http://127.0.0.1:8008/api/docs/>

## 3. Demo accounts

| Role | Log in with | Password |
|---|---|---|
| PIC | username `pic_demo` | `DEMO_PIC_PASSWORD` in `.env` |
| Engineering Manager | username `em_demo` | `DEMO_EM_PASSWORD` in `.env` |
| Worker | staff ID `1001` (also `1002`–`1006`) | none, but the device must be registered |

**Registering a workstation tablet:**
1. Sign in as the PIC **on that tablet**.
2. Go to Devices, type a name, pick the workstation, and press **Register this device**.
3. Log out and open `/worker`.

To register a different tablet from your own computer, press **Register a device** instead. Then type the one-time code into that tablet's worker screen.

## 4. Scanners (Honeywell over TCP/IP)

1. Each scanner is one entry under `scanner_gateway.devices` in `config/settings.yaml`. It holds the IP, port, `mode`, terminator and the workstation it belongs to.
2. `mode: client` means the gateway connects to the scanner (the scanner is set to "TCP server"). `mode: server` means the scanner connects to the gateway.
3. To test without hardware, run `python tools/scanner_simulator.py --port 55256`, then type a barcode and press Enter.
4. A new brand needs a new file in `site_gateway/drivers/` plus one line in `drivers/__init__.py`.

## 4b. Cameras (TCP/IP)

| Camera | What it sends | Settings (`scanner_gateway.devices`) |
|---|---|---|
| Vision (Cognex In-Sight IS8500) | `PASS` or `FAIL,<reason>` + CR LF per inspection | `kind: vision`, `driver: cognex_tcp`, camera as TCP server on port 3000, `workstation: WS-06` |
| Rack camera | `SLOT,<bin>,EMPTY` / `OCCUPIED` / `<goods code>` | `kind: rack`, `driver: rack_tcp`, port 3100 |

- To test without hardware, run `python tools/camera_simulator.py --mode vision --port 3000`. Add `--every 5 --fail-rate 0.1` for automatic results. For the rack camera, use `--mode rack --port 3100`.
- In Cognex In-Sight Explorer, set up a TCP/IP output (the camera acts as server) that writes the line above after each inspection.
- A camera FAIL becomes 1 piece of scrap ("Vision reject") on the batch running at that workstation. A rack mismatch raises an alert and never changes stock.

## 5. Backups and Excel

| What | Command |
|---|---|
| Backup both databases now | `./deploy/backup/backup.sh` (output: `backups/`, kept 30 days) |
| Nightly Excel file | `conda run -n 3form_WMS python manage.py export_production` (output: `exports/`) |
| Restore | see the bottom of `deploy/backup/backup.sh` |
| Re-plan when a machine is stopped > 30 min | `conda run -n 3form_WMS python manage.py aps_watch` (scheduled every 5 min) |
| Expiry alerts + re-check orders waiting for material | `conda run -n 3form_WMS python manage.py daily_checks` (scheduled 06:00) |

**Scheduled every night on this Mac** (installed 2026-10-19 and tested):
```
PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin
0 2 * * * cd "<project>" && PY=<conda env>/bin/python /bin/bash ./deploy/backup/backup.sh >> logs/cron.log 2>&1
5 2 * * * cd "<project>" && <conda env>/bin/python manage.py export_production >> logs/cron.log 2>&1
```
Two macOS details that matter:
- `cron` needs **Full Disk Access** (System Settings → Privacy & Security), because the project is in Desktop.
- Start the script **through `/bin/bash`**. When the script is run directly, macOS blocks Python inside the Desktop folder.
- To see or edit the schedule, use `crontab -l` / `crontab -e`. The output goes to `logs/cron.log`.

## 5b. Planner (APS)

- **Plan page:** the Gantt chart, LATE RISK orders, blocked orders, and drafts to accept or reject.
- **Calendar page:** shifts, breaks, working days, holidays and staffing. Changes apply from the next re-plan.
- **Rules in `config/settings.yaml` → `aps:`:** horizon, changeover, frozen hours, late buffer, workers per station, and whether re-planning is automatic.
- **Holidays:** check gov.hk each year and add the next year to `aps/holidays.py`, then run `load_holidays`.

## 6. Troubleshooting

| You see | Do this |
|---|---|
| Worker screen red: "Cannot reach the server" | Check the tablet's network. Is the server running? (`./scripts/dev_start.sh`) |
| Worker screen red: "Scanner not responding" | Check the scanner's power and cable, and its IP in `settings.yaml`. Then read `logs/scanner.log` |
| "Device not authorised" | The PIC must register this tablet (section 3) |
| "Account locked" | Wait 15 minutes, or the PIC presses Unlock in People |
| Port already in use | Change `MONGO_PORT` / `POSTGRES_PORT` in `.env`. Port 27030 belongs to `fpl-mongo` on this Mac |
| Anything else | Look in `logs/error.log` first, then `logs/app.log` |

## 7. Run the automated tests

```bash
conda run -n 3form_WMS python -m pytest
```
