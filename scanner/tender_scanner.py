"""
Tanzania Tender Scanner - Nordic Construction Company Ltd (assignment F-01)

Checks Tanzanian tender sources for construction and civil-works tenders and adds the
relevant new ones to the "Pipeline" sheet of Nordic_Opportunity_Pipeline.xlsx.
Tenders that are relevant in type but screened out (too far, too big, closing too soon)
go to the "Screened Out" sheet so nothing is lost.

Sources (switch each on/off and set how often it is checked in scanner_config.json):
  nest       NeST - National e-Procurement System of Tanzania (all Mainland public tenders)
  worldbank  World Bank procurement notices - Tanzania projects, civil works only
  tanroads   TANROADS website tender list
  ddo        DDO Tenders Portal – newspaper, private-sector, donor and NGO tenders across Tanzania
  web_pages  any other tender page with a plain list (ZPPDA, TANESCO, TPA, RUWASA, TARURA, BoT, AfDB, CRDB, NMB, ...)

It only reads public pages - the same information anyone sees without logging in.
It never logs in, downloads documents or submits anything.

Run:  py tender_scanner.py            normal run (the Windows schedule does this)
      py tender_scanner.py --dry-run  show what would be added, change nothing
"""
import argparse, hashlib, html, json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

HERE = os.path.dirname(os.path.abspath(__file__))
try:                      # use the Windows certificate store, so sites with incomplete certificate chains
    import truststore     # (e.g. tanesco.co.tz, tarura.go.tz) are verified the same way a browser does
    truststore.inject_into_ssl()
except Exception:
    pass
VERSION = "3.0 NORDIC NEXUS (26 Sep 2026)"
UA = "Nordic-Tender-Scanner/2.0 (tender monitoring for a Tanzanian contractor)"
OPEN_STATUSES = ("Watching", "Preparing")
LOGIN = "NeST login needed"
DOC = "See tender document"

NEST_LIST = "https://nest.go.tz/gateway/nest-app/graphql"
NEST_PE = "https://nest.go.tz/gateway/nest-uaa/graphql"
NEST_PAGE = "https://nest.go.tz/tenders/published-tenders"
NEST_QUERY = """query getPublishedEntityViewData($input: DataRequestInputInput) {
  items: getPublishedEntityViewData(input: $input) {
    totalRecords
    rows: data { descriptionOfTheProcurement entityNumber entitySubCategoryName entityType
                 entityUuid invitationDate procurementCategoryName procuringEntityName
                 procuringEntityUuid submissionOrOpeningDate lotCount }
  }
}"""
NEST_PE_QUERY = """query getProcuringEntityDetailsByUuid($uuid: String) {
  getProcuringEntityDetailsByUuid(uuid: $uuid) { data { region { areaName } district { areaName } } }
}"""
WB_API = ("https://search.worldbank.org/api/v2/procnotices?format=json&rows=100&os=0"
          "&project_ctry_name_exact=Tanzania&procurement_group_exact=CW&srt=submission_date&order=desc")
WB_NOTICE = "https://projects.worldbank.org/en/projects-operations/procurement-detail/"


# ================================================================== small helpers
def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def has_any(text, words):
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text) for w in words)


def key_of(*parts):
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def load_json(name, default):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(name, data):
    try:
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
    except OSError:
        pass


# keeps cookies between redirects (some sites, e.g. tarura.go.tz, set a cookie and redirect)
from http import cookiejar as _cookiejar
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookiejar.CookieJar()))


def http(url, payload=None, tries=3, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.5"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, data=data, method="POST" if data else "GET", headers=headers)
            with OPENER.open(req, timeout=timeout) as r:
                raw = r.read()
                enc = r.headers.get_content_charset() or "utf-8"
                return raw.decode(enc, errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            if attempt < tries:
                time.sleep(5 * attempt)
    raise RuntimeError(f"could not reach {url.split('/')[2]} ({last})")


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_dt(s):
    """Understands 2026-10-09T14:00, 09/10/2026 10:00 AM, 9-Oct-2026, 9th October 2026, October 9, 2026."""
    if not s:
        return None
    s = clean(str(s))
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?", s)
    if m:
        y, mo, d, hh, mm = m.groups()
        return safe_dt(int(y), int(mo), int(d), int(hh or 0), int(mm or 0))
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?:\D{1,3}(\d{1,2})[:.](\d{2})\s*([AaPp][Mm])?)?", s)
    if m:
        d, mo, y, hh, mm, ap = m.groups()
        return safe_dt(int(y), int(mo), int(d), hour12(hh, ap), int(mm or 0))
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})\.?,?[\s\-]+(\d{4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        return safe_dt(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)), *time_in(s))
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return safe_dt(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)), *time_in(s))
    return None


def hour12(hh, ap):
    if hh is None:
        return 0
    h = int(hh)
    if ap and ap.lower() == "pm" and h < 12:
        h += 12
    if ap and ap.lower() == "am" and h == 12:
        h = 0
    return h


def time_in(s):
    m = re.search(r"(\d{1,2})[:.](\d{2})\s*([AaPp]\.?[Mm]\.?)?", s)
    if not m:
        return (0, 0)
    return (hour12(m.group(1), (m.group(3) or "").replace(".", "")), int(m.group(2)))


def safe_dt(y, mo, d, hh=0, mm=0):
    try:
        return datetime(y, mo, d, min(hh, 23), min(mm, 59))
    except ValueError:
        return None


