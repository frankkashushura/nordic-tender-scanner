"""Round 6 (one-off): test web-search (DuckDuckGo) and JSON-API sources with ts_next.py. Writes data/probe_report.json."""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ts_next as ts
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "scanner_config.json"), encoding="utf-8"))
TZW = ["tanzania", "dar es salaam", "dodoma", "arusha", "mwanza", "zanzibar", "tanga", "mbeya", "morogoro", "moshi", "kigoma", "mtwara", "lindi", "iringa", "tabora", "pwani", "bagamoyo"]
S = [("TANESCO", "site:tanesco.co.tz tender"), ("NMB", "site:nmbbank.co.tz tender"), ("TAA", "site:taa.go.tz tender"),
     ("ZPPDA", "site:zppda.go.tz zabuni OR tender"), ("PSSSF", "site:psssf.go.tz tender"), ("Councils sw", 'site:go.tz "tangazo la zabuni" ujenzi'),
     ("Gov en", 'site:go.tz "invitation for tenders" construction'), ("AfDB TZ", "site:afdb.org Tanzania procurement notice"),
     ("GIZ TZ", "GIZ Tanzania tender construction"), ("JICA TZ", "JICA Tanzania tender construction"), ("US Embassy TZ", "site:tz.usembassy.gov solicitation"),
     ("EU TZ", "EU Delegation Tanzania tender"), ("Embassies", '"Dar es Salaam" embassy tender renovation'), ("NGOs", 'Tanzania NGO "invitation to tender" construction'),
     ("Aga Khan", "Aga Khan Tanzania tender construction"), ("Mining", "Tanzania mine tender construction contractor"), ("EIB TZ", "site:eib.org Tanzania procurement")]
EC = "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=Tanzania&pageSize=50&pageNumber=1"


def srch(a):
    n, q = a
    try:
        rows = ts._ddg(q)
        pg = {"name": "Web search – " + n, "search": q, "url": "https://duckduckgo.com/?q=" + q, "must_contain": TZW if n not in ("TANESCO", "NMB", "TAA", "ZPPDA", "PSSSF", "Councils sw", "Gov en") else None}
        pg = {k: v for k, v in pg.items() if v}
        got = ts.src_webpage(pg, cfg, None, 0)
        return {"name": n, "ok": True, "rows": len(rows), "sample": [r[0][:90] + " | " + r[1][:80] for r in rows[:6]], "n": len(got), "items": [g["title"][:120] for g in got[:6]]}
    except Exception as e:
        return {"name": n, "ok": False, "error": str(e)[:200]}


def api(a):
    n, pg = a
    try:
        got = ts.src_webpage(pg, cfg, None, 0)
        kept, dropped, _ = ts.analyse([dict(g, _src=n) for g in got], ts.datetime.now(), cfg)
        return {"name": n, "ok": True, "n": len(got), "items": [(g["title"][:110], str(g["deadline"]), g["source_url"][:90]) for g in got[:8]], "kept": len(kept)}
    except Exception as e:
        return {"name": n, "ok": False, "error": str(e)[:300]}


def raw(a):
    n, form = a
    import uuid, urllib.request
    try:
        bnd = uuid.uuid4().hex
        body = "".join(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"; filename="blob"\r\nContent-Type: application/json\r\n\r\n{json.dumps(v)}\r\n' for k, v in form.items()) + f"--{bnd}--\r\n"
        req = urllib.request.Request(EC, data=body.encode(), method="POST", headers={**ts.BROWSER_HEADERS, "Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={bnd}"})
        with ts.OPENER.open(req, timeout=60) as r:
            j = json.loads(r.read().decode())
        res = j.get("results", [])
        return {"name": n, "ok": True, "total": j.get("totalResults"), "first": [{k: (v if k != "metadata" else {mk: mv[:2] if isinstance(mv, list) else mv for mk, mv in list(v.items())[:60]}) for k, v in x.items() if k in ("title", "url", "summary", "reference", "metadata")} for x in res[:2]],
                "types": sorted({str((x.get("metadata") or {}).get("type")) for x in res})}
    except Exception as e:
        return {"name": n, "ok": False, "error": str(e)[:300]}


APIS = [("UK Contracts Finder API", {"name": "UK Contracts Finder – Tanzania", "url": "https://www.contractsfinder.service.gov.uk/Search/Results?keywords=Tanzania",
         "api": {"method": "POST", "url": "https://www.contractsfinder.service.gov.uk/api/rest/2/search_notices/json",
                 "body": {"searchCriteria": {"keyword": "Tanzania", "statuses": ["Open"]}, "size": 100},
                 "items": "noticeList", "title": "item.title", "text": "item.description", "id": "item.id",
                 "link_template": "https://www.contractsfinder.service.gov.uk/Notice/{id}", "deadline": "item.deadlineDate", "posted": "item.publishedDate"}})]
RAW = [("EC all", {"languages": ["en"]}),
       ("EC tenders open", {"query": {"bool": {"must": [{"terms": {"type": ["0", "1", "2", "8"]}}, {"terms": {"status": ["31094501", "31094502"]}}]}}, "languages": ["en"]}),
       ("EC type 0 only", {"query": {"bool": {"must": [{"terms": {"type": ["0"]}}]}}, "languages": ["en"]})]

if __name__ == "__main__":
    with ThreadPoolExecutor(6) as ex:
        a = list(ex.map(srch, S)); b = list(ex.map(api, APIS)); c = list(ex.map(raw, RAW))
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "round": 6, "search": a, "api": b, "raw": c},
              open(os.path.join(HERE, "..", "data", "probe_report.json"), "w", encoding="utf-8"), indent=1, default=str)
    print("done")
