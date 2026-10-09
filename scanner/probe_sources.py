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
# round 5 candidates
TZW = ["tanzania", "dar es salaam", "dodoma", "arusha", "mwanza", "zanzibar", "tanga", "mbeya", "morogoro", "moshi", "kigoma", "mtwara", "lindi", "iringa", "tabora", "pwani", "bagamoyo"]
C = []
def page(name, url, client="", ctype="", grp="intl", **kw): C.append(dict(kind="page", name=name, url=url, client=client, client_type=ctype, grp=grp, **kw))
for n, u in [("IOM procurement", "https://www.iom.int/procurement-opportunities"), ("UNESCO procurement", "https://www.unesco.org/en/procurement"),
             ("WHO AFRO procurement", "https://www.afro.who.int/about-us/procurement"), ("FAO bidding", "https://www.fao.org/unfao/procurement/bidding-opportunities/en"),
             ("UN-Habitat procurement", "https://unhabitat.org/procurement"), ("ILO tenders", "https://www.ilo.org/about-ilo/how-ilo-works/procurement"),
             ("Danida tenders", "https://um.dk/en/danida/tenders"), ("GIZ procurement", "https://www.giz.de/en/workingwithgiz/procurement.html"),
             ("KfW tenders", "https://www.kfw-entwicklungsbank.de/International-financing/KfW-Development-Bank/Tenders/"),
             ("AfDB specific procurement notices", "https://www.afdb.org/en/documents/project-related-procurement/procurement-notices/specific-procurement-notices"),
             ("AfDB general procurement notices", "https://www.afdb.org/en/documents/project-related-procurement/procurement-notices/general-procurement-notices"),
             ("GlobalTenders Tanzania", "https://www.globaltenders.com/government-tenders-tanzania"), ("GlobalTenders Tanzania 2", "https://www.globaltenders.com/tanzania-tenders.php"),
             ("TenderImpulse Tanzania", "https://www.tenderimpulse.com/tanzania-tenders"), ("TendersGo Tanzania", "https://www.tendersgo.com/tanzania-tenders"),
             ("EAC procurement notices", "https://www.eac.int/procurement/procurement-notices"), ("EAC tenders 2", "https://www.eac.int/procurement/tenders"),
             ("African Court tenders", "https://www.african-court.org/wpafc/tenders/"), ("African Court procurement cat", "https://www.african-court.org/wpafc/category/procurement/"),
             ("IRMCT procurement", "https://www.irmct.org/en/about/procurement"), ("LVBC procurement", "https://www.lvbcom.org/procurement"),
             ("EADB procurement", "https://eadb.org/procurement/"), ("TDB Group procurement", "https://www.tdbgroup.org/procurement/"),
             ("AUDA-NEPAD procurement", "https://www.nepad.org/procurement"), ("Nile Basin procurement", "https://nilebasin.org/procurement"),
             ("UNOPS Tanzania", "https://www.unops.org/tanzania"), ("UNICEF supply tenders", "https://www.unicef.org/supply/tenders"),
             ("WFP procurement", "https://www.wfp.org/procurement"), ("UNHCR procurement", "https://www.unhcr.org/what-we-do/how-we-work/procurement"),
             ("Global Fund sourcing", "https://www.theglobalfund.org/en/sourcing-management/"), ("JICA notices", "https://www.jica.go.jp/english/about/announce/notice/index.html"),
             ("US Embassy Tanzania business", "https://tz.usembassy.gov/business/"), ("British Council Tanzania", "https://www.britishcouncil.co.tz/about/procurement"),
             ("Aga Khan University procurement", "https://www.aku.edu/about/Pages/procurement.aspx"), ("World Bank TZ projects procurement", "https://projects.worldbank.org/en/projects-operations/procurement?srce=both&countrycode_exact=TZ"),
             ("UK Contracts Finder", "https://www.contractsfinder.service.gov.uk/Search/Results?keywords=Tanzania"), ("PPRA notices", "https://www.ppra.go.tz/publications/public-notices"),
             ("Exim Bank Tanzania", "https://www.eximbank.co.tz/tenders"), ("Equity Bank Tanzania", "https://equitygroupholdings.com/tz/tenders"),
             ("CRDB Foundation", "https://crdbbank.co.tz/en/about-us/tender"), ("Absa Tanzania", "https://www.absa.co.tz/about-us/tenders/"),
             ("DTB Tanzania", "https://diamondtrust.co.tz/tenders"), ("KCB Tanzania", "https://tz.kcbgroup.com/tenders"),
             ("Mwalimu Commercial Bank", "https://www.mwalimubank.co.tz/tenders"), ("Vodacom Tanzania", "https://vodacom.co.tz/tenders"),
             ("Tanzania Breweries", "https://www.tanzaniabreweries.co.tz/tenders"), ("GGML Geita Gold", "https://www.geitamine.com/tenders"),
             ("Barrick Tanzania", "https://www.barrick.com/English/operations/tanzania/default.aspx"), ("Puma Energy Tanzania", "https://pumaenergy.com/en/tanzania/tenders")]:
    page(n, u, grp="tz" if n in ("PPRA notices", "Exim Bank Tanzania", "Equity Bank Tanzania", "CRDB Foundation", "Absa Tanzania", "DTB Tanzania", "KCB Tanzania", "Mwalimu Commercial Bank", "Vodacom Tanzania", "Tanzania Breweries", "GGML Geita Gold", "Barrick Tanzania", "Puma Energy Tanzania") else "intl")
API = [("EC F&T search API (GET)", "GET", "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=Tanzania&pageSize=20&pageNumber=1", None),
       ("EC F&T search API (POST)", "POST", "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=Tanzania&pageSize=20&pageNumber=1", {}),
       ("Contracts Finder API", "POST", "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json", {"searchCriteria": {"keyword": "Tanzania"}, "size": 20}),
       ("Find a Tender OCDS", "GET", "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?limit=5", None),
       ("UNDP notices page", "GET", "https://procurement-notices.undp.org/search.cfm?cur_off_id=TZA", None),
       ("DuckDuckGo html", "GET", "https://html.duckduckgo.com/html/?q=site%3Ago.tz+%22invitation+for+tenders%22", None)]

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


def api(a):
    n, m, u, body = a
    try:
        req = ts.urllib.request.Request(u, data=json.dumps(body).encode() if body is not None else None, method=m,
                                        headers={**ts.BROWSER_HEADERS, "Content-Type": "application/json", "Accept": "application/json, text/html"})
        with ts.OPENER.open(req, timeout=40) as r:
            t = r.read().decode("utf-8", "replace")
        return {"name": n, "ok": True, "bytes": len(t), "head": t[:600], "tanzania": t.lower().count("tanzania")}
    except Exception as e:
        return {"name": n, "ok": False, "error": str(e)[:200]}


if __name__ == "__main__":
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(run, enumerate(C)))
        apis = list(ex.map(api, API))
    res.append({"name": "_api", "grp": "", "kind": "api", "routes": {}, "apis": apis})
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "round": 5, "results": res},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1)
    for r in res:
        print(r["name"][:40], r.get("ok"), r.get("used", ""), r.get("n"), r.get("error", "")[:80])