def nice_name(pe):
    small = {"of", "and", "for", "the", "wa", "la", "ya", "es"}
    keep = {"TARURA", "TANROADS", "RUWASA", "TRC", "NHC", "TPDC", "TANESCO", "DAWASA", "LATRA", "TANAPA",
            "NPS", "DC", "MC", "CO.LTD", "LTD", "HQ", "TBC", "BOT", "NIC", "NFRA", "TRA", "PPRA", "CRDB", "NMB", "PLC",
            "NSSF", "TCRA", "TPA", "TAA", "TTCL", "UDSM", "DUWASA", "MUWASA", "TUWASA", "ZPPDA", "ZECO", "ZAWA", "SMZ"}
    out = []
    for i, w in enumerate(clean(pe).split(" ")):
        if w.upper().strip("(),") in keep:
            out.append(w.upper())
        elif w.lower() in small and i:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out).replace("Refferal", "Referral")


# ================================================================== sources
# Every source returns a list of "items" (plain dicts) with these keys:
#   key, source, source_url, no, client, client_type, title, text_for_location, pe_region, pe_district,
#   deadline (datetime or None), invited (datetime or None), notice_type, info_cells (dict of Pipeline values)

def src_nest(cfg, fx):
    if fx is not None:
        data = json.load(open(os.path.join(fx, "nest.json"), encoding="utf-8"))
        rows, regions = data["rows"], data["regions"]
    else:
        rows, page = [], 1
        while True:
            payload = {"operationName": "getPublishedEntityViewData", "query": NEST_QUERY, "variables": {"input": {
                "page": page, "pageSize": 100,
                "fields": [{"fieldName": "invitationDate", "isSortable": True, "orderDirection": "DESC"}],
                "mustHaveFilters": [
                    {"fieldName": "entityStatus", "operation": "IN", "inValues": ["PUBLISHED"]},
                    {"fieldName": "procurementCategoryName", "operation": "IN", "inValues": ["Works"]}]}}}
            res = json.loads(http(NEST_LIST, payload))
            items = (res.get("data") or {}).get("items")
            if not items:
                raise RuntimeError(f"unexpected answer from NeST: {str(res)[:200]}")
            batch = items.get("rows") or []
            rows.extend(batch)
            if len(batch) < 100 or len(rows) >= (items.get("totalRecords") or 0) or page > 50:
                break
            page += 1
        cache = load_json("pe_region_cache.json", {})
        for u in {r.get("procuringEntityUuid") for r in rows}:
            if u and u not in cache:
                try:
                    res = json.loads(http(NEST_PE, {"operationName": "getProcuringEntityDetailsByUuid",
                                                    "query": NEST_PE_QUERY, "variables": {"uuid": u}}, tries=2))
                    d = ((res.get("data") or {}).get("getProcuringEntityDetailsByUuid") or {}).get("data") or {}
                    cache[u] = [(d.get("region") or {}).get("areaName") or "", (d.get("district") or {}).get("areaName") or ""]
                except RuntimeError:
                    pass
        save_json("pe_region_cache.json", cache)
        regions = cache
    out = []
    for t in rows:
        reg, dist = regions.get(t.get("procuringEntityUuid"), ["", ""])
        sub = clean(t.get("entitySubCategoryName"))
        out.append({
            "key": t.get("entityUuid") or key_of("nest", t.get("entityNumber", "")), "source": "NeST",
            "source_url": NEST_PAGE, "no": clean(t.get("entityNumber")),
            "client": nice_name(t.get("procuringEntityName")), "client_type": None,
            "title": clean(t.get("descriptionOfTheProcurement")), "loc_text": "", "pe_region": reg, "pe_district": dist,
            "deadline": parse_dt(t.get("submissionOrOpeningDate")), "invited": parse_dt(t.get("invitationDate")),
            "notice_type": f"{sub} / {clean(t.get('entityType')).replace('_', ' ').title()}", "sub": sub,
            "lots": t.get("lotCount") or 1, "login_fields": LOGIN})
    return out


def src_worldbank(cfg, fx):
    raw = open(os.path.join(fx, "worldbank.json"), encoding="utf-8").read() if fx is not None else http(WB_API)
    data = json.loads(raw)
    skip = [w.lower() for w in cfg["sources"]["worldbank"].get("skip_notice_types", [])]
    out = []
    for n in data.get("procnotices", []):
        nt = clean(n.get("notice_type"))
        if any(w in nt.lower() for w in skip):
            continue
        if (n.get("project_ctry_name") or "").lower() != "tanzania":
            continue
        dl = parse_dt(n.get("submission_deadline_date"))
        if dl and n.get("submission_deadline_time"):
            t = parse_dt("2000-01-01T" + n["submission_deadline_time"])
            if t:
                dl = dl.replace(hour=t.hour, minute=t.minute)
        client = clean(n.get("contact_organization")) or clean(n.get("project_name"))
        out.append({
            "key": "WB:" + clean(n.get("id")), "source": "donor", "source_url": WB_NOTICE + clean(n.get("id")),
            "no": clean(n.get("bid_reference_no")) or clean(n.get("id")), "client": nice_name(client),
            "client_type": "donor", "title": clean(n.get("bid_description")),
            "loc_text": clean(n.get("project_name")) + " " + clean(n.get("contact_address")),
            "pe_region": "", "pe_district": "", "deadline": dl, "invited": parse_dt(n.get("noticedate")),
            "notice_type": f"World Bank – {nt} ({clean(n.get('procurement_method_name'))})",
            "sub": clean(n.get("procurement_method_name")), "lots": 1, "login_fields": DOC,
            "extra_scope": f"World Bank project: {clean(n.get('project_name'))} ({clean(n.get('project_id'))})"})
    return out


