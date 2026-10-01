"""One-off source probe (NEXUS): reads candidate tender pages from GitHub's computers and reports what the scanner would get.
Nothing is added to the pipeline. Result: data/source_probe.txt"""
import json, os, sys, time, urllib.request, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scanner"))
import tender_scanner as ts

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
cfg = json.load(open(os.path.join(os.path.dirname(ts.__file__), "scanner_config.json"), encoding="utf-8"))
C = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_list.json"), encoding="utf-8"))
out = []
def fetch(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5", "Accept-Language": "en-US,en;q=0.8"})
    t = time.time()
    with ts.OPENER.open(req, timeout=40) as r:
        raw = r.read(); return r.status, raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace"), round(time.time() - t, 1), r.geturl()
for c in C:
    url = c["url"]; line = {"name": c["name"], "url": url}
    for label, ua in (("bot", ts.UA), ("browser", BROWSER)):
        try:
            st, html, sec, final = fetch(url, ua)
            p = ts.Blocks(); p.feed(html)
            if label == 'browser':
                d = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'probe_html'); os.makedirs(d, exist_ok=True)
                open(os.path.join(d, re.sub(r'[^a-z0-9]+', '_', c['name'].lower()) + '.html'), 'w', encoding='utf-8').write(html)
            tw = [b[1] for b in p.blocks if ts.has_any(b[1].lower(), cfg["keywords"]["tender_words"]) or ts.TENDER_NO.search(b[1])]
            line[label] = {"status": st, "sec": sec, "bytes": len(html), "final": final, "blocks": len(p.blocks), "tenderish": len(tw), "sample": [x[:140] for x in sorted(tw, key=len)[:4]]}
            if label == "bot":
                saved = ts.UA
            # what the scanner's own reader keeps (construction only)
            pc = dict(c); pc.setdefault("source", "client site")
            orig_http = ts.http
            ts.http = lambda u, payload=None, tries=1, timeout=40, _h=html: _h
            try:
                kept = ts.src_webpage(pc, cfg, None, 0)
                line[label]["kept"] = len(kept); line[label]["kept_sample"] = [k["title"][:120] for k in kept[:3]]
            except Exception as e:
                line[label]["kept_err"] = str(e)[:120]
            finally:
                ts.http = orig_http
        except Exception as e:
            line[label] = {"error": str(e)[:160]}
    out.append(line)
    print(json.dumps(line, ensure_ascii=False))
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"), exist_ok=True)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "source_probe.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
