"""Render one Çözdil "Gerçek An" reel from a JSON config.

usage: python engine/render.py configs/pending/<name>.json
Writes videos/<out_name> and qa/<out_name>.jpg (contact sheet for review).
"""
import json, os, sys, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(sys.argv[1], encoding="utf-8"))
exec(compile(open(os.path.join(HERE, "engine_core.py"), encoding="utf-8").read(), "engine_core", "exec"))

import httpx, numpy as np, soundfile as sf
from PIL import Image, ImageDraw

UA = {"User-Agent": "CozdilReels/1.0 (https://github.com/bestselleryilmaz-cmyk/cozdil-reels)"}
CACHE = os.environ.get("COZDIL_CACHE", os.path.expanduser("~/.cache/cozdil"))
os.makedirs(CACHE, exist_ok=True)
WORK = os.path.join(CACHE, "work"); os.makedirs(WORK, exist_ok=True)

def fetch(url, dest, headers=None):
    if os.path.exists(dest) and os.path.getsize(dest) > 0: return dest
    with httpx.stream("GET", url, headers=headers or {}, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest + ".part", "wb") as f:
            for c in r.iter_bytes(1 << 20): f.write(c)
    os.replace(dest + ".part", dest); return dest

GH = "https://github.com/google/fonts/raw/main/ofl/"
FP = {"tr": "poppins/Poppins-SemiBold.ttf", "en": "lora/Lora%5Bwght%5D.ttf", "brand": "poppins/Poppins-ExtraBold.ttf",
      "ui": "poppins/Poppins-Medium.ttf", "serif": "playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf"}
Fo = Fonts({k: fetch(GH + f, os.path.join(CACHE, k + ".ttf")) for k, f in FP.items()})
fetch("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx", os.path.join(CACHE, "kokoro.onnx"))
fetch("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin", os.path.join(CACHE, "voices.bin"))
from kokoro_onnx import Kokoro
K = Kokoro(os.path.join(CACHE, "kokoro.onnx"), os.path.join(CACHE, "voices.bin"))

def tts(text, v):
    a, sr = K.create(text.replace("…", "..."), voice=v, speed=1.0, lang="en-us"); a = np.asarray(a, np.float32)
    idx = np.where(np.abs(a) > 0.012)[0]; i0, i1 = (idx[0], idx[-1] + 1) if len(idx) else (0, len(a))
    return a[max(0, i0 - 600): i1 + 1500], sr

src = os.path.join(WORK, "src.vid"); srcf = os.path.join(WORK, "srcf")
if os.path.exists(src): os.remove(src)
fetch(SRC_URL, src, UA)
subprocess.run(["rm", "-rf", srcf]); os.makedirs(srcf)
SRC_FPS = eval(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", src],
                              capture_output=True, text=True).stdout.strip().split("\n")[0])
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", "scale=-2:'min(1280,ih)'", "-q:v", "3", os.path.join(srcf, "s_%05d.jpg")], check=True)
orig_wav = os.path.join(WORK, "orig.wav")
has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip()
if has_audio:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(SR), orig_wav], check=True)
    orig, _ = sf.read(orig_wav, dtype="float32")
else:
    orig = np.zeros(int(300 * SR), np.float32)

y, times, fin0, slogan_t, dur = build_audio(tts, orig)
y = y / max(1e-6, float(np.abs(y).max())) * 0.95
raw = os.path.join(WORK, "mix_raw.wav"); mix = os.path.join(WORK, "mix.wav")
sf.write(raw, y, SR)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-ar", str(SR), "-ac", "2", mix], check=True)

os.makedirs("videos", exist_ok=True); os.makedirs("qa", exist_ok=True)
out = os.path.join("videos", OUT_NAME)
t0 = time.time()
render(Fo, srcf, out, mix, times, fin0, slogan_t, dur)
print(f"render {time.time() - t0:.0f}s dur {dur:.1f}s fin0 {fin0:.1f} slogan {slogan_t:.1f}")

# QA contact sheet with timestamps
marks = [0.5, 1.5, FREEZE_OUT - 0.6, FREEZE_OUT + 0.9, times[0][0] + 0.4, times[len(times) // 2][0] + 0.4,
         fin0 + 1.0, fin0 + (FIN_SRC1 - FIN_SRC0) * 0.45, fin0 + (FIN_SRC1 - FIN_SRC0) - 0.5, slogan_t + 1.2]
tiles = []
for s in marks:
    p = os.path.join(WORK, "qa.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, s):.2f}", "-i", out, "-frames:v", "1", p], check=True)
    im = Image.open(p).convert("RGB").resize((270, 480)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 64, 20], fill=(0, 0, 0)); d.text((4, 4), f"{s:.1f}s", fill=(255, 255, 0)); tiles.append(im)
sheet = Image.new("RGB", (270 * 5, 480 * 2))
for i, im in enumerate(tiles): sheet.paste(im, ((i % 5) * 270, (i // 5) * 480))
sheet.save(os.path.join("qa", OUT_NAME.rsplit(".", 1)[0] + ".jpg"), quality=82)
json.dump({"out": out, "duration": round(dur, 1), "fin0": round(fin0, 2), "slogan_t": round(slogan_t, 2),
           "phrase_times": [[round(a, 2), round(b, 2)] for a, b in times]},
          open(os.path.join("qa", OUT_NAME.rsplit(".", 1)[0] + ".json"), "w"), indent=1)
