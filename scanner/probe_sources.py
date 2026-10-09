"""Round 3 (one-off): run the scanner's own web-page reader on each proposed new source and record what it would
pick up (titles, dates). Writes data/probe_report.json. Nothing is added to the pipeline."""
import json, os, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tender_scanner as ts
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "scanner_config.json"), encoding="utf-8"))
P = lambda name, url, client, ctype, **kw: dict(name=name, url=url, source=kw.pop("source", "client site"), client=client,
                                             client_type=ctype, every_minutes=kw.pop("every", 60), enabled=True, **kw)
NEW = [
 P("TRC tenders", "https://www.trc.co.tz/tenders", "Tanzania Railways Corporation (TRC)", "parastatal", about="Railway stations, yards, buildings and civil works"),
 P("TCRA tenders", "https://www.tcra.go.tz/tenders", "Tanzania Communications Regulatory Authority (TCRA)", "government"),
 P("Azania Bank tenders", "https://www.azaniabank.co.tz/tenders", "Azania Bank", "bank", about="Branch fit-outs and refurbishments"),
 P("NBC Bank procurement", "https://www.nbc.co.tz/en/procurement/", "NBC Bank", "bank"),
 P("Ministry of Water tenders", "https://www.maji.go.tz/tenders", "Ministry of Water", "government"),
 P("REA tenders", "https://www.rea.go.tz/category/tenders", "Rural Energy Agency (REA)", "government"),
 P("DART tenders", "https://www.dart.go.tz/publications/tenders", "DART (Dar Rapid Transit Agency)", "government", region="Dar es Salaam"),
 P("TASAC tenders", "https://www.tasac.go.tz/publications/tender", "TASAC", "government"),
 P("TMDA tenders", "https://www.tmda.go.tz/tenders", "Tanzania Medicines and Medical Devices Authority (TMDA)", "government"),
 P("DUWASA tenders", "https://www.duwasa.go.tz/tenders", "DUWASA (Dodoma water)", "parastatal", region="Dodoma"),
 P("MWAUWASA tenders", "https://www.mwauwasa.go.tz/tenders", "MWAUWASA (Mwanza water)", "parastatal", region="Mwanza"),
 P("Ministry of Finance tenders", "https://www.mof.go.tz/pages/tenders", "Ministry of Finance", "government"),
 P("SUA tenders (zabuni)", "https://www.sua.ac.tz/zabuni", "Sokoine University of Agriculture (SUA)", "government", region="Morogoro"),
 P("Tanzania Posts announcements", "https://www.posta.co.tz/sw/announcement/all-announcement/", "Tanzania Posts Corporation", "parastatal"),
 P("TRA public notices", "https://www.tra.go.tz/public-notice/all", "Tanzania Revenue Authority (TRA)", "government"),
 P("UDSM announcements", "https://www.udsm.ac.tz", "University of Dar es Salaam", "government", region="Dar es Salaam"),
 P("TAWA announcements", "https://www.tawa.go.tz/announcements", "Tanzania Wildlife Management Authority (TAWA)", "government"),
 P("Ministry of Health notices", "https://www.moh.go.tz", "Ministry of Health", "government"),
 P("NSSF tenders", "https://www.nssf.go.tz/tenders/general-procurement-notice", "NSSF", "parastatal"),
 P("NM-AIST tenders", "https://www.nm-aist.ac.tz/tenders/all", "NM-AIST", "government", region="Arusha"),
 P("BidDetail – Tanzania tenders", "https://www.biddetail.com/tanzania-tenders", "", "", source="aggregator", every=120),
 P("ZoomTanzania tenders", "https://www.zoomtanzania.net/tenders", "", "", source="aggregator", every=120),
 P("TendersInfo – Tanzania", "https://www.tendersinfo.com/global-tanzania-tenders.php", "", "", source="aggregator", every=120),
 P("TendersInfo – Tanzania construction", "https://www.tendersinfo.com/global-tanzania-construction-tenders.php", "", "", source="aggregator", every=120),
]


def run(a):
    i, pg = a
    t0 = time.time()
    try:
        got = ts.src_webpage(pg, cfg, None, i)
        items = [{"title": g["title"][:160], "deadline": str(g["deadline"] or ""), "no": g["no"], "url": g["source_url"][:160]} for g in got]
        try:
            kept, dropped, _ = ts.analyse([dict(g, _src=pg["name"]) for g in got], ts.datetime.now(), cfg)
            k = [{"title": t["title"][:120], "why": t.get("why", "")[:120]} for t in kept]
            d = [{"title": t["title"][:120], "why": t.get("why", "")[:120]} for t in dropped][:8]
        except Exception as e:
            k, d = [], [{"title": "analyse failed", "why": str(e)[:200]}]
        return {"name": pg["name"], "ok": True, "n": len(got), "items": items[:15], "kept": k[:10], "dropped": d, "sec": round(time.time() - t0, 1)}
    except Exception as e:
        return {"name": pg["name"], "ok": False, "error": str(e)[:200], "sec": round(time.time() - t0, 1)}


if __name__ == "__main__":
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(run, enumerate(NEW)))
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "round": 3, "results": res},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1)
    for r in res:
        print(r["name"], r.get("n"), r.get("error", ""))