class TableRows(HTMLParser):
    """Collects table rows as lists of (text, first link) cells."""
    def __init__(self):
        super().__init__(); self.rows, self.row, self.cell, self.href, self.in_cell = [], None, [], None, False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.in_cell, self.cell, self.href = True, [], None
        elif tag == "a" and self.in_cell and self.href is None:
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.in_cell:
            self.row.append((clean(" ".join(self.cell)), self.href)); self.in_cell = False
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def src_tanroads(cfg, fx):
    url = cfg["sources"]["tanroads"]["url"]
    page = open(os.path.join(fx, "tanroads.html"), encoding="utf-8").read() if fx is not None else http(url)
    p = TableRows(); p.feed(page)
    out, header = [], None
    for row in p.rows:
        texts = [c[0].lower() for c in row]
        if "tender no." in texts or "tender no" in texts or ("name" in texts and "deadline" in texts):
            header = texts; continue
        if header is None or len(row) < len(header):
            continue
        cell = {h: row[i] for i, h in enumerate(header)}
        name, no = cell.get("name", ("", None)), cell.get("tender no.", cell.get("tender no", ("", None)))
        title, tno = name[0], no[0]
        if not title or re.search(r"/C/\d|/NC/\d|/G/\d", tno):      # consultancy, non-consultancy, goods
            continue
        region = cell.get("region", ("", None))[0]
        out.append({
            "key": "TANROADS:" + (norm(tno) or key_of(title)), "source": "client site",
            "source_url": urljoin(url, name[1] or no[1] or url), "no": tno, "client": "TANROADS",
            "client_type": "government", "title": title, "loc_text": region, "pe_region": region, "pe_district": "",
            "deadline": parse_dt(cell.get("deadline", ("", None))[0]), "invited": None,
            "notice_type": "TANROADS website", "sub": "", "lots": 1, "login_fields": DOC})
    if not p.rows:
        raise RuntimeError("TANROADS page had no table – the page layout may have changed")
    return out


DDO_URL = "https://www.ddotenders.co.tz/tender.php?page=home"
DDO_CARD = re.compile(r'<div class="caard vacancy-list" data-id="(\d+)">(.*?)<hr class="divider"', re.S)


def src_ddo(cfg, fx):
    """DDO Tenders Portal – Tanzanian aggregator of newspaper, private-sector, donor and NGO tenders.
    The public list shows title, company, reference, closing date and place; full details need a
    DDO subscription or the original advert."""
    url = cfg["sources"].get("ddo", {}).get("url", DDO_URL)
    page = open(os.path.join(fx, "ddo.html"), encoding="utf-8").read() if fx is not None else http(url)
    cards = DDO_CARD.findall(page)
    if not cards:
        raise RuntimeError("DDO page had no tender cards – the page layout may have changed")
    out = []
    for did, body in cards:
        h3 = re.search(r"<h3>(.*?)</h3>", body, re.S)
        raw = clean(re.sub(r"<[^>]+>", " ", h3.group(1))) if h3 else ""
        m = re.match(r"(.*?)_(\d{1,2}),?\s*([A-Za-z]{3,9})\s+(\d{4})\s*$", raw)
        title, posted = (m.group(1).strip(), parse_dt(f"{m.group(2)} {m.group(3)[:3]} {m.group(4)}")) if m else (raw, None)
        det = clean(html.unescape(re.sub(r"<[^>]+>", " ", (re.search(r"<larger[^>]*>(.*?)</larger>", body, re.S) or [None, ""])[1])))
        def field(name, nxt):
            f = re.search(name + r"\s*:\s*(.*?)(?=" + nxt + r"|$)", det)
            return f.group(1).strip() if f else ""
        company = field("Company", r"Reference\s*:|Closing date\s*:|Place\s*:")
        ref = field("Reference", r"Closing date\s*:|Place\s*:")
        closing = field("Closing date", r"Place\s*:")
        place = field("Place", r"$^")
        dl = parse_dt(closing) if closing else None
        if dl is None:
            d2 = re.search(r"DEADLINE:\s*(\d{4}-\d{2}-\d{2})", body)
            dl = parse_dt(d2.group(1)) if d2 else None
        if dl is not None and dl.hour == 0 and dl.minute == 0:
            dl = dl.replace(hour=10)                     # closing hour not shown – assume 10:00 and confirm
        out.append({
            "key": "DDO:" + did, "source": "press", "source_url": url, "no": ref, "client": company or "See advert",
            "client_type": None, "title": title, "loc_text": place, "pe_region": place, "pe_district": "",
            "deadline": dl, "deadline_guess": True, "invited": posted,
            "notice_type": "DDO Tenders (newspaper / private / donor)", "sub": "", "lots": 1, "login_fields": DOC})
    return out


class Blocks(HTMLParser):
    """Collects readable text blocks (headings, table rows, list items, links, short paragraphs)."""
    BLOCK = {"tr", "li", "h1", "h2", "h3", "h4", "h5", "p", "article", "div", "section", "td", "dd", "dt"}

    def __init__(self):
        super().__init__(); self.stack, self.blocks, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header", "noscript"):
            self.skip += 1
        if tag in self.BLOCK:
            self.stack.append({"tag": tag, "text": [], "href": None})
        if tag == "a" and self.stack and self.stack[-1]["href"] is None:
            self.stack[-1]["href"] = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK and self.stack:
            b = self.stack.pop()
            text = clean(" ".join(b["text"]))
            if self.stack:                      # parent also gets the text (for its own date/link)
                self.stack[-1]["text"].append(text)
                if self.stack[-1]["href"] is None:
                    self.stack[-1]["href"] = b["href"]
            if 20 <= len(text) <= 600:
                self.blocks.append((b["tag"], text, b["href"]))

    def handle_data(self, data):
        if not self.skip and self.stack:
            self.stack[-1]["text"].append(data)


TENDER_NO = re.compile(r"\b(?:[A-Z]{1,6}\d{0,4}|\d{1,4}[A-Z]?\d*)(?:/[A-Za-z0-9.\-]{1,12}){1,7}/(?:W|WKS|WORKS)/\d{1,4}\b")


