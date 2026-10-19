# 3Form WMS / MES / APS — Project Plan (agreed design)

Status: **Approved** 2026-10-19. Phase 1 (v3.1.0) signed off 2026-10-19. Phase 2 (v3.2.0) signed off 2026-10-19. Phase 3 (v3.3.0) signed off 2026-10-19.
Diagrams in this folder: `01-system-map.html`, `02-production-flow.html`, `03-version-timeline.html`.

---

## 1. What we are building

A **production-scale** factory system for small and medium manufacturers, sold as part of 3Form's AI service:

| Part | Plain meaning |
|---|---|
| **WMS** (existing GreaterWMS, upgraded) | Where every item sits in the warehouse. Stock goes out oldest-first (FIFO). |
| **MES** (new) | What each workstation is doing right now, and what it produced, scrapped or stopped for. |
| **APS** (new) | The plan: which work order runs on which workstation, and when. |
| **AI agent** (new) | Reads all of the above and **gives advice only**. A human clicks Accept. |
| **ERP connectors** (new) | Swap work orders and results with SAP or Oracle. Simulated for now. Workday is used for staff lists only. |

## 2. Agreed decisions

### People and permissions
| Action | PIC | Eng. Manager | Worker |
|---|---|---|---|
| ERP connections, users, settings, device registration | ✅ | ❌ | ❌ |
| Create or release work orders (incl. **Special / Urgent**) | ✅ | ❌ (view) | ❌ |
| Edit process-step templates (routing) | ✅ | ❌ (view) | ❌ |
| Accept or reject the APS plan and agent advice | ✅ | ✅ | ❌ |
| Progress, OEE, SPC dashboards, camera views, scrap trace-back | ✅ | ✅ | ❌ |
| Scan, start, finish, scrap, machine stopped, measurement | ✅ | ✅ | ✅ |
| **Edit WIP or scrap records** (every edit is audited) | ✅ only | ❌ | ❌ |
| Excel export | ✅ | ✅ | ❌ |

- **Logins:** PIC and EM use a username and strong password, logged out after 30 minutes idle. The worker types or scans a **staff ID only**, on a **PIC-registered device only**.
- **Demo accounts:** `pic_demo`, `em_demo`, `worker_demo`.
- **Audit trail:** every change records who, when, the old value and the new value. It can't be deleted.

### Production flow (see `02-production-flow.html`)
1. A work order comes from the **ERP**, or the **PIC types a Special / Urgent order**.
2. The **APS** plans it.
3. Each **MES workstation** step runs. At **every step completion** the worker records good qty, **scrap qty + reason**, machine stop + reason, and a measurement where needed.
4. **QC passes** → into **WMS stock** (FIFO) → client, **or** ship direct to the client (the work order decides). QC fail → scrap, and the batch goes back to the MES.
5. The result goes back to the ERP: good qty, scrap qty, batch IDs.

### Unique IDs (made automatically, printed as barcodes)
`WO-20261019-0001` · `B-20261019-0001` (batch) · `WIP-B-20261019-0001-S03-001` (batch, step 3, unit 1) · plus a hidden random ID on every scan, so nothing is ever counted twice.

### APS planner rules
1. **Sort:** Special/Urgent → due date → client priority → time received.
2. **Fit** into hard limits: machine rate, calendar & shifts, workers available, and whether raw material is in stock.
3. Can't make the due date → **LATE RISK** flag + agent options (overtime, split batch, swap orders).
4. Urgent order → re-plan, but **running batches finish** and the **next 4 h are frozen** (a setting you can change).

### Lean / Six Sigma (DMAIC)
- **Measure (auto):** OEE, first-pass yield, scrap %, DPMO / sigma level, SPC charts.
- **Analyse (agent):** scrap Pareto, 5-Whys, fishbone draft.
- **Improve:** EM accepts the suggestion.
- **Control:** SPC alarm.
- **Scrap reasons:** Spill/overfill, Underfill, Leak/seal fail, Label error, Damaged packaging, Contamination, Machine fault, **Vision reject** (from the camera, automatic), Other. The PIC can edit this list.
- **Visibility:** the worker presses Scrap but sees no totals. The EM and PIC see the full trace-back.

