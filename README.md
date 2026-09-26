# NORDIC NEXUS – Tender Scanner (cloud)

Nordic Construction Company Ltd · developed by Eng. Frank & Eng. Michael

Scans Tanzanian public tender sources (NeST, World Bank, AfDB, DDO Tenders, TANROADS, TARURA,
TPA, RUWASA, Bank of Tanzania, TEITI, CRDB) every 5 minutes on GitHub Actions, screens them for
Nordic's building and civil works (Pursue / Check / Drop) and keeps the list in
`data/Nordic_Opportunity_Pipeline.xlsx`. NORDIC NEXUS copies new tenders from here every hour.

* `scanner/` – the scanner, its settings (`scanner_config.json`) and status (`last_scan.txt`, `logs/`)
* `data/` – the tender pipeline workbook and source test results
* `.github/workflows/` – the 5-minute schedule and the "Test all sources" check

Only public tender notices are stored here. Staff contacts and alert keys are GitHub **Secrets**
(Settings → Secrets and variables → Actions) and are never written to this repository:
`RECIPIENTS_JSON`, `SMTP_PASSWORD`, `BEEM_API_KEY`, `BEEM_SECRET_KEY`, `WHATSAPP_TOKEN`.
Bid decisions, notes and finance stay in NORDIC NEXUS.
