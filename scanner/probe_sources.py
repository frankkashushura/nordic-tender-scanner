"""Probe candidate Tanzanian tender pages from GitHub's computers (one-off check, writes data/probe_report.json).
For each site: try the known tender-page addresses, and also look on the home page for links about tenders
(tender / zabuni / procurement / manunuzi). Each page is read with the scanner's own reader so the report
shows exactly what the scanner would see. Nothing is added to the pipeline."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tender_scanner as ts

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "scanner_config.json"), encoding="utf-8"))
KW = cfg["keywords"]

C = [  # name, client, type, home, [likely tender paths]
 ("TBA – Tanzania Buildings Agency", "Tanzania Buildings Agency (TBA)", "government", "https://www.tba.go.tz", ["/tenders", "/pages/tenders", "/zabuni"]),
 ("NHC – National Housing Corporation", "National Housing Corporation (NHC)", "parastatal", "https://www.nhc.co.tz", ["/tenders", "/en/tenders", "/procurement"]),
 ("Watumishi Housing (WHC)", "Watumishi Housing Investments", "parastatal", "https://www.whc.go.tz", ["/tenders", "/pages/tenders"]),
 ("DAWASA", "DAWASA", "parastatal", "https://www.dawasa.go.tz", ["/tenders", "/zabuni"]),
 ("TPDC", "TPDC", "parastatal", "https://www.tpdc.co.tz", ["/tenders", "/procurement"]),
 ("TRC – Tanzania Railways Corporation", "Tanzania Railways Corporation (TRC)", "parastatal", "https://www.trc.co.tz", ["/tenders", "/procurement"]),
 ("TANESCO", "TANESCO", "parastatal", "https://www.tanesco.co.tz", ["/procurement/tenders", "/tenders"]),
 ("REA – Rural Energy Agency", "Rural Energy Agency (REA)", "government", "https://www.rea.go.tz", ["/tenders", "/Tenders"]),
 ("TEMESA", "TEMESA", "government", "https://www.temesa.go.tz", ["/tenders"]),
 ("TAMISEMI (PO-RALG)", "PO-RALG (TAMISEMI)", "government", "https://www.tamisemi.go.tz", ["/tenders", "/zabuni"]),
 ("Ministry of Health", "Ministry of Health", "government", "https://www.moh.go.tz", ["/tenders"]),
 ("Ministry of Education", "Ministry of Education, Science and Technology", "government", "https://www.moe.go.tz", ["/en/tenders", "/tenders"]),
 ("Ministry of Works", "Ministry of Works", "government", "https://www.mow.go.tz", ["/tenders"]),
 ("Ministry of Water", "Ministry of Water", "government", "https://www.maji.go.tz", ["/tenders"]),
 ("NSSF", "NSSF", "parastatal", "https://www.nssf.go.tz", ["/tenders", "/procurement"]),
 ("PSSSF", "PSSSF", "parastatal", "https://www.psssf.go.tz", ["/tenders"]),
 ("TRA", "Tanzania Revenue Authority (TRA)", "government", "https://www.tra.go.tz", ["/index.php/tenders", "/tenders"]),
 ("TCAA", "TCAA", "government", "https://www.tcaa.go.tz", ["/tenders"]),
 ("EWURA", "EWURA", "government", "https://www.ewura.go.tz", ["/tenders"]),
 ("TANAPA", "TANAPA", "government", "https://www.tanzaniaparks.go.tz", ["/tenders"]),
 ("NCAA – Ngorongoro", "Ngorongoro Conservation Area Authority", "government", "https://www.ncaa.go.tz", ["/tenders"]),
 ("TFS – Forest Service", "Tanzania Forest Service (TFS)", "government", "https://www.tfs.go.tz", ["/tenders"]),
 ("TASAF", "TASAF", "government", "https://www.tasaf.go.tz", ["/tenders"]),
 ("MSD – Medical Stores", "Medical Stores Department (MSD)", "government", "https://www.msd.go.tz", ["/tenders"]),
 ("TBS", "Tanzania Bureau of Standards", "government", "https://www.tbs.go.tz", ["/tenders"]),
 ("NEMC", "NEMC", "government", "https://www.nemc.or.tz", ["/tenders"]),
 ("TCRA", "TCRA", "government", "https://www.tcra.go.tz", ["/tenders", "/procurement/tenders"]),
 ("LATRA", "LATRA", "government", "https://www.latra.go.tz", ["/tenders"]),
 ("TTCL", "TTCL", "parastatal", "https://www.ttcl.co.tz", ["/tenders"]),
 ("TPC Posta", "Tanzania Posts Corporation", "parastatal", "https://www.posta.co.tz", ["/tenders"]),
 ("ATCL", "Air Tanzania", "parastatal", "https://www.airtanzania.co.tz", ["/tenders"]),
 ("TIC", "Tanzania Investment Centre", "government", "https://www.tic.go.tz", ["/tenders"]),
 ("NIDA", "NIDA", "government", "https://www.nida.go.tz", ["/tenders"]),
 ("TMA", "Tanzania Meteorological Authority", "government", "https://www.meteo.go.tz", ["/tenders"]),
 ("GST – Geological Survey", "Geological Survey of Tanzania", "government", "https://www.gst.go.tz", ["/tenders"]),
 ("UDSM", "University of Dar es Salaam", "university", "https://www.udsm.ac.tz", ["/tenders", "/web/index.php/tenders"]),
 ("UDOM", "University of Dodoma", "university", "https://www.udom.ac.tz", ["/tenders"]),
 ("SUA", "Sokoine University", "university", "https://www.sua.ac.tz", ["/tenders"]),
 ("MUHAS", "MUHAS", "university", "https://www.muhas.ac.tz", ["/tenders"]),
 ("Ardhi University", "Ardhi University", "university", "https://www.aru.ac.tz", ["/tenders"]),
 ("Mzumbe University", "Mzumbe University", "university", "https://www.mzumbe.ac.tz", ["/tenders"]),
 ("NM-AIST", "NM-AIST", "university", "https://www.nm-aist.ac.tz", ["/tenders"]),
 ("DIT", "Dar es Salaam Institute of Technology", "university", "https://www.dit.ac.tz", ["/tenders"]),
 ("Muhimbili National Hospital", "Muhimbili National Hospital", "hospital", "https://www.mnh.or.tz", ["/tenders"]),
 ("Benjamin Mkapa Hospital", "Benjamin Mkapa Hospital", "hospital", "https://www.bmh.or.tz", ["/tenders"]),
 ("KCMC", "KCMC", "hospital", "https://www.kcmc.ac.tz", ["/tenders"]),
 ("NBC Bank", "NBC Bank", "bank", "https://www.nbc.co.tz", ["/en/tenders", "/tenders"]),
 ("TCB Bank", "Tanzania Commercial Bank", "bank", "https://www.tcbbank.co.tz", ["/tenders"]),
 ("Azania Bank", "Azania Bank", "bank", "https://www.azaniabank.co.tz", ["/tenders"]),
 ("TIB Development Bank", "TIB Development Bank", "bank", "https://www.tib.co.tz", ["/tenders"]),
 ("DSE", "Dar es Salaam Stock Exchange", "private", "https://www.dse.co.tz", ["/tenders"]),
 ("Zanzibar ZPPDA", "ZPPDA", "government", "https://www.zppda.go.tz", ["/tenders"]),
 ("Zanzibar ZECO", "ZECO", "parastatal", "https://www.zeco.go.tz", ["/tenders"]),
 ("Dodoma City Council", "Dodoma City Council", "government", "https://www.dodomacc.go.tz", ["/tenders"]),
 ("Dar es Salaam City Council", "Dar es Salaam City Council", "government", "https://www.dcc.go.tz", ["/tenders"]),
 ("Arusha City Council", "Arusha City Council", "government", "https://www.arushacc.go.tz", ["/tenders"]),
 ("Mwanza City Council", "Mwanza City Council", "government", "https://www.mwanzacc.go.tz", ["/tenders"]),
 ("Kinondoni MC", "Kinondoni Municipal Council", "government", "https://www.kinondonimc.go.tz", ["/tenders"]),
 ("Ilala MC", "Ilala Municipal Council", "government", "https://www.ilalamc.go.tz", ["/tenders"]),
 ("Temeke MC", "Temeke Municipal Council", "government", "https://www.temekemc.go.tz", ["/tenders"]),
 ("UNOPS Tanzania (UNGM)", "UN agencies", "donor", "https://www.ungm.org", ["/Public/Notice?Countries=210"]),
 ("GIZ tenders", "GIZ", "donor", "https://www.giz.de", ["/en/workingwithgiz/tenders.html"]),
 ("AfDB procurement", "African Development Bank", "donor", "https://www.afdb.org", ["/en/projects-and-operations/procurement"]),
 ("Aga Khan Foundation TZ", "Aga Khan", "ngo", "https://www.akdn.org", ["/where-we-work/eastern-africa/tanzania"]),
 ("Tanzania Daily News tenders", "various", "aggregator", "https://dailynews.co.tz", ["/category/tenders", "/tenders"]),
 ("The Citizen tenders", "various", "aggregator", "https://www.thecitizen.co.tz", ["/tanzania/tenders"]),
 ("Ajira / Zoom Tanzania tenders", "various", "aggregator", "https://www.zoomtanzania.net", ["/tenders"]),
 ("Tenders Info Tanzania", "various", "aggregator", "https://www.tendersinfo.com", ["/global-tanzania-tenders.php"]),
 ("Global Tenders Tanzania", "various", "aggregator", "https://www.globaltenders.com", ["/government-tenders-tanzania.htm"]),
 ("TendersOnTime Tanzania", "various", "aggregator", "https://www.tendersontime.com", ["/tanzania-tenders/"]),
 ("BidDetail Tanzania", "various", "aggregator", "https://www.biddetail.com", ["/tanzania-tenders"]),
 ("Tenders Tanzania (tenders.co.tz)", "various", "aggregator", "https://www.tenders.co.tz", ["/"]),
]
LINK = re.compile(r"(tender|zabuni|procure|manunuzi|bids?\b|invitation)", re.I)


class Links(ts.HTMLParser):
    def __init__(self):
        super().__init__(); self.links, self._a = [], None
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._a = [dict(attrs).get("href") or "", ""]
    def handle_data(self, d):
        if self._a is not None:
            self._a[1] += d
    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.links.append(tuple(self._a)); self._a = None


def read(url):
    t0 = time.time()
    try:
        page = ts.http(url, tries=1, timeout=25)
    except Exception as e:
        return {"url": url, "ok": False, "error": str(e)[:160], "sec": round(time.time() - t0, 1)}
    p = ts.Blocks(); p.feed(page)
    tenderish, cons, samples = 0, 0, []
    for tag, text, href in p.blocks:
        tl = text.lower()
        if ts.has_any(tl, KW["tender_words"]) or ts.TENDER_NO.search(text):
            tenderish += 1
            if ts.categorise(tl, cfg) is not None:
                cons += 1
                if len(samples) < 4 and text not in samples:
                    samples.append(text[:160])
    return {"url": url, "ok": True, "bytes": len(page), "blocks": len(p.blocks), "tenderish": tenderish,
            "construction": cons, "samples": samples, "sec": round(time.time() - t0, 1), "_page": page}


def probe(c):
    name, client, ctype, home, paths = c
    tried, best = [], None
    for u in [home.rstrip("/") + p for p in paths]:
        r = read(u); r.pop("_page", None); tried.append(r)
        if r.get("ok") and r.get("tenderish", 0) >= 2:
            best = r; break
    if not best:
        h = read(home)
        page = h.pop("_page", None); tried.append(h)
        if page:
            L = Links(); L.feed(page)
            cand = []
            for href, text in L.links:
                if href and (LINK.search(href) or LINK.search(text)) and not href.startswith(("mailto:", "javascript:", "#")):
                    u = urljoin(home + "/", href)
                    if u not in cand and u.split("/")[2].endswith(home.split("/")[2].replace("www.", "")):
                        cand.append(u)
            for u in cand[:4]:
                r = read(u); r.pop("_page", None); tried.append(r)
                if r.get("ok") and (best is None or r.get("tenderish", 0) > best.get("tenderish", 0)):
                    best = r
    return {"name": name, "client": client, "client_type": ctype, "home": home, "best": best, "tried": tried}


if __name__ == "__main__":
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(probe, C))
    os.makedirs(os.path.join(HERE, "..", "data"), exist_ok=True)
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "results": res},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1)
    for r in res:
        b = r["best"] or {}
        print(f"{r['name'][:38]:38} {'OK ' if b.get('ok') else '-- '} tenderish={b.get('tenderish', 0):3} cons={b.get('construction', 0):3} {b.get('url', '')}")