### AI agent
- **Jobs:**
  - **Work order calculation:** materials needed, stock check, expected finish time.
  - **Progress risk:** late, slow or scrap rising.
  - **Stock-take gaps:** counted stock vs system stock.
  - **Low inventory warnings:** against PIC-set minimum stock levels.
- **When it runs:** hourly, on request, and on alarm.
- **Model:** DeepSeek (key provided later). It receives **anonymised totals only**, and each client has a switch to turn it off.
- **With no key:** the same jobs run as plain calculations, and the panel shows "Advisor offline".
- **Limits:** it is read-only and can never write data. Every suggestion and decision is saved and searchable.

### Hardware
- **Scanners:** **Honeywell over TCP/IP**. Each brand has its own swappable driver; each scanner's network address maps to one workstation.
- **Industrial cameras:** the camera runs its own vision (CV). We receive its **pass/fail over TCP/IP** (Cognex IS8500: `PASS` / `FAIL,<reason>`), and a fail is logged as scrap. **Live video is postponed**: the IS8500 firmware is older than 5.6.0, so there's no Web HMI.
- **Warehouse rack camera inspection:** Phase 2, using the same method.
- **Network alarm:** server, scanner or camera silent for 10 s (a setting you can change) → red screen + sound + "Fix it" checklist. Scans queue on the device, and the EM dashboard shows which workstation is down.

### Data
- **PostgreSQL:** WMS stock, users, audit.
- **MongoDB Atlas Local** on `mongodb://localhost:27032` (27030 is already used by `fpl-mongo` on this Mac; the port is a setting in `.env`): MES events, batches, WIP, scrap, downtime, measurements, APS plans, agent advice.
- **Search (decided 2026-10-19):** **keyword (full-text) search only for now**, over scrap/issue notes, downtime notes, work-order text, agent advice and SOP documents. The vector + hybrid index structure is created but **switched off**, and **no local model (bge-m3) is included**. The embedding source (a small local model or an online API) is to be chosen later.
- **Excel export:** one workbook with these sheets, by date range, plus an automatic nightly copy:
  - Work orders
  - Step logs
  - Scrap
  - Downtime
  - Measurements
  - Stock movements
  - Audit trail
- **Backups:** daily, both databases, kept 30 days.

### Look and feel
- 3Form brand: blue `#0050CC`, navy `#001A4A`, light blue `#5B9BF0`, greys.
- Fonts: **Inter** for text, **Source Serif 4** for headings (taken from 3formhk.com), Noto Sans TC for 中文.
- Logos from `Marketing/Logos`. EN / 繁中 switch.
- Apple-HIG-style simplicity.
- The worker page meets **WCAG 2.2 AA**: big buttons and high contrast.
- Industry drop-down: Cosmetics, Food & Beverage, Pharma, Chemicals, Electronics, General. Each loads its default steps, scrap reasons and sign-off rules.

### Deployment
- **Site part** (always in the factory): scanner gateway, video relay, heartbeat, offline queue.
- **Core part:** on a **factory edge box** (main target) **or an Azure / AWS VM**, reached over **VPN + HTTPS**.
- **Docker** packages everything. Development happens on Edward's Mac.
- **Edge box minimum:** x86, 8 cores, 32 GB RAM, 1 TB SSD, 2 network ports.
- **Demo factory:** 1 site, 6 workstations (Mixing, Filling, Capping, Labelling, Packaging, QC), cosmetics industry, 3 months of made-up history. The number of workstations is a setting.

### Engineering rules
- Conda env **`3form_WMS`**.
- **Modular code:** one folder per job.
- **Every setting is tunable** in `config/` (YAML + `.env`). Nothing is hard-coded.
- **Logging:** separate files for app, scanner, camera, aps, agent and audit, kept 90 days.
- **Versioning:** one CHANGELOG entry and one version tag per phase (v3.1.0 to v3.5.0). The timeline diagram is updated each phase.
- **Release:** one `git push` to `fongpolok/3form-wms-demo` after Edward signs off all phases.

## 3. Folder structure (target)

