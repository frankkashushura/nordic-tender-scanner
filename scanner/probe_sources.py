"""Round 4 (one-off): try previously blocked sites through other routes (browser headers, public page reader, web search) and test new Tanzanian and international sources with the next scanner version
(ts_next.py). Writes data/probe_report.json. Nothing is added to the pipeline."""
import json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ts_next as ts
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "scanner_config.json"), encoding="utf-8"))
KW = cfg["keywords"]
FX = os.path.join(HERE, "..", "data", "probe_fx"); os.makedirs(FX, exist_ok=True)
_rl = threading.Lock(); _last = [0.0]
TZW = ["tanzania", "dar es salaam", "dodoma", "arusha", "mwanza", "zanzibar", "tanga", "mbeya", "morogoro", "moshi", "kigoma", "mtwara", "lindi", "iringa", "tabora", "pwani", "bagamoyo"]
C = []
def page(name, url, client="", ctype="", grp="intl", **kw): C.append(dict(kind="page", name=name, url=url, client=client, client_type=ctype, grp=grp, must_contain=TZW, **kw))
for n, u in [("UN Women procurement", "https://www.unwomen.org/en/about-us/procurement/contract-opportunities"), ("UNFPA bid opportunities", "https://www.unfpa.org/procurement/bid-opportunities"),
             ("OPEC Fund procurement", "https://opecfund.org/procurement"), ("BADEA procurement", "https://www.badea.org/procurement"),
             ("Afreximbank procurement", "https://www.afreximbank.com/procurement/"), ("Shelter Afrique procurement", "https://www.shelterafrique.org/procurement/"),
             ("IUCEA procurement", "https://www.iucea.org/procurement/"), ("EALA procurement", "https://www.eala.org/procurement"),
             ("EACJ procurement", "https://www.eacj.org/procurement"), ("ESAMI procurement", "https://esami-africa.org/procurement"),
             ("African Wildlife Foundation procurement", "https://www.awf.org/procurement"), ("CHAI RFPs", "https://www.clintonhealthaccess.org/rfps/"),
             ("PSI procurement", "https://www.psi.org/procurement/"), ("IRC procurement", "https://www.rescue.org/procurement"),
             ("NRC procurement", "https://www.nrc.no/procurement/"), ("DRC procurement", "https://pro.drc.ngo/procurement/"),
             ("Concern tenders", "https://www.concern.net/tenders"), ("Welthungerhilfe tenders", "https://www.welthungerhilfe.org/tenders"),
             ("Plan International procurement", "https://plan-international.org/organisation/procurement/"), ("IFRC procurement", "https://www.ifrc.org/procurement"),
             ("Save the Children Tanzania", "https://tanzania.savethechildren.net/tenders"), ("CARE Tanzania", "https://www.care.or.tz/tenders"),
             ("World Vision Tanzania", "https://www.wvi.org/tanzania/tenders"), ("Mercy Corps RFPs", "https://www.mercycorps.org/rfps"),
             ("Lake Tanganyika Authority", "https://lta-alt.org/procurement"), ("UN Tanzania", "https://tanzania.un.org/en/resources/publications"),
             ("GlobalTenders TZ construction", "https://www.globaltenders.com/tanzania-construction-tenders.php"), ("TenderImpulse TZ construction", "https://www.tenderimpulse.com/tanzania-construction-tenders"),
             ("Tendersglobal Tanzania", "https://www.tendersglobal.net/countries/tanzania/"), ("Africa Tenders Tanzania", "https://www.africa-tenders.com/tanzania"),
             ("EC tenders (TED eTendering Tanzania)", "https://etendering.ted.europa.eu/cft/cft-search.html?_caList=1&text=Tanzania"),
             ("WFP Tanzania", "https://www.wfp.org/countries/tanzania"), ("UNHCR Tanzania", "https://www.unhcr.org/countries/united-republic-tanzania")]:
    page(n, u)

def reader(url):
    with _rl:                                   # the free page reader allows about 20 requests a minute
        wait = 3.5 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
    return ts.http(ts.READER + url, tries=1, timeout=60, headers={"X-Return-Format": "html", "X-Timeout": "40", "Accept": "text/html"})


def stats(page):
    p = ts.Blocks(); p.feed(page); t = c = 0
    for _, text, _ in p.blocks:
        tl = text.lower()
        if ts.has_any(tl, KW["tender_words"]) or ts.TENDER_NO.search(text):
            t += 1; c += ts.categorise(tl, cfg) is not None
    return {"blocks": len(p.blocks), "tenderish": t, "construction": c, "bytes": len(page)}


def run(a):
    i, c = a
    r = {"name": c["name"], "grp": c["grp"], "kind": c["kind"], "routes": {}}
    slug = re.sub(r"[^a-z0-9]+", "_", c["name"].lower()).strip("_")
    t0 = time.time()
    try:
        if c["kind"] == "search":
            raw = ts.http("https://www.bing.com/search?format=rss&count=50&setlang=en&q=" + quote_plus(c["search"]), tries=2, timeout=45, headers=ts.BROWSER_HEADERS)
            P = ts._RSS(); P.feed(raw.replace("<link/>", "<link></link>"))
            r["routes"]["search"] = {"ok": True, "items": len(P.items), "dated": sum(1 for x in P.items if x["pubdate"]), "sample": [x["title"][:100] for x in P.items[:4]]}
            open(os.path.join(FX, f"web_{slug}.rss"), "w", encoding="utf-8").write(raw)
        else:
            page = None
            if c.get("via") != "reader":
                try:
                    pg = ts.http(c["url"], tries=1, timeout=40, headers=ts.BROWSER_HEADERS)
                    r["routes"]["direct"] = {"ok": True, **stats(pg)}; page = pg
                except Exception as e:
                    r["routes"]["direct"] = {"ok": False, "error": str(e)[:140]}
            if page is None or r["routes"].get("direct", {}).get("tenderish", 0) == 0:
                try:
                    pg = reader(c["url"]); r["routes"]["reader"] = {"ok": True, **stats(pg)}
                    if page is None or r["routes"]["reader"]["tenderish"] > max(v.get("tenderish", 0) for k, v in r["routes"].items() if k != "reader"):
                        page = pg; r["used"] = "reader"
                except Exception as e:
                    r["routes"]["reader"] = {"ok": False, "error": str(e)[:140]}
            if page is None:
                raise RuntimeError("no route worked")
            r.setdefault("used", "direct" if r["routes"].get("direct", {}).get("ok") else "reader")
            open(os.path.join(FX, f"web_{slug}.html"), "w", encoding="utf-8").write(page)
        pg = {k: v for k, v in c.items() if k not in ("kind", "grp")}
        got = ts.src_webpage(pg, cfg, FX, i)
        kept, dropped, _ = ts.analyse([dict(g, _src=c["name"]) for g in got], ts.datetime.now(), cfg)
        r.update(ok=True, n=len(got), items=[g["title"][:140] for g in got[:8]], kept=[t["title"][:110] + " || " + t.get("why", "")[:60] for t in kept[:6]])
    except Exception as e:
        r.update(ok=False, error=str(e)[:200])
    r["sec"] = round(time.time() - t0, 1)
    return r


if __name__ == "__main__":
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(run, enumerate(C)))
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "round": 7, "results": res},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1)
    for r in res:
        print(r["name"][:40], r.get("ok"), r.get("used", ""), r.get("n"), r.get("error", "")[:80])