def src_json_list(page_cfg, cfg, fx, slug):
    """Sites whose web page is a JavaScript app (e.g. TARURA): read the list straight from the site's JSON API."""
    url = page_cfg["api_url"]
    raw = open(os.path.join(fx, f"web_{slug}.json"), encoding="utf-8").read() if fx is not None else http(url)
    try:
        j = json.loads(raw)
    except ValueError:
        raise RuntimeError("the site's tender list API did not return JSON")
    rows = j.get("data", j) if isinstance(j, dict) else j
    if not isinstance(rows, list):
        raise RuntimeError("the site's tender list API changed format")
    kw, out = cfg["keywords"], []
    for r in rows:
        if not isinstance(r, dict) or r.get("published") is False:
            continue
        title = clean(r.get("title") or "")
        text = clean(title + " " + (r.get("description") or ""))
        tl = text.lower()
        if not (page_cfg.get("every_item_is_a_tender") or has_any(tl, kw["tender_words"]) or TENDER_NO.search(text)):
            continue
        if page_cfg.get("must_contain") and not any(w.lower() in tl for w in page_cfg["must_contain"]):
            continue
        if categorise(tl, cfg) is None:
            continue
        m = TENDER_NO.search(text)
        posted = None
        try:
            posted = datetime.strptime((r.get("createdAt") or "")[:10], "%d-%m-%Y")
        except ValueError:
            pass
        if posted and (datetime.now() - posted).days > page_cfg.get("max_age_days", 60):
            continue                                                     # old notice, long closed
        out.append({
            "key": f"WEB:{slug}:" + (norm(m.group(0)) if m else str(r.get("id") or key_of(title))),
            "source": page_cfg.get("source", "client site"),
            "source_url": r.get("file") or page_cfg["url"], "no": m.group(0) if m else "",
            "client": page_cfg.get("client") or "", "client_type": page_cfg.get("client_type"),
            "title": title[:300], "loc_text": "", "pe_region": page_cfg.get("region", ""), "pe_district": "",
            "deadline": None, "deadline_guess": False, "invited": posted,
            "notice_type": f"{page_cfg['name']} (web page)", "sub": "", "lots": 1, "login_fields": DOC,
            "web": True})
    return out


def src_webpage(page_cfg, cfg, fx, idx):
    url = page_cfg["url"]
    slug = re.sub(r"[^a-z0-9]+", "_", page_cfg["name"].lower()).strip("_")
    if page_cfg.get("api_url"):
        return src_json_list(page_cfg, cfg, fx, slug)
    page = open(os.path.join(fx, f"web_{slug}.html"), encoding="utf-8").read() if fx is not None else http(url)
    p = Blocks(); p.feed(page)
    if not p.blocks:
        raise RuntimeError("no readable text on the page – it may load its list with JavaScript")
    out, seen_txt = [], set()
    kw = cfg["keywords"]
    date_re = re.compile(
        r"\d{1,2}(?:st|nd|rd|th)?[\s\-/.]+(?:[A-Za-z]{3,9}|\d{1,2})[\s\-/.,]+\d{4}(?:\D{1,3}\d{1,2}[:.]\d{2}\s*[AaPp]?[Mm]?)?"
        r"|\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2})?|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}")
    by_len = sorted(p.blocks, key=lambda b: len(b[1]))
    for tag, text, href in by_len:                                       # shortest (most specific) first
        tl = text.lower()
        if not (page_cfg.get("every_item_is_a_tender") or has_any(tl, kw["tender_words"]) or TENDER_NO.search(text)):
            continue
        if page_cfg.get("must_contain") and not any(w.lower() in tl for w in page_cfg["must_contain"]):
            continue
        if categorise(tl, cfg) is None:
            continue
        k = norm(text)[:140]
        if any(k in s_ or s_ in k for s_ in seen_txt):                   # same tender at another nesting level
            continue
        seen_txt.add(k)
        # the listing's dates, number and link are often in a sibling line: use the smallest block around it
        context, ctx_href = text, href
        for _, t2, h2 in by_len:
            if len(t2) > len(text) and text in t2 and len(t2) <= len(text) + 400:
                context, ctx_href = t2, ctx_href or h2
                break
        m = TENDER_NO.search(context)
        dates = [d for d in (parse_dt(x) for x in date_re.findall(context)) if d]
        href = ctx_href
        title = re.sub(r"\s*(read more|download|view details|more)\s*$", "", text, flags=re.I)[:300]
        out.append({
            "key": f"WEB:{slug}:" + (norm(m.group(0)) if m else key_of(k)), "source": page_cfg.get("source", "client site"),
            "source_url": urljoin(url, href) if href else url, "no": m.group(0) if m else "",
            "client": page_cfg.get("client") or "", "client_type": page_cfg.get("client_type"),
            "title": title, "loc_text": "", "pe_region": page_cfg.get("region", ""), "pe_district": "",
            "deadline": max(dates) if dates else None, "deadline_guess": bool(dates), "invited": None,
            "notice_type": f"{page_cfg['name']} (web page)", "sub": "", "lots": 1, "login_fields": DOC,
            "web": True})
    return out


# ================================================================== classification
def locate(text_l, pe_region, pe_district, cfg):
    skip = set(cfg.get("places_title_skip", []))
    best = None
    for place, (label, zone) in cfg["places"].items():
        if place in skip:
            continue
        m = re.search(r"(?<![a-z])" + re.escape(place) + r"(?![a-z])", text_l)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), label, zone)
    if best:
        return best[1], best[2]
    for k in (pe_district, pe_region):
        k = (k or "").lower().replace(" cbd", "").strip()
        if k in cfg["places"]:
            label, zone = cfg["places"][k]
            return f"{label} (from client's office – confirm site)", zone
    reg = clean(pe_region).title()
    return (f"{reg} (from client's office – confirm site)" if reg else "Not stated – read the notice"), ("far" if reg else "unknown")