```
WMS_Demo/
├── environment.yml              conda env "3form_WMS"
├── config/                      ALL tunable settings
│   ├── settings.yaml            workstations, alarm timeout, shifts, frozen window, retention…
│   ├── industries/*.yaml        cosmetics, food, pharma… (steps, scrap reasons, sign-off)
│   └── .env.example             DB URLs, DeepSeek key (blank = advisor offline)
├── greaterwms/                  Django project settings (SQLite → PostgreSQL)
├── <existing WMS apps>          goods, stock, binset, asn, dn, cyclecount… (kept, extended)
├── core/                        logging setup, unique-ID generator, Mongo client, config loader
├── accounts/                    roles, staff-ID login, device registry, audit trail
├── mes/                         routing templates, work orders, batches, WIP, step events
├── lean/                        OEE, FPY, DPMO/sigma, SPC, Pareto calculations
├── aps/                         planner engine (sort → fit), urgent re-plan, frozen window
├── agent/                       DeepSeek client, 4 jobs, rule-based fallback, advice store
├── search/                      bge-m3 embeddings, vector + hybrid index setup, SOP ingest
├── erp/                         connector interface + mock SAP / Oracle, Workday staff import
├── reports/                     Excel export + nightly job
├── site_gateway/                separate service (runs in factory)
│   ├── drivers/                 honeywell_tcp.py, vision_camera_tcp.py (add brands here)
│   ├── queue/                   offline store-and-forward
│   └── heartbeat/               health checks → alarm
├── frontend/                    NEW Vue 3 app: /worker  /manager  /pic  /login
├── deploy/
│   ├── docker-compose.dev.yml   Mac: Postgres, Mongo Atlas Local :27030, MediaMTX
│   ├── docker-compose.edge.yml  factory edge box
│   ├── docker-compose.cloud.yml Azure / AWS VM (+ HTTPS proxy, VPN)
│   └── backup/                  daily backup scripts
├── logs/                        app / scanner / camera / aps / agent / audit
├── docs/plan/                   this plan + diagrams;  docs/install/ edge-spec, troubleshooting
├── tests/
└── CHANGELOG.md
```

## 4. Phases — what each delivers and how you check it

| Phase | Version | Delivers | You check it by… |
|---|---|---|---|
| 1 Foundation | v3.1.0 | conda env, config, logging, Postgres + Mongo :27030 in Docker, unique IDs, roles + 3 demo logins, device registry, audit trail, new Vue 3 shell in 3Form look, worker page (WCAG), Honeywell TCP driver + network alarm, basic step logging (start / finish / scrap / stop / measure), Excel export, backups | Log in as each demo user; scan with a Honeywell (or the simulator); pull the network cable and see the alarm; download the Excel file |
| 2 MES + WMS link | v3.2.0 | **new WMS screens for inbound (ASN), outbound (DN), bins, cycle count**; stock-out rule **FEFO when the item has an expiry date, else FIFO** (per-industry setting); routing templates + industry drop-down, batch progress bars (order → steps → stock/client), QC → FIFO stock or ship direct, OEE / SPC / Pareto dashboards, camera video + vision-reject scrap, rack camera alerts, demo factory with 3 months of data | Run a batch end to end and watch the progress bar; trigger a vision reject; see the stock appear in the WMS |
| 3 APS | v3.3.0 | planner (sort → fit), shifts / calendar / workers / machine rate settings, urgent re-plan with frozen window, late-risk flags, EM accept / reject | Add an urgent order and watch the plan change; check that nothing exceeds capacity |
| 4 Agent + search | v3.4.0 | 4 agent jobs, DeepSeek + offline fallback, anonymiser, accept / reject log, keyword search index (vector / hybrid prepared, off), SOP ingest | Ask the agent "why is scrap up on Filling?"; search "leak line 2 last week"; remove the key and check the system still works |
| 5 ERP + release | v3.5.0 | connector interface, mock SAP / Oracle (WO in, results out), Workday staff import, edge + cloud Docker files, install guide, troubleshooting guide | Import a mock ERP order, finish it, and see the result sent back; then you sign off → **git push** |

## 5. Noted for later (not in scope yet)
- Camera live video (needs IS8500 firmware ≥ 5.6.0 for Web HMI, or another stream).
- Stock data: the new ledger (`inventory`) is the source of truth; legacy GreaterWMS stock endpoints are read-only.
- Pick **Azure or AWS** when the first client signs.
- Choose an embedding source to switch on vector / hybrid search (small local model or online API).
- Real SAP / Oracle credentials replace the mocks.
- Digital scale over TCP/IP for fill weight.
- Two-step login for PIC / EM.
- A second site.
