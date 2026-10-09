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
# kind: page (fetch a list page) or search (Bing RSS). grp: tz / intl
TZW = ["tanzania", "dar es salaam", "dodoma", "arusha", "mwanza", "zanzibar", "tanga", "mbeya", "morogoro", "moshi", "kigoma", "mtwara", "lindi", "iringa", "tabora", "pwani", "bagamoyo"]
C = []
def page(name, url, client="", ctype="", grp="tz", **kw): C.append(dict(kind="page", name=name, url=url, client=client, client_type=ctype, grp=grp, **kw))
def search(name, q, client="", ctype="", grp="tz", **kw): C.append(dict(kind="search", name=name, search=q, client=client, client_type=ctype, grp=grp, **kw))

# --- previously blocked or empty Tanzanian sites
page("TANESCO tenders", "https://www.tanesco.co.tz/procurement/tenders", "TANESCO", "parastatal")
page("TANESCO tenders (alt)", "https://www.tanesco.co.tz/index.php/procurement/tenders", "TANESCO", "parastatal")
page("MSD tenders", "https://www.msd.go.tz/tenders", "Medical Stores Department (MSD)", "government")
page("WHC tenders", "https://www.whc.go.tz/tenders", "Watumishi Housing Investments", "parastatal")
page("TIC tenders", "https://www.tic.go.tz/tenders", "Tanzania Investment Centre", "government")
page("ZPPDA open tenders", "https://tenders.zppda.go.tz/", "ZPPDA (Zanzibar)", "government", region="Zanzibar")
page("NMB Bank tenders", "https://www.nmbbank.co.tz/tenders", "NMB Bank", "bank")
page("MUHAS tenders", "https://www.muhas.ac.tz/tenders", "MUHAS", "government", region="Dar es Salaam")
page("TAA tenders", "https://www.taa.go.tz/tenders", "Tanzania Airports Authority (TAA)", "government")
page("RUWASA tenders", "https://www.ruwasa.go.tz/tenders", "RUWASA", "government")
page("NHC tenders", "https://www.nhc.co.tz/tenders", "National Housing Corporation (NHC)", "parastatal")
page("TBA procurement", "https://www.tba.go.tz/pages/procurement-management-unit", "Tanzania Buildings Agency (TBA)", "government")
page("TBA announcements", "https://www.tba.go.tz/announcements", "Tanzania Buildings Agency (TBA)", "government")
page("DAWASA announcements", "https://www.dawasa.go.tz/announcements", "DAWASA", "parastatal", region="Dar es Salaam")
page("TPDC tenders", "https://www.tpdc.co.tz/tenders", "TPDC", "parastatal")
page("EWURA public notices", "https://www.ewura.go.tz/publications/public-notice", "EWURA", "government")
page("TANAPA", "https://www.tanzaniaparks.go.tz/tenders", "TANAPA", "government")
page("NCAA", "https://www.ncaa.go.tz/tenders", "Ngorongoro Conservation Area Authority", "government", region="Arusha")
page("PSSSF", "https://www.psssf.go.tz/tenders", "PSSSF", "parastatal")
page("TTCL tenders", "https://www.ttcl.co.tz/ttcl-tenders", "TTCL", "parastatal")
page("ATCL tenders", "https://www.airtanzania.co.tz/tenders", "Air Tanzania", "parastatal")
page("TAMISEMI tenders", "https://www.tamisemi.go.tz/tenders", "PO-RALG (TAMISEMI)", "government")
page("MNH tenders", "https://www.mnh.or.tz/tenders", "Muhimbili National Hospital", "government", region="Dar es Salaam")
page("TIB tenders", "https://www.tib.co.tz/tenders", "TIB Development Bank", "bank")
page("TCB tenders", "https://www.tcbbank.co.tz/tenders", "Tanzania Commercial Bank", "bank")
page("KCMC tenders", "https://www.kcmc.ac.tz/tenders", "KCMC", "government", region="Kilimanjaro")
for cc, nm, rg in [("dodomacc", "Dodoma City Council", "Dodoma"), ("dcc", "Dar es Salaam City Council", "Dar es Salaam"), ("arushacc", "Arusha City Council", "Arusha"),
                   ("mwanzacc", "Mwanza City Council", "Mwanza"), ("kinondonimc", "Kinondoni MC", "Dar es Salaam"), ("ilalamc", "Ilala MC", "Dar es Salaam"),
                   ("temekemc", "Temeke MC", "Dar es Salaam"), ("ubungomc", "Ubungo MC", "Dar es Salaam"), ("morogoromc", "Morogoro MC", "Morogoro"),
                   ("tangacc", "Tanga City Council", "Tanga"), ("mbeyacc", "Mbeya City Council", "Mbeya"), ("moshimc", "Moshi MC", "Kilimanjaro")]:
    page(nm + " tenders", f"https://www.{cc}.go.tz/tenders", nm, "government", region=rg)