def categorise(tl, cfg):
    k = cfg["keywords"]
    if has_any(tl, k["exclude"]):
        return None
    b, c, r, f, m = (has_any(tl, k[x]) for x in ("building", "civil", "renovation", "fitout", "mep"))
    if f:
        return "fit-out"
    if m and not b:
        return "MEP"
    if r and (b or not c):
        return "renovation"
    if b and not c:
        return "building"
    if c:
        return "civil"
    if b:
        return "building"
    return None


def client_type(pe_l):
    if "bank of tanzania" in pe_l:
        return "government"
    if "bank" in pe_l:
        return "bank"
    if re.search(r"corporation|company|co\.?\s?ltd|limited|tpdc|tanesco|nhc", pe_l):
        return "parastatal (verify)"
    return "government"


CONSTRUCTION_WORDS = ["construction", "construct", "constructing", "ujenzi", "kujenga"]


def screen(it, cat, zone, days, cfg):
    res = _screen(it, cat, zone, days, cfg)
    # construction tenders are never dropped for type or distance - they go to NEXUS as "Check" (user rule, 27 Sep 2026)
    words = cfg.get("always_keep_words", CONSTRUCTION_WORDS)
    if res[0] == "Drop" and has_any(it["title"].lower(), words) and (days is None or days >= cfg["min_days_left_to_record"]):
        return "Check", f"Construction tender kept for review (would have been dropped: {res[1]})"
    return res


def _screen(it, cat, zone, days, cfg):
    tl, sub = it["title"].lower(), it.get("sub", "").lower()
    if days is None:
        if cat == "MEP":
            return "Drop", "Specialist MEP works – pass to an electrical/mechanical subcontractor"
        return "Check", "Deadline not shown on the source page – open the link and read the notice"
    if days < cfg["min_days_left_to_record"]:
        return "Drop", f"Closes in under {cfg['min_days_left_to_record']:g} days"
    if "subcontract" in sub:
        return "Drop", "Works subcontract package – not main-contractor work"
    if cat == "MEP":
        return "Drop", "Specialist MEP works – pass to an electrical/mechanical subcontractor"
    big_civil = cat == "civil" and ("large" in sub or has_any(tl, ["bitumen", "tarmac", "double surface dressing"]))
    if big_civil and zone != "near":
        return "Drop", "Large road works, likely above Civil Class IV – JV only (escalate to MD if of interest)"
    prequal = "prequalification" in tl or "pre-qualification" in tl
    if cat in ("building", "renovation", "fit-out"):
        if zone in ("near", "mid"):
            res = ("Pursue", "Building works within reach of Dar") if days >= 4 else ("Check", "Good fit but little time left")
        elif zone == "lindi":
            res = ("Check", "Lindi/Mtwara – Nordic has worked there (Likong'o)")
        elif zone == "unknown":
            res = ("Check", "Site not stated in the listing – read the notice")
        else:
            res = ("Check", "Building works but remote from Dar") if days >= 7 else ("Drop", "Remote and closing soon")
    else:
        if zone == "near":
            res = ("Check", "Civil works in Dar/Coast – confirm CRB class and margin")
        elif zone in ("mid", "unknown") and days >= 5:
            res = ("Check", "Civil works – confirm site, CRB class and margin")
        else:
            res = ("Drop", "Remote civil works")
    if res[0] == "Pursue" and "quotation" in sub and not prequal:
        res = ("Check", "Quotation route – value may be below TZS 200m")
    return res


NEXT = {"Pursue": "Get the tender document, confirm value, CRB class, site visit and bid security; brief the MD",
        "Check": "Read the notice and decide with the QS Director whether to pursue",
        "Drop": "Record only"}


def analyse(items, now, cfg):
    kept, dropped, ignored = [], [], 0
    seen_no, seen_title = set(), set()
    for it in items:
        dup_keys = ({norm(it["no"])} if it["no"] else set()), norm(it["title"])[:80]
        if (dup_keys[0] & seen_no) or dup_keys[1] in seen_title:
            ignored += 1; continue                                       # same tender from a second source
        seen_no |= dup_keys[0]; seen_title.add(dup_keys[1])
        tl = it["title"].lower()
        if not it["title"] or (it["deadline"] is not None and it["deadline"] <= now):
            ignored += 1; continue
        cat = categorise(tl, cfg)
        if cat is None:
            ignored += 1; continue
        loc, zone = locate(tl + " " + it.get("loc_text", "").lower(), it["pe_region"], it["pe_district"], cfg)
        days = (it["deadline"] - now).total_seconds() / 86400 if it["deadline"] else None
        scr, why = screen(it, cat, zone, days, cfg)
        if it.get("deadline_guess"):
            why += " · deadline read from the web page – confirm"
        it.update(cat=cat, loc=loc, zone=zone, screen=scr, why=f"Auto ({it['notice_type'].split(' (')[0]}): {why}",
                  client=it["client"] or "See notice", client_type=it["client_type"] or client_type(it["client"].lower()))
        (kept if scr in ("Pursue", "Check") else dropped).append(it)
    return kept, dropped, ignored


# ================================================================== workbook
class WorkbookOpen(Exception):
    pass


def header_map(ws, row):
    return {str(c.value).strip(): c.column for c in ws[row] if c.value}


