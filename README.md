<div align="center">
  <img src="frontend/public/brand/logo.png" alt="3Form" width="96" />
  <h1>3Form WMS / MES / APS</h1>
  <p>Warehouse · Production · Planning, with an advisory AI agent, for small and medium manufacturers.</p>
</div>

## What it does

| Module | In short |
|---|---|
| **WMS** | Stock by item + lot + bin + expiry; inbound, outbound, bins, cycle count; FEFO (FIFO when no expiry); expired lots never picked |
| **MES** | Work orders, batches and WIP with unique IDs. Workers on registered tablets record start / finish / scrap / machine stop / measurement at every step |
| **Material gate** | Orders reserve their recipe materials, or wait for material (material requests + alerts). They release automatically when stock arrives |
| **APS** | 14-day finite-capacity plan (urgent → due → client priority; machines, shifts, workers, changeovers). Drafts need Engineering Manager approval; urgent orders publish at once. Gantt chart. HK holidays |
| **Lean / Six Sigma** | OEE, first-pass yield, DPMO / sigma, scrap Pareto, SPC with Cpk and alarms |
| **Devices** | Honeywell scanners, Cognex vision (`PASS` / `FAIL,<reason>`) and rack cameras over TCP/IP, through a site gateway with an offline outbox and a network alarm |
| **AI agent** | Advisory only. Four scheduled jobs and a read-only chat. Provider-neutral (default DeepSeek `deepseek-v4-pro`), anonymised, works without AI |
| **Search + SOPs** | Keyword search (English + 中文) over SOPs, notes, orders and advice. SOP library for RAG |
| **ERP** | SAP / Oracle orders in and results out (ERP inbox + outbox), Workday staff import, read-only API keys |
| **Roles** | PIC > Engineering Manager > Worker. Audited changes; only the PIC corrects WIP / scrap |

## Quick start (development, macOS / Linux)

```bash
conda env create -f environment.yml          # Python 3.11 environment "3form_WMS"
cp .env.example .env                          # fill in every value
./scripts/dev_start.sh                        # databases (Docker), server, scanner gateway
conda run -n 3form_WMS python manage.py seed_demo       # demo company + accounts
conda run -n 3form_WMS python manage.py seed_history    # optional: 90 days of demo data
```

Open http://127.0.0.1:8008/login (PIC / Engineering Manager) and http://127.0.0.1:8008/worker (workstation tablet).
Day-to-day operation, demo accounts and troubleshooting: **[docs/install/README.md](docs/install/README.md)**.

## Production

- **Factory edge box** (Ubuntu Server 24.04), or **Azure / AWS VM + factory site gateway over WireGuard**.
- Everything runs in Docker. See **[deploy/README.md](deploy/README.md)**.

## Project documents

- Plan and decisions: [docs/plan/PROJECT_PLAN.md](docs/plan/PROJECT_PLAN.md)
- Diagrams: [system map](docs/plan/01-system-map.html), [production flow](docs/plan/02-production-flow.html), [version timeline](docs/plan/03-version-timeline.html)
- Change history: [CHANGELOG.md](CHANGELOG.md)
- API reference (for integrators and AI tools): `/api/docs/` on a running server

## Tests

```bash
conda run -n 3form_WMS python -m pytest      # needs the development databases running
```

## Licence and credits

Licensed under the **Apache License 2.0** (see [LICENSE](LICENSE)).

This project started from **[GreaterWMS](https://github.com/GreaterWMS/GreaterWMS)** (© GreaterWMS / Singosgu), also under Apache 2.0.
Its Django data models for goods, bins, suppliers and customers are still used. The screens, inventory ledger, MES, APS, AI agent, integrations and deployment are new work by 3Form.