page("TendersOnTime Tanzania", "https://www.tendersontime.com/tanzania-tenders/", "", "", source="aggregator")
page("Mwananchi zabuni", "https://www.mwananchi.co.tz/mw/habari/zabuni", "", "", source="aggregator")
page("The Citizen tenders", "https://www.thecitizen.co.tz/tanzania/notices/tenders", "", "", source="aggregator")
page("Daily News tenders", "https://dailynews.co.tz/category/tenders/", "", "", source="aggregator")
page("Exim Bank Tanzania", "https://www.eximbank.co.tz/tenders", "Exim Bank Tanzania", "bank")
page("Stanbic Tanzania", "https://www.stanbicbank.co.tz/tanzania/personal/about-us/tenders", "Stanbic Bank Tanzania", "bank")
page("PPRA tender portal news", "https://www.ppra.go.tz/publications/public-notices", "PPRA", "government")
# --- Tanzanian web searches (catch any government / company site that blocks direct reading)
search("Web search – government tenders (English)", 'site:go.tz "invitation for tenders" construction', source="web search")
search("Web search – government zabuni (Swahili)", 'site:go.tz "tangazo la zabuni" ujenzi', source="web search")
search("Web search – companies and NGOs", 'site:co.tz OR site:or.tz tender "construction" Tanzania', source="web search", must_contain=TZW)
search("Web search – universities and colleges", 'site:ac.tz "invitation for tender" OR "invitation for bids"', source="web search")
search("Web search – NMB / banks", '(site:nmbbank.co.tz OR site:crdbbank.co.tz OR site:nbc.co.tz OR site:stanbicbank.co.tz) tender', source="web search")
search("Web search – TANESCO", 'site:tanesco.co.tz tender', "TANESCO", "parastatal")

