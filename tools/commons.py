"""Find and preview free (CC0 / PD / CC BY / CC BY-SA) videos on Wikimedia Commons.

python tools/commons.py search "implosion" "avalanche" ...      -> analysis/candidates.json
python tools/commons.py sheets "File:A.webm" "File:B.ogv" ...   -> analysis/<slug>.jpg (+ .json meta)
python tools/commons.py fine "File:A.webm" 6.0 11.0 [fps]       -> analysis/<slug>_fine_<t0>-<t1>.jpg
"""
import glob, html, json, os, re, subprocess, sys
import httpx
from PIL import Image, ImageDraw

UA = {"User-Agent": "CozdilReels/1.0 (https://github.com/bestselleryilmaz-cmyk/cozdil-reels)"}
API = "https://commons.wikimedia.org/w/api.php"
OK_LICENSES = ("cc0", "public domain", "pd", "cc by ", "cc by-sa", "cc-by", "cc-by-sa")
os.makedirs("analysis", exist_ok=True)
WORK = "/tmp/cozdil_an"; os.makedirs(WORK, exist_ok=True)

def slug(t): return re.sub(r"[^A-Za-z0-9]+", "_", t.replace("File:", ""))[:70].strip("_")
def clean(s): return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

def used():
    try: return {l.strip() for l in open("used_clips.txt", encoding="utf-8") if l.strip()}
    except FileNotFoundError: return set()

def info(titles):
    out = []
    for i in range(0, len(titles), 40):
        r = httpx.get(API, params={"action": "query", "format": "json", "titles": "|".join(titles[i:i + 40]), "prop": "imageinfo",
                                   "iiprop": "url|size|extmetadata|mediatype"}, headers=UA, timeout=60)
        for p in r.json().get("query", {}).get("pages", {}).values():
            if "imageinfo" not in p: continue
            ii = p["imageinfo"][0]; md = ii.get("extmetadata", {})
            out.append({"title": p["title"], "url": ii["url"], "width": ii.get("width"), "height": ii.get("height"),
                        "duration": round(ii.get("duration") or 0, 1), "license": clean(md.get("LicenseShortName", {}).get("value")),
                        "artist": clean(md.get("Artist", {}).get("value")), "description": clean(md.get("ImageDescription", {}).get("value"))[:200]})
    return out

def license_ok(l):
    l = (l or "").lower()
    return any(l.startswith(x) or x in l for x in OK_LICENSES) and "nc" not in l and "nd" not in l

def search(queries):
    seen, res, u = set(), [], used()
    for q in queries:
        r = httpx.get(API, params={"action": "query", "format": "json", "list": "search", "srsearch": q + " filetype:video",
                                   "srnamespace": 6, "srlimit": 25}, headers=UA, timeout=60)
        titles = [h["title"] for h in r.json().get("query", {}).get("search", []) if h["title"] not in seen]
        seen.update(titles)
        for m in info(titles):
            if m["title"].replace("File:", "") in u or m["title"] in u: continue
            if not license_ok(m["license"]) or not (3 <= m["duration"] <= 240): continue
            m["query"] = q; res.append(m)
    json.dump(res, open("analysis/candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(res)} candidates")
    for m in res: print(f'{m["duration"]:6.1f}s {m["width"]}x{m["height"]} {m["license"]:14s} {m["title"]}')

def download(m):
    p = os.path.join(WORK, slug(m["title"]) + os.path.splitext(m["url"])[1])
    if not os.path.exists(p):
        with httpx.stream("GET", m["url"], headers=UA, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            with open(p, "wb") as f:
                for c in r.iter_bytes(1 << 20): f.write(c)
    return p

def grid(path, t0, t1, n, height, outp):
    d = os.path.join(WORK, "fr"); subprocess.run(["rm", "-rf", d]); os.makedirs(d)
    step = (t1 - t0) / n
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t0:.2f}", "-t", f"{t1 - t0:.2f}", "-i", path,
                    "-vf", f"fps=1/{step:.4f},scale=-2:{height}", os.path.join(d, "f%04d.png")], check=True)
    ims = []
    for i, f in enumerate(sorted(glob.glob(os.path.join(d, "*.png")))[:n]):
        im = Image.open(f).convert("RGB"); dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 74, 22], fill=(0, 0, 0)); dr.text((4, 4), f"{t0 + i * step:.2f}s", fill=(255, 255, 0)); ims.append(im)
    w, h = ims[0].size; cols = 8 if w < h else 5; rows = (len(ims) + cols - 1) // cols
    sh = Image.new("RGB", (w * cols, h * rows))
    for k, im in enumerate(ims): sh.paste(im, ((k % cols) * w, (k // cols) * h))
    sh.save(outp, quality=80); print("wrote", outp, sh.size)

def sheets(titles):
    for m in info(titles):
        try:
            p = download(m)
            grid(p, 0, max(1.0, m["duration"]), 30 if m["duration"] > 8 else 20, 220, f"analysis/{slug(m['title'])}.jpg")
            json.dump(m, open(f"analysis/{slug(m['title'])}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e: print("FAIL", m["title"], e)

def fine(title, t0, t1, fps=4):
    m = info([title])[0]; p = download(m)
    n = int((t1 - t0) * fps)
    grid(p, t0, t1, n, 300, f"analysis/{slug(title)}_fine_{t0:g}-{t1:g}.jpg")

if __name__ == "__main__":
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "search": search(args)
    elif mode == "sheets": sheets([a if a.startswith("File:") else "File:" + a for a in args])
    elif mode == "fine": fine(args[0] if args[0].startswith("File:") else "File:" + args[0], float(args[1]), float(args[2]), float(args[3]) if len(args) > 3 else 4)
