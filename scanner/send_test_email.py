"""
NORDIC NEXUS – send ONE test tender-alert email (Nordic Construction Company Ltd)
Developed by Eng. Frank and Eng. Michael.

Run it from GitHub: Actions → "Send test email" → Run workflow. It builds the same digest the
scanner sends (newest open Pursue/Check tenders + deadlines within 7 days), marks it [TEST],
and sends it to the addresses you type. Nothing is written to the repository and no alert is
marked as sent. The mailbox password comes only from the GitHub secret SMTP_PASSWORD.
"""
import argparse, json, os, socket, sys
from datetime import datetime
import nexus_alerts as A


def reach(host, port):
    try:
        socket.create_connection((host, port), timeout=10).close(); return "open"
    except Exception as e:
        return f"closed ({e.__class__.__name__})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="comma-separated email addresses")
    ap.add_argument("--mailbox", required=True, help="sending mailbox, e.g. tenders@nordictz.co.tz")
    ap.add_argument("--host", default="mail.nordictz.co.tz")
    ap.add_argument("--port", type=int, default=465)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(A.HERE, "scanner_config.json"), encoding="utf-8"))
    acfg = cfg.setdefault("alerts", {})
    ecfg = acfg.setdefault("email", {})
    ecfg.update({"enabled": True, "method": "smtp", "smtp_user": a.mailbox.strip(), "from": a.mailbox.strip(),
                 "smtp_host": a.host.strip(), "smtp_port": a.port})

    tenders = A.open_tenders(A._abs(cfg.get("workbook_path", "../data/Nordic_Opportunity_Pipeline.xlsx")))
    now = datetime.now()
    new = tenders[-3:][::-1]                                   # newest rows are at the bottom of the Pipeline
    due = sorted([(t, max(1, int((t["deadline"] - now).total_seconds() / 86400 + 0.999))) for t in tenders
                  if isinstance(t["deadline"], datetime) and 0 < (t["deadline"] - now).total_seconds() <= 7 * 86400],
                 key=lambda x: x[1])[:5]
    subject, text, html, _ = A.compose(new, due)
    subject = "[TEST] " + subject
    html = html.replace("<div style='font-family", "<p style='background:#FBEBC0;padding:8px 12px;font-family:Arial;font-size:13px'>"
                        "This is a TEST of the NORDIC NEXUS tender email alerts. No action needed.</p><div style='font-family", 1)
    print(f"Subject: {subject}\nFrom: {a.mailbox} via {a.host}:{a.port}\nOpen tenders read: {len(tenders)} · in digest: {len(new)} new, {len(due)} closing\n")
    print(f"Mail server check: port 465 {reach(a.host, 465)} · port 587 {reach(a.host, 587)}")
    if a.dry_run:
        print("\n" + text); return 0
    if not os.environ.get("SMTP_PASSWORD"):
        print("\nFAILED: the GitHub secret SMTP_PASSWORD is missing. Add it under Settings → Secrets and variables → Actions.")
        return 1
    failed = 0
    for to in [x.strip() for x in a.to.split(",") if x.strip()]:
        try:
            A.send_email(acfg, to, subject, text, html); print(f"SENT   → {to}")
        except Exception as e:
            failed += 1; print(f"FAILED → {to}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