# --- International / donor sources active in Tanzania
page("AfDB procurement (Tanzania)", "https://www.afdb.org/en/projects-and-operations/procurement", "African Development Bank", "donor", grp="intl", must_contain=TZW)
search("AfDB – Tanzania notices (web search)", 'site:afdb.org Tanzania "invitation for bids" OR "procurement notice"', "African Development Bank", "donor", grp="intl", must_contain=TZW)
page("dgMarket – Tanzania", "https://www.dgmarket.com/tenders/list.do?locationISO=tz", "", "", grp="intl", source="aggregator")
page("AFD (France) – Tanzania", "https://afd.dgmarket.com/tenders/list.do?locationISO=tz", "Agence Française de Développement", "donor", grp="intl")
page("EAC procurement (Arusha)", "https://www.eac.int/procurement", "East African Community", "donor", grp="intl", region="Arusha")
page("EAC tenders (Arusha)", "https://www.eac.int/tenders", "East African Community", "donor", grp="intl", region="Arusha")
page("African Court (Arusha)", "https://www.african-court.org/wpafc/procurement/", "African Court on Human and Peoples' Rights", "donor", grp="intl", region="Arusha")
page("TradeMark Africa procurement", "https://www.trademarkafrica.com/procurement/", "TradeMark Africa", "donor", grp="intl", must_contain=TZW)
page("IFAD procurement notices", "https://www.ifad.org/en/procurement-notices", "IFAD", "donor", grp="intl", must_contain=TZW)
page("IsDB project tenders", "https://www.isdb.org/project-procurement/tenders", "Islamic Development Bank", "donor", grp="intl", must_contain=TZW)
page("EU Funding & Tenders – Tanzania", "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-tenders?keywords=Tanzania", "European Commission", "donor", grp="intl", via="reader")
page("UK Find a Tender – Tanzania", "https://www.find-tender.service.gov.uk/Search/Results?keywords=Tanzania", "UK Government (FCDO)", "donor", grp="intl")
page("UK Contracts Finder – Tanzania", "https://www.contractsfinder.service.gov.uk/Search/Results?keywords=Tanzania", "UK Government (FCDO)", "donor", grp="intl")
page("CanadaBuys – Tanzania", "https://canadabuys.canada.ca/en/tender-opportunities?search_filter=Tanzania", "Government of Canada", "donor", grp="intl")
page("Irish eTenders – Tanzania", "https://www.etenders.gov.ie/epps/quickSearchAction.do?searchType=projectFTS&latest=true&searchString=Tanzania", "Irish Aid", "donor", grp="intl")
page("Enabel (Belgium) procurement", "https://www.enabel.be/public-procurement/", "Enabel", "donor", grp="intl", must_contain=TZW)
page("Global Fund business opportunities", "https://www.theglobalfund.org/en/business-opportunities/", "The Global Fund", "donor", grp="intl", must_contain=TZW)
page("Gavi tenders", "https://www.gavi.org/our-alliance/work-with-us/tenders", "Gavi", "donor", grp="intl", must_contain=TZW)
page("African Union bids", "https://au.int/en/bids", "African Union", "donor", grp="intl", must_contain=TZW)
page("SADC procurement", "https://www.sadc.int/procurement", "SADC", "donor", grp="intl", must_contain=TZW)
page("IOM Tanzania procurement", "https://tanzania.iom.int/procurement", "IOM Tanzania", "donor", grp="intl")
page("DevelopmentAid – Tanzania tenders", "https://www.developmentaid.org/tenders/search?locations=196", "", "", grp="intl", source="aggregator", must_contain=TZW)
page("UNGM – Tanzania (reader)", "https://www.ungm.org/Public/Notice?Countries=210", "UN agencies", "donor", grp="intl")
search("GIZ Tanzania tenders (web search)", '(site:giz.de OR site:ausschreibungen.giz.de) Tanzania tender OR Ausschreibung', "GIZ", "donor", grp="intl", must_contain=TZW)
search("KfW / GTAI Tanzania tenders (web search)", '(site:gtai.de OR site:kfw-entwicklungsbank.de) Tansania Ausschreibung OR tender', "KfW-funded", "donor", grp="intl", must_contain=TZW + ["tansania"])
search("JICA Tanzania tenders (web search)", 'site:jica.go.jp Tanzania tender OR bidding', "JICA", "donor", grp="intl", must_contain=TZW)
search("US Embassy Tanzania solicitations (web search)", 'site:tz.usembassy.gov solicitation OR tender OR "request for quotations"', "US Embassy Dar es Salaam", "donor", grp="intl")
search("EU Delegation Tanzania (web search)", '(site:eeas.europa.eu OR site:ec.europa.eu) Tanzania tender construction', "EU Delegation", "donor", grp="intl", must_contain=TZW)
search("EIB Tanzania (web search)", 'site:eib.org Tanzania procurement OR tender', "European Investment Bank", "donor", grp="intl", must_contain=TZW)
search("UN agencies Tanzania (web search)", '(site:unicef.org OR site:wfp.org OR site:unhcr.org OR site:unops.org OR site:fao.org) Tanzania "invitation to bid" OR tender', "UN agencies", "donor", grp="intl", must_contain=TZW)
search("Embassies in Dar es Salaam (web search)", 'embassy "Dar es Salaam" tender OR "request for quotation" construction OR renovation', "Embassies", "donor", grp="intl", must_contain=TZW)
search("NGOs in Tanzania (web search)", 'Tanzania NGO "invitation to tender" construction OR renovation OR rehabilitation', "NGOs", "ngo", grp="intl", must_contain=TZW)
search("Aga Khan Tanzania (web search)", 'Aga Khan Tanzania tender construction OR "expression of interest"', "Aga Khan Development Network", "ngo", grp="intl", must_contain=TZW)
search("Mining companies Tanzania (web search)", 'Tanzania mine tender construction "expression of interest" OR "invitation to tender"', "Mining companies", "private", grp="intl", must_contain=TZW)
search("World Bank Tanzania (web search)", 'site:worldbank.org Tanzania "invitation for bids" OR "request for bids" works', "World Bank-funded", "donor", grp="intl", must_contain=TZW)


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
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "round": 4, "results": res},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1)
    for r in res:
        print(r["name"][:40], r.get("ok"), r.get("used", ""), r.get("n"), r.get("error", "")[:80])