def update_workbook(path, kept, dropped, sources_ok, now, cfg, dry_run):
    from openpyxl import load_workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    wb = load_workbook(path)
    pl, bn, sl = wb["Pipeline"], wb["Bid-NoBid"], wb["Scan Log"]
    H = header_map(pl, 4)
    alias = {"Notice type": "NeST tender type", "Source ID": "NeST ID"}      # older workbooks
    for new, old in alias.items():
        if new not in H and old in H:
            H[new] = H[old]
    need = ["Tender no.", "Date found", "Source", "Source URL", "Client", "Client type", "Tender title", "Scope summary",
            "Location", "Category", "CRB class required", "Funding confirmed", "Site visit date", "Clarification deadline",
            "Submission date", "Bid security", "Documents purchased", "Status", "Owner", "Date advertised",
            "Notice type", "Initial screen", "Screen reason", "Next action", "Found by", "Source ID"]
    missing = [h for h in need if h not in H]
    if missing:
        raise RuntimeError(f"the Pipeline sheet is missing columns {missing} – was a column renamed or deleted?")

    blue, wrap = Font(name="Arial", size=10, color="0000FF"), Alignment(wrap_text=True, vertical="top")
    first, last = 5, 5
    for r in range(first, pl.max_row + 1):
        v = pl.cell(row=r, column=1).value
        if isinstance(v, str) and v.startswith("="):
            last = r
    ids, nos, titles, by_id, next_row = set(), set(), set(), {}, None
    for r in range(first, last + 1):
        no = pl.cell(row=r, column=H["Tender no."]).value
        ttl = pl.cell(row=r, column=H["Tender title"]).value
        if not no and not ttl:
            next_row = next_row or r; continue
        u = pl.cell(row=r, column=H["Source ID"]).value
        if u:
            ids.add(u); by_id[u] = r
        if no:
            nos.add(norm(str(no)))
        if ttl:
            titles.add(norm(ttl)[:80])
    so = wb["Screened Out"] if "Screened Out" in wb.sheetnames else None
    so_ids = {so.cell(row=r, column=9).value for r in range(5, so.max_row + 1)} if so is not None else set()

    def known(t):
        return (t["key"] in ids or (t["no"] and norm(t["no"]) in nos) or norm(t["title"])[:80] in titles)

    today = datetime(now.year, now.month, now.day)
    added, updated, full = [], [], 0
    live = {t["key"]: t for t in kept + dropped if not t.get("deadline_guess")}
    for u, r in by_id.items():
        if u in live and live[u]["deadline"] and pl.cell(row=r, column=H["Status"]).value in OPEN_STATUSES:
            cell = pl.cell(row=r, column=H["Submission date"])
            if isinstance(cell.value, datetime) and abs((cell.value - live[u]["deadline"]).total_seconds()) > 60:
                updated.append((pl.cell(row=r, column=H["Tender no."]).value, cell.value, live[u]["deadline"]))
                if not dry_run:
                    old = cell.value; cell.value = live[u]["deadline"]
                    na = pl.cell(row=r, column=H["Next action"])
                    na.value = f"Deadline changed at source {today:%d-%b} (was {old:%d-%b %H:%M}). " + (na.value or "")

    for t in sorted(kept, key=lambda x: (x["deadline"] is None, x["deadline"] or now)):
        if known(t):
            continue
        if next_row is None or next_row > last:
            full += 1; continue
        r = next_row
        scope = t.get("extra_scope") or f"From {t['source']} notice ({t['lots']} lot{'s' if t['lots'] != 1 else ''}) – read the tender document"
        vals = {"Tender no.": t["no"] or "(not shown)", "Date found": today, "Source": t["source"], "Source URL": t["source_url"],
                "Client": t["client"], "Client type": t["client_type"], "Tender title": t["title"], "Scope summary": scope,
                "Location": t["loc"], "Category": t["cat"], "CRB class required": t["login_fields"],
                "Funding confirmed": "Y" if t["source"] == "donor" else "unknown", "Site visit date": t["login_fields"],
                "Clarification deadline": t["login_fields"], "Submission date": t["deadline"], "Bid security": t["login_fields"],
                "Documents purchased": "N", "Status": "Watching", "Owner": cfg["owner"], "Date advertised": t["invited"],
                "Notice type": t["notice_type"], "Initial screen": t["screen"], "Screen reason": t["why"],
                "Next action": NEXT[t["screen"]], "Found by": "Auto-scan", "Source ID": t["key"]}
        if not dry_run:
            for h, v in vals.items():
                c = pl.cell(row=r, column=H[h], value=v); c.font = blue; c.alignment = wrap
            score = cfg["location_score"].get(t["zone"])
            if score is not None and bn.cell(row=r, column=14).value in (None, ""):
                bn.cell(row=r, column=14, value=score)
        added.append(t)
        ids.add(t["key"]); titles.add(norm(t["title"])[:80])
        if t["no"]:
            nos.add(norm(t["no"]))
        next_row = next((x for x in range(r + 1, last + 1) if not pl.cell(row=x, column=H["Tender no."]).value
                         and not pl.cell(row=x, column=H["Tender title"]).value), None)

    new_drops = [t for t in dropped if t["key"] not in so_ids and not known(t)]
    changed = bool(added or new_drops or updated)
    if not dry_run and changed:
        d, n = os.path.split(path)
        if os.path.exists(os.path.join(d, "~$" + n)):
            raise WorkbookOpen(added, new_drops, updated)
        if so is None:
            so = wb.create_sheet("Screened Out")
            so["A1"] = "Screened out automatically"; so["A1"].font = Font(name="Arial", bold=True, size=14, color="1F3A4D")
            so["A2"] = ("Construction/civil tenders the scanner found but did not add to the Pipeline, with the reason. "
                        "To pursue one, copy it into the next empty Pipeline row.")
            so["A2"].font = Font(name="Arial", italic=True, size=9)
            for j, h in enumerate(["Date found", "Tender no.", "Client", "Tender title", "Location", "Category", "Closes",
                                   "Reason", "Source ID", "Source", "Link"], 1):
                c = so.cell(row=4, column=j, value=h)
                c.font = Font(name="Arial", bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F3A4D")
            for j, w in enumerate([11, 24, 30, 60, 26, 10, 16, 50, 14, 12, 30], 1):
                so.column_dimensions[chr(64 + j)].width = w
            so.freeze_panes = "A5"
        r = max(5, so.max_row + 1)
        for t in new_drops:
            for j, v in enumerate([today, t["no"], t["client"], t["title"], t["loc"], t["cat"], t["deadline"], t["why"],
                                   t["key"], t["source"], t["source_url"]], 1):
                c = so.cell(row=r, column=j, value=v); c.font = Font(name="Arial", size=10); c.alignment = wrap
            so.cell(row=r, column=1).number_format = "dd-mmm-yy"; so.cell(row=r, column=7).number_format = "dd-mmm-yy hh:mm"
            r += 1
        lr = 5
        while sl.cell(row=lr, column=1).value not in (None, ""):
            lr += 1
        per = {}
        for t in added:
            per[t["notice_type"].split(" (")[0].split(" – ")[0].split(" /")[0]] = per.get(t["notice_type"].split(" (")[0].split(" – ")[0].split(" /")[0], 0) + 1
        msg = (f"Automatic scan of {', '.join(sources_ok)}: {len(added)} new added to Pipeline"
               + (f" ({', '.join(f'{k}: {v}' for k, v in per.items())})" if per else "")
               + f"; {len(new_drops)} screened out; {len(updated)} deadline change(s)" + (f"; {full} NOT added – Pipeline full" if full else ""))
        for j, v in enumerate([today, "Automatic scan (all sources)", "", msg, len(added), "Auto-scanner"], 1):
            c = sl.cell(row=lr, column=j, value=v); c.font = blue; c.alignment = wrap
        sl.cell(row=lr, column=1).number_format = "dd-mmm-yy"
        wb.calculation.fullCalcOnLoad = True
        tmp = path + ".tmp.xlsx"
        try:
            wb.save(tmp); os.replace(tmp, path)
        except PermissionError:
            try: os.remove(tmp)
            except OSError: pass
            raise WorkbookOpen(added, new_drops, updated)
    free = sum(1 for x in range(first, last + 1) if not pl.cell(row=x, column=H["Tender no."]).value
               and not pl.cell(row=x, column=H["Tender title"]).value)
    return added, new_drops, updated, full, free


# ================================================================== report and email
def write_report(show, drops, updated, full, free, source_lines, now, dry_run, pending):
    L = [f"Tender Scan – {now:%A %d %B %Y, %H:%M}" + ("  (DRY RUN – nothing saved)" if dry_run else ""), ""]
    L += ["Sources checked:"] + [f"  {s}" for s in source_lines] + [""]
    if pending:
        L += ["THE WORKBOOK IS OPEN, so these have NOT been added yet. They will be added",
              "automatically at the first scan after the workbook is closed.", ""]
    for label in ("Pursue", "Check"):
        items = [t for t in show if t["screen"] == label]
        L.append(f"NEW – {label.upper()} ({len(items)})")
        for t in items:
            closes = f"closes {t['deadline']:%a %d %b %H:%M}" if t["deadline"] else "closing date: see notice"
            L.append(f"  • {closes}  {t['client']} – {t['title'][:110]}  [{t['loc']}]  ({t['no'] or 'no number'}; {t['notice_type']})")
            L.append(f"      {t['source_url']}")
        L.append("")
    if updated:
        L.append("DEADLINE CHANGED AT SOURCE")
        L += [f"  • {no}: was {old:%d %b %H:%M}, now {new:%d %b %H:%M}" for no, old, new in updated] + [""]
    L.append(f"Screened out (see the 'Screened Out' sheet): {len(drops)}")
    if free is not None:
        L.append(f"Empty Pipeline rows left: {free}")
    if full:
        L.append(f"WARNING: {full} tenders could not be added because the Pipeline is full. Start a new workbook.")
    elif free is not None and free < 50:
        L.append("WARNING: fewer than 50 empty rows left. Plan a new workbook for the next quarter.")
    text = "\n".join(L)
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    rp = os.path.join(HERE, "reports", f"scan_{now:%Y-%m-%d_%H%M}.txt")
    with open(rp, "w", encoding="utf-8") as f:
        f.write(text)
    return text, rp


def email_report(text, fresh, cfg, pending):
    to = (cfg.get("email_to") or "").strip()
    if not to or not fresh:
        return
    try:
        import win32com.client  # optional: py -m pip install pywin32 ; needs Outlook on this PC
        mail = win32com.client.Dispatch("Outlook.Application").CreateItem(0)
        mail.To = to
        n = sum(1 for t in fresh if t["screen"] == "Pursue")
        mail.Subject = f"Tender scan: {len(fresh)} new tenders ({n} to pursue)" + (" – workbook open, not yet added" if pending else "")
        mail.Body = text + "\n\nOpen the Pipeline workbook in the shared folder for details."
        mail.Send()
        log(f"Report emailed to {to}")
    except Exception as e:
        log(f"Email not sent ({e}). The report is still saved in the reports folder.")


# ================================================================== main
def single_instance(minutes):
    lock = os.path.join(HERE, "scanner.lock")
    try:
        if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < minutes * 60:
            return None
        with open(lock, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    return lock


def open_logfile(path):
    path = os.path.join(HERE, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if os.path.getsize(path) > 1_000_000:
            os.replace(path, path + ".old")
    except OSError:
        pass
    sys.stdout = sys.stderr = open(path, "a", encoding="utf-8", buffering=1)


def main():
    ap = argparse.ArgumentParser(description="Scan Tanzanian tender sources and add relevant tenders to the pipeline.")
    ap.add_argument("--dry-run", action="store_true", help="show what would be added; change nothing")
    ap.add_argument("--all", action="store_true", help="check every source now, ignoring each source's interval")
    ap.add_argument("--logfile", help="append output to this file (used by the scheduled task)")
    ap.add_argument("--fixture-dir", help="(testing) read sources from files in this folder")
    ap.add_argument("--now", help="(testing) pretend the time is YYYY-MM-DDTHH:MM")
    args = ap.parse_args()
    if args.logfile:
        open_logfile(args.logfile)
    with open(os.path.join(HERE, "scanner_config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    lock = None
    if not args.dry_run:
        lock = single_instance(cfg.get("skip_if_previous_scan_running_minutes", 14))
        if lock is None:
            log("Previous scan still running – skipped."); return
    try:
        run(args, cfg)
    finally:
        if lock:
            try: os.remove(lock)
            except OSError: pass


def run(args, cfg):
    now = datetime.strptime(args.now, "%Y-%m-%dT%H:%M") if args.now else datetime.now()
    path = cfg["workbook_path"].replace("\\", "/").replace("/", os.sep)
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(HERE, path))
    if not os.path.exists(path):
        raise RuntimeError(f"Workbook not found at {path}. Check workbook_path in scanner_config.json.")
    fx = os.path.abspath(args.fixture_dir) if args.fixture_dir else None
    state = load_json("source_state.json", {})

    jobs = []
    S = cfg["sources"]
    if S["nest"]["enabled"]:
        jobs.append(("NeST", S["nest"], lambda: src_nest(cfg, fx)))
    if S["worldbank"]["enabled"]:
        jobs.append(("World Bank (Tanzania, civil works)", S["worldbank"], lambda: src_worldbank(cfg, fx)))
    if S["tanroads"]["enabled"]:
        jobs.append(("TANROADS website", S["tanroads"], lambda: src_tanroads(cfg, fx)))
    if S.get("ddo", {}).get("enabled"):
        jobs.append(("DDO Tenders (newspapers, private, donors)", S["ddo"], lambda: src_ddo(cfg, fx)))
    for i, pg in enumerate(S.get("web_pages", [])):
        if pg.get("enabled", True):
            jobs.append((pg["name"], pg, (lambda pg=pg, i=i: src_webpage(pg, cfg, fx, i))))

    items, ok, lines, first_time = [], [], [], set()
    for name, sc, fn in jobs:
        st = state.get(name, {})
        due = args.all or args.dry_run or fx is not None or \
            (time.time() - st.get("last_try", 0)) >= sc.get("every_minutes", 15) * 60 - 30
        if not due:
            continue
        st["last_try"] = time.time()
        try:
            got = fn()
            st.update(last_ok=f"{now:%Y-%m-%d %H:%M}", fails=0, last_count=len(got))
            if st.get("baseline_done") is None:
                first_time.add(name); st["baseline_done"] = True
            for g in got:
                g["_src"] = name
            items += got; ok.append(name)
            lines.append(f"{name}: {len(got)} notices read")
        except Exception as e:
            st["fails"] = st.get("fails", 0) + 1
            st["last_error"] = f"{now:%Y-%m-%d %H:%M} {e}"
            lines.append(f"{name}: FAILED ({e})" + ("  – failing repeatedly, check the source" if st["fails"] >= 3 else ""))
            log(f"{name}: FAILED – {e}")
        state[name] = st

    if not args.dry_run:
        save_json("source_state.json", state)
    if not jobs or not (ok or lines):
        log("No source due this time."); return

    kept, dropped, _ = analyse(items, now, cfg)
    # first check of a plain web page: don't flood the Pipeline with its old notices
    for t in list(kept):
        if t["_src"] in first_time and t.get("web") and t["deadline"] is None:
            kept.remove(t); dropped.append({**t, "why": t["why"] + " · (first check of this page – listed for review only)"})
    seen = set(load_json("notified.json", []))
    pending = False
    try:
        added, drops, updated, full, free = update_workbook(path, kept, dropped, ok, now, cfg, args.dry_run)
    except WorkbookOpen as w:
        (added, drops, updated), full, free, pending = w.args, 0, None, True

    status = (f"{now:%Y-%m-%d %H:%M}  " + "; ".join(lines) + " → "
              + (f"{len(added)} new, {len(updated)} deadline change(s)" if (added or updated) else "no new tenders")
              + ("; WORKBOOK OPEN – waiting to add them" if pending else ""))
    if not args.dry_run:
        with open(os.path.join(HERE, "last_scan.txt"), "w", encoding="utf-8") as f:
            f.write(status + "\n\nPer source:\n" + "\n".join(
                f"  {k}: last OK {v.get('last_ok', 'never')}" + (f"; last error {v['last_error']}" if v.get("fails") else "")
                for k, v in state.items() if k in {j[0] for j in jobs}) + "\n")
    log(status.split("  ", 1)[1])

    fresh = [t for t in added if t["key"] not in seen]
    show = fresh if pending else added
    worth = bool(fresh) if pending else bool(added or updated or drops or full)
    text = ""
    if args.dry_run or worth:
        text, rp = write_report(show, [] if pending else drops, [] if pending else updated, full, free, lines, now,
                                args.dry_run, pending)
        print("\n" + text + "\n")
        log(f"Report saved: {rp}")
    if not args.dry_run and fresh:
        email_report(text, fresh, cfg, pending)
        save_json("notified.json", sorted(seen | {t["key"] for t in fresh}))
    if not args.dry_run:
        try:
            import nexus_alerts
            nexus_alerts.after_scan(cfg, path, fresh, now, log)
        except Exception as e:
            log(f"NEXUS alerts step failed: {e}")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        main()
    except Exception as e:
        log(f"SCAN FAILED: {e}")
        sys.exit(1)
