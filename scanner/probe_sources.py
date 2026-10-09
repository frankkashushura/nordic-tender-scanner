"""Probe candidate Tanzanian tender pages from GitHub's computers (one-off check, writes data/probe_report.json).
Round 2: for sites whose home page loads, list the menu links about tenders and try the common tender-page
addresses used by government (e-GA) sites. Nothing is added to the pipeline."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, quote
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tender_scanner as ts

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "scanner_config.json"), encoding="utf-8"))
KW = cfg["keywords"]
COMMON = ["/tenders", "/tender", "/pages/tenders", "/pages/procurement-management-unit", "/publications/tenders",
          "/procurement", "/procurements", "/index.php/tenders", "/en/tenders", "/zabuni", "/announcements",
          "/category/tenders", "/tenders/all", "/procurement/tenders"]
SITES = """tba.go.tz nhc.co.tz dawasa.go.tz tpdc.co.tz rea.go.tz temesa.go.tz moe.go.tz mow.go.tz psssf.go.tz
ewura.go.tz tanzaniaparks.go.tz ncaa.go.tz tfs.go.tz tasaf.go.tz tbs.go.tz nemc.or.tz ttcl.co.tz posta.co.tz
airtanzania.co.tz meteo.go.tz gst.go.tz udom.ac.tz sua.ac.tz aru.ac.tz mzumbe.ac.tz nm-aist.ac.tz bmh.or.tz
kcmc.ac.tz tcbbank.co.tz moh.go.tz tcaa.go.tz latra.go.tz maji.go.tz tra.go.tz udsm.ac.tz
tawa.go.tz tazara.co.tz dart.go.tz tasac.go.tz ega.go.tz tari.go.tz costech.go.tz heslb.go.tz necta.go.tz
tcu.go.tz nacte.go.tz osha.go.tz wcf.go.tz nhif.or.tz gpsa.go.tz tmda.go.tz ppra.go.tz tbc.go.tz
mwauwasa.go.tz auwsa.go.tz duwasa.go.tz kilimo.go.tz ardhi.go.tz tamisemi.go.tz ikulu.go.tz pmo.go.tz
mof.go.tz nbs.go.tz tpsc.go.tz bunge.go.tz judiciary.go.tz nit.ac.tz cbe.ac.tz ifm.ac.tz must.ac.tz
mocu.ac.tz tia.ac.tz nssf.go.tz tirdo.or.tz tcaa.go.tz ruwasa.go.tz taa.go.tz tanesco.co.tz zppda.go.tz
mwanzacc.go.tz dodomacc.go.tz arushacc.go.tz kinondonimc.go.tz temekemc.go.tz ubungomc.go.tz kigamboni.go.tz
morogoromc.go.tz tangacc.go.tz mbeyacc.go.tz moshimc.go.tz""".split()
SITES = list(dict.fromkeys(SITES))
LINK = re.compile(r"(tender|zabuni|procure|manunuzi|\bbids?\b|invitation|announce|tangazo|matangazo|notice)", re.I)


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
            self.links.append((self._a[0].strip(), ts.clean(self._a[1]))); self._a = None


def read(url):
    t0 = time.time()
    url = quote(url, safe=":/?=&%#.-_~+")
    try:
        page = ts.http(url, tries=1, timeout=25)
    except Exception as e:
        return {"url": url, "ok": False, "error": str(e)[:120], "sec": round(time.time() - t0, 1)}
    p = ts.Blocks(); p.feed(page)
    tenderish, cons, samples = 0, 0, []
    for tag, text, href in p.blocks:
        tl = text.lower()
        if ts.has_any(tl, KW["tender_words"]) or ts.TENDER_NO.search(text):
            tenderish += 1
            if ts.categorise(tl, cfg) is not None:
                cons += 1
            if len(samples) < 3 and len(text) < 220 and text not in samples:
                samples.append(text[:160])
    return {"url": url, "ok": True, "blocks": len(p.blocks), "tenderish": tenderish, "construction": cons,
            "samples": samples, "_page": page}


def probe(dom):
    home = "https://www." + dom
    tried, links = [], []
    h = read(home)
    page = h.pop("_page", None)
    if not page:
        home = "https://" + dom; h2 = read(home); page = h2.pop("_page", None)
        if page: h = h2
    tried.append(h)
    cand = []
    if page:
        L = Links(); L.feed(page)
        for href, text in L.links:
            if href and (LINK.search(href) or LINK.search(text)) and not href.startswith(("mailto:", "javascript:", "#", "tel:")):
                u = urljoin(home + "/", href)
                if dom.split("/")[0] in u.split("/")[2] and u not in [c for c, _ in links]:
                    links.append((u, text[:60]))
        cand = [u for u, _ in links if not u.lower().endswith((".pdf", ".doc", ".docx"))][:8]
        for p in COMMON:
            u = home + p
            if u not in cand:
                cand.append(u)
        for u in cand:
            r = read(u); r.pop("_page", None)
            if r.get("ok") or "404" not in r.get("error", ""):
                tried.append(r)
    best = max([t for t in tried if t.get("ok")], key=lambda t: (t.get("tenderish", 0), t.get("construction", 0)), default=None)
    return {"dom": dom, "home_ok": bool(page), "best": best, "links": links[:25], "tried": tried}


if __name__ == "__main__":
    with ThreadPoolExecutor(20) as ex:
        res = list(ex.map(probe, SITES))
    os.makedirs(os.path.join(HERE, "..", "data"), exist_ok=True)
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "round": 2, "results": res},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1)
    for r in res:
        b = r["best"] or {}
        print(f"{r['dom'][:24]:24} home={'Y' if r['home_ok'] else 'n'} t={b.get('tenderish', 0):3} c={b.get('construction', 0):3} {b.get('url', '')}")
