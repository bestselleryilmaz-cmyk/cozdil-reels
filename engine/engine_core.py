import subprocess, os, re, math, random, time, io, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
IMG_H = 880
BG = (14, 20, 38); YEL = (255, 200, 46); LAV = (190, 176, 255); WHITE = (255, 255, 255); DIM = (150, 160, 190)
SR = 44100
def ease(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)
def eout(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3

class Fonts:
    def __init__(self, paths): self.p = paths; self.c = {}
    def __call__(self, k, s):
        if (k, s) not in self.c:
            f = ImageFont.truetype(self.p[k], s)
            if k in ("en", "serif"):
                try: f.set_variation_by_axes([700 if k == "en" else 900])
                except Exception: pass
            self.c[(k, s)] = f
        return self.c[(k, s)]

def word_times(text, s, e):
    words = text.split(); wts = [len(re.sub(r"[^\w']", "", w)) + 1.5 for w in words]
    tot = sum(wts); out = []; t = s
    for w, k in zip(words, wts):
        d = (e - s) * k / tot; out.append((w, t, t + d)); t += d
    return out

# ---------------- content ----------------
PAIRS = [
 ["Geri çekilin!", "Get back!", "am_michael"],
 ["Üç, iki, bir…", "Three, two, one…", "am_michael"],
 ["İşte gidiyor!", "Here it goes!", "af_heart"],
 ["Aman Tanrım, yıkılıyor!", "Oh my God, it's falling!", "af_heart"],
 ["Şuna bak!", "Look at that!", "am_michael"],
 ["Bunu gördün mü?!", "Did you see that?!", "af_heart"],
 ["Bu inanılmazdı!", "That was insane!", "am_michael"],
]
SRC_A, SRC_FREEZE = 3.3, 8.1          # hook plays src 3.3 -> 8.1 then freezes
FREEZE_OUT = SRC_FREEZE - SRC_A       # 4.8
HOOK_END = 6.2; LEAD = 6.5
HOOK1 = [("BU BİNA", "w", 0.2), ("3 SANİYE SONRA", "w", 0.65), ("YAN YATACAK", "y", 1.15)]
HOOK2 = [("BU ANDA", "w", 4.85), ("İNGİLİZCE", "y", 5.15), ("NE BAĞIRILIR?", "y", 5.45)]
FIN_SRC0, FIN_SRC1 = 3.3, 14.0
FIN_CAPS = [(4.6, 6.6, "Three, two, one…", "Üç, iki, bir…"), (6.75, 7.9, "Here it goes!", "İşte gidiyor!"),
            (7.9, 9.6, "Oh my God, it's falling!", "Aman Tanrım, yıkılıyor!"), (9.6, 11.6, "Did you see that?!", "Bunu gördün mü?!"),
            (11.6, 14.0, "That was insane!", "Bu inanılmazdı!")]
SLOGAN_EN = "Send this to a friend who is learning English!"
SRC_URL = "https://upload.wikimedia.org/wikipedia/commons/6/67/Radio_Network_House_implosion.ogv"
OUT_NAME = "cozdil_bina_hook.mp4"; PANEL_YC = 0.40; LOOP_LEN = 6.3; TOPIC_TAG = "Gerçek Anlarla İngilizce"; CROP_X = 0.5
# ---- override everything from a CFG dict defined before exec() ----
_C = globals().get("CFG")
if _C:
    PAIRS = _C["pairs"]; SRC_A = _C["src_a"]; SRC_FREEZE = _C["src_freeze"]; FREEZE_OUT = SRC_FREEZE - SRC_A
    HOOK_END = FREEZE_OUT + 1.4; LEAD = HOOK_END + 0.3
    HOOK1 = [tuple(x) for x in _C["hook1"]]; HOOK2 = [(a, b, FREEZE_OUT + c) for a, b, c in _C["hook2"]]
    FIN_SRC0, FIN_SRC1 = _C["fin_src0"], _C["fin_src1"]; FIN_CAPS = [tuple(x) for x in _C["fin_caps"]]
    SRC_URL = _C["src_url"]; OUT_NAME = _C["out_name"]; PANEL_YC = _C.get("panel_yc", 0.40); LOOP_LEN = _C.get("loop_len", 6.0)
    QUESTION_AT = _C.get("question_at", FIN_SRC1 - 2.0); CROP_X = _C.get("crop_x", 0.5)
else:
    QUESTION_AT = 12.0

def render(F, src_dir, out, audio_wav, times, fin0, slogan_t, dur):
    n = len(PAIRS)
    srcf = sorted(glob.glob(os.path.join(src_dir, "s_*.jpg"))); SFPS = float(globals().get("SRC_FPS", 25.0))
    fcache = {}
    def src(t, size):
        i = max(0, min(len(srcf) - 1, int(round(t * SFPS))))
        key = (i, size)
        if key not in fcache:
            if len(fcache) > 40: fcache.clear()
            im = Image.open(srcf[i]).convert("RGB")
            if size == "full":
                sw, sh = im.size
                if sw / sh > W / H: nw = int(sh * W / H); x0 = max(0, min(sw - nw, int(sw * CROP_X - nw / 2))); im = im.crop((x0, 0, x0 + nw, sh))
                im = im.resize((W, H), Image.BILINEAR)
            else:
                sw, sh = im.size; ch = int(sw * IMG_H / W)
                if ch <= sh:
                    y0 = int(sh * PANEL_YC - ch / 2); y0 = max(0, min(sh - ch, y0)); im = im.crop((0, y0, sw, y0 + ch))
                else:
                    cw = int(sh * W / IMG_H); x0 = int(sw * CROP_X - cw / 2); x0 = max(0, min(sw - cw, x0)); im = im.crop((x0, 0, x0 + cw, sh))
                im = im.resize((W, IMG_H), Image.BILINEAR)
            fcache[key] = im
        return fcache[key]
    grad = Image.new("RGBA", (W, IMG_H), (0, 0, 0, 0)); gd = ImageDraw.Draw(grad)
    for y in range(IMG_H - 260, IMG_H): gd.line([(0, y), (W, y)], fill=BG + (int(255 * ((y - (IMG_H - 260)) / 260) ** 1.6),))
    topg = Image.new("RGBA", (W, 220), (0, 0, 0, 0)); td = ImageDraw.Draw(topg)
    for y in range(220): td.line([(0, y), (W, y)], fill=(0, 0, 0, int(120 * (1 - y / 220))))
    hgrad = Image.new("RGBA", (W, H), (0, 0, 0, 0)); hd_ = ImageDraw.Draw(hgrad)
    for y in range(1000, H): hd_.line([(0, y), (W, y)], fill=(5, 8, 16, int(215 * min(1, ((y - 1000) / 380)) ** 1.2)))
    chrome = Image.new("RGBA", (W, H), (0, 0, 0, 0)); cd = ImageDraw.Draw(chrome)
    fb = F("brand", 40); tw = cd.textlength("ÇÖZDİL", font=fb)
    cd.rounded_rectangle([40, 48, 40 + tw + 48, 118], radius=35, fill=(14, 20, 38, 220)); cd.text((64, 54), "ÇÖZDİL", font=fb, fill=YEL)
    ft = F("ui", 30); t2 = "Gerçek Anlarla İngilizce"; w2 = cd.textlength(t2, font=ft)
    cd.rounded_rectangle([W - 40 - w2 - 48, 52, W - 40, 114], radius=31, fill=(14, 20, 38, 170)); cd.text((W - 40 - w2 - 24, 62), t2, font=ft, fill=WHITE)
    fh = F("ui", 30); hd = "@cozdil_ingilizce"; cd.text(((W - cd.textlength(hd, font=fh)) / 2, H - 92), hd, font=fh, fill=DIM)
    MAXW = 940; X0 = 70; f_tr = F("tr", 40); f_en = F("en", 76)
    D = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    def wrap(words, f):
        lines, cur = [], []
        for w in words:
            if D.textlength(" ".join(cur + [w]), font=f) <= MAXW or not cur: cur.append(w)
            else: lines.append(cur); cur = [w]
        if cur: lines.append(cur)
        return lines
    blocks = []; y = 0; sp = D.textlength(" ", font=f_en)
    for i, (tr, en, _) in enumerate(PAIRS):
        trl = wrap(tr.split(), f_tr); enl = wrap(en.split(), f_en); wt = word_times(en, *times[i])
        pos = []; yy = len(trl) * 56 + 14; k = 0
        for line in enl:
            x = X0
            for w in line:
                ww = D.textlength(w, font=f_en); pos.append((w, x, yy, ww, wt[k][1], wt[k][2])); x += ww + sp; k += 1
            yy += 100
        blocks.append({"trl": trl, "pos": pos, "y": y, "h": yy + 60}); y += yy + 60
    def draw_block(b, mode, t=0.0):
        img = Image.new("RGBA", (W, b["h"]), (0, 0, 0, 0)); dr = ImageDraw.Draw(img); yy = 0
        for line in b["trl"]:
            dr.text((X0, yy), " ".join(line), font=f_tr, fill=LAV + (255 if mode == "active" else 90,)); yy += 56
        for (w, x, wy, ww, ws, we) in b["pos"]:
            if mode != "active": dr.text((x, wy), w, font=f_en, fill=(255, 255, 255, 70 if mode == "past" else 95)); continue
            if ws <= t < we:
                dr.rounded_rectangle([x - 12, wy + 6, x + ww + 12, wy + 96], radius=18, fill=YEL + (255,)); dr.text((x, wy), w, font=f_en, fill=BG + (255,))
            elif t >= we: dr.text((x, wy), w, font=f_en, fill=WHITE + (255,))
            else: dr.text((x, wy), w, font=f_en, fill=(255, 255, 255, 105))
        return img
    cache = {}
    def blk(i, mode):
        if (i, mode) not in cache: cache[(i, mode)] = draw_block(blocks[i], mode)
        return cache[(i, mode)]
    TXT_TOP, TXT_BOT = IMG_H - 20, H - 150; ANCHOR = 170
    def offset(t):
        idx = 0
        for i in range(n):
            if t >= times[i][0] - 0.25: idx = i
        if idx == 0: return 0.0, idx
        k = eout((t - (times[idx][0] - 0.25)) / 0.45)
        return blocks[idx - 1]["y"] + (blocks[idx]["y"] - blocks[idx - 1]["y"]) * k, idx
    fade = Image.new("RGBA", (W, TXT_BOT - TXT_TOP), (0, 0, 0, 0)); fdd = ImageDraw.Draw(fade)
    for k in range(110):
        a = int(255 * (1 - k / 110) ** 1.3)
        fdd.line([(0, k), (W, k)], fill=BG + (a,)); fdd.line([(0, TXT_BOT - TXT_TOP - 1 - k), (W, TXT_BOT - TXT_TOP - 1 - k)], fill=BG + (a,))
    hc = {}
    def hook_img(txt, st):
        if (txt, st) not in hc:
            kind = "serif" if st == "y" else "brand"; f = F(kind, 150 if st == "y" else 100)
            dd = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
            while dd.textlength(txt, font=f) > W - 100: f = F(kind, f.size - 6)
            tw_ = int(dd.textlength(txt, font=f)); bb = dd.textbbox((0, 0), txt, font=f)
            im = Image.new("RGBA", (tw_ + 40, bb[3] + 30), (0, 0, 0, 0)); di = ImageDraw.Draw(im)
            di.text((24, 9), txt, font=f, fill=(0, 0, 0, 200)); di.text((20, 4), txt, font=f, fill=(YEL if st == "y" else WHITE) + (255,))
            hc[(txt, st)] = im
        return hc[(txt, st)]
    def draw_lines(fr, lines, t, a, yc_mid):
        ims = [hook_img(tx, st) for tx, st, ta in lines]; gap = 2
        tot = sum(i.height for i in ims) + gap * (len(ims) - 1); yc = yc_mid - tot / 2; yend = yc_mid + tot / 2
        for (tx, st, ta), im2 in zip(lines, ims):
            if t >= ta:
                k = min(1.0, (t - ta) / 0.16); sc = 1.35 - 0.35 * eout(k)
                im3 = im2 if k >= 1 else im2.resize((max(1, int(im2.width * sc)), max(1, int(im2.height * sc))), Image.BILINEAR)
                al = min(a, 0.3 + 0.7 * k)
                if al < 1: im3 = im3.copy(); im3.putalpha(im3.getchannel("A").point(lambda v: int(v * al)))
                fr.alpha_composite(im3, (int((W - im3.width) / 2), int(yc + im2.height / 2 - im3.height / 2)))
            yc += im2.height + gap
        return yend
    rnd = random.Random(5)
    def hook_frame(t):
        if t < FREEZE_OUT:
            fr = src(SRC_A + t, "full").convert("RGBA")
        else:
            k = t - FREEZE_OUT; base = src(SRC_FREEZE, "full")
            z = 1.0 + 0.06 * eout(k / 1.2); cw, ch = int(W / z), int(H / z)
            x0 = int((W - cw) * 0.35 + rnd.uniform(-6, 6) * max(0, 1 - k * 2)); y0 = int((H - ch) * 0.4)
            fr = base.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)
            g = fr.convert("L").convert("RGB"); fr = Image.blend(fr, g, min(0.6, k * 2)).convert("RGBA")
            if k < 0.25: fr.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(200 * (1 - k / 0.25)))))
        fr.alpha_composite(hgrad)
        if t < FREEZE_OUT - 1.0:
            a1 = 1.0 if t < FREEZE_OUT - 1.3 else 1 - ease((t - FREEZE_OUT + 1.3) / 0.3)
            draw_lines(fr, HOOK1, t, a1, 1430)
        if t >= FREEZE_OUT:
            yend = draw_lines(fr, HOOK2, t, 1.0, 1400)
            if t > HOOK2[-1][2] + 0.25:
                d = ImageDraw.Draw(fr); fs = F("ui", 42); tx = "Sonuna kadar izle"
                w = d.textlength(tx, font=fs); d.text(((W - w) / 2, yend + 30), tx, font=fs, fill=(235, 238, 250, 235))
        fr.alpha_composite(chrome)
        return fr
    def pill(fr, txt, a, ycen, size=46):
        d = ImageDraw.Draw(fr); f = F("brand", size); w = d.textlength(txt, font=f); x0 = (W - w) / 2 - 36; y0 = ycen - 46
        d.rounded_rectangle([x0, y0, x0 + w + 72, y0 + 92], radius=46, fill=(14, 20, 38, int(225 * a)), outline=YEL + (int(255 * a),), width=5)
        d.text((x0 + 36, y0 + 10), txt, font=f, fill=YEL + (int(255 * a),))
    capc = {}
    def caption(en, tr):
        if (en, tr) not in capc:
            fe = F("brand", 78); ftr = F("tr", 44); dd = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
            while dd.textlength(en, font=fe) > W - 160: fe = F("brand", fe.size - 4)
            we = dd.textlength(en, font=fe); wt_ = dd.textlength(tr, font=ftr)
            im = Image.new("RGBA", (W, 230), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rounded_rectangle([(W - we) / 2 - 34, 10, (W + we) / 2 + 34, 130], radius=28, fill=YEL + (255,))
            d.text(((W - we) / 2, 18), en, font=fe, fill=BG + (255,))
            d.text(((W - wt_) / 2 + 2, 152), tr, font=ftr, fill=(0, 0, 0, 180)); d.text(((W - wt_) / 2, 150), tr, font=ftr, fill=WHITE + (255,))
            capc[(en, tr)] = im
        return capc[(en, tr)]
    def finale_frame(t):
        s = FIN_SRC0 + (t - fin0); fr = src(min(s, FIN_SRC1 - 0.05), "full").convert("RGBA"); fr.alpha_composite(hgrad)
        for (a0, a1, en, tr) in FIN_CAPS:
            if a0 <= s < a1:
                k = eout((s - a0) / 0.18); im = caption(en, tr)
                if k < 1:
                    sc = 0.7 + 0.3 * k; im = im.resize((int(W * sc), int(230 * sc)), Image.BILINEAR)
                fr.alpha_composite(im, (int((W - im.width) / 2), int(1330 + (230 - im.height) / 2)))
        if t - fin0 < 1.6:
            a = 1 - ease((t - fin0 - 1.1) / 0.5); pill(fr, "ŞİMDİ GERÇEK ANI İZLE", a, 300)
        if s >= QUESTION_AT:
            pill(fr, "SEN NE BAĞIRIRDIN? YORUMA YAZ", ease((s - QUESTION_AT) / 0.25), 300, 42)
        fr.alpha_composite(chrome)
        return fr
    def slogan_layer(a, t):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.rectangle([0, 0, W, H], fill=BG + (int(252 * a),))
        pulse = 1 + 0.04 * math.sin(max(0, t) * 6)
        items = (("Bu videoyu İngilizce öğrenen", F("tr", 56), WHITE, 560), ("bir arkadaşına", F("tr", 56), WHITE, 638),
                 ("GÖNDER", F("brand", int(190 * pulse)), YEL, 800),
                 ("Bir sonraki sefer o da ne diyeceğini bilsin.", F("ui", 38), DIM, 960),
                 ("Her gün gerçek anlarla İngilizce için", F("ui", 42), WHITE, 1150), ("TAKİP ET", F("brand", 110), YEL, 1260))
        for txt, f, col, cy in items:
            w = d.textlength(txt, font=f); d.text(((W - w) / 2, cy - f.size / 2), txt, font=f, fill=col + (int(255 * a),))
        return lay
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio_wav,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    LOOP = LOOP_LEN
    for fi in range(int(dur * FPS)):
        t = fi / FPS
        if t < HOOK_END:
            p.stdin.write(hook_frame(t).convert("RGB").tobytes()); continue
        if fin0 <= t < slogan_t - 0.2 + 0.4:
            fr = finale_frame(t)
            if t >= slogan_t - 0.2: fr.alpha_composite(slogan_layer(ease((t - slogan_t + 0.2) / 0.4), t - slogan_t))
            p.stdin.write(fr.convert("RGB").tobytes()); continue
        if t >= slogan_t:
            fr = finale_frame(min(t, slogan_t)); fr.alpha_composite(slogan_layer(1.0, t - slogan_t))
            p.stdin.write(fr.convert("RGB").tobytes()); continue
        fr = Image.new("RGBA", (W, H), BG + (255,))
        lt = (t - HOOK_END) % (2 * LOOP); lt = lt if lt < LOOP else 2 * LOOP - lt   # ping-pong loop of the waiting crowd
        img = src(lt, "panel"); fr.paste(img, (0, 0)); fr.alpha_composite(topg, (0, 0)); fr.alpha_composite(grad, (0, 0))
        off, idx = offset(t)
        win = Image.new("RGBA", (W, TXT_BOT - TXT_TOP), (0, 0, 0, 0))
        for i, b in enumerate(blocks):
            yy = ANCHOR + b["y"] - off
            if yy + b["h"] < 0 or yy > TXT_BOT - TXT_TOP: continue
            win.alpha_composite(draw_block(b, "active", t) if i == idx else blk(i, "past" if i < idx else "future"), (0, int(yy)))
        win.alpha_composite(fade); fr.alpha_composite(win, (0, TXT_TOP)); fr.alpha_composite(chrome)
        pill(fr, "BU ANDA İNGİLİZCE NE DENİR?", 1.0, IMG_H - 150, 40)
        if t > fin0 - 1.4:
            pill(fr, "ŞİMDİ GERÇEK ANI İZLE", ease((t - fin0 + 1.4) / 0.25), IMG_H - 150 - 110, 46)
        d = ImageDraw.Draw(fr)
        d.rounded_rectangle([70, H - 128, W - 70, H - 120], radius=4, fill=(255, 255, 255, 40))
        d.rounded_rectangle([70, H - 128, 70 + max(8, int((W - 140) * min(1, t / dur))), H - 120], radius=4, fill=YEL + (255,))
        if t < HOOK_END + 0.4:
            fr = Image.blend(fr, hook_frame(HOOK_END - 0.01), 1 - ease((t - HOOK_END) / 0.4))
        p.stdin.write(fr.convert("RGB").tobytes())
    p.stdin.close(); p.wait()

# ---------------- audio ----------------
def noise(n, seed): return np.random.RandomState(seed).randn(n).astype(np.float32)
def lowpass(x, k): return np.convolve(x, np.ones(k, dtype=np.float32) / k, mode="same")
def sfx_click():
    n = int(0.06 * SR); tt = np.arange(n) / SR
    return (0.25 * np.sin(2 * np.pi * 900 * tt) * np.exp(-tt * 70)).astype(np.float32)
def sfx_hit():
    n = int(1.4 * SR); tt = np.arange(n) / SR
    y = 0.8 * np.sin(2 * np.pi * (50 + 40 * np.exp(-tt * 8)) * tt) * np.exp(-tt * 3.0) + 0.3 * lowpass(noise(n, 3), 25) * np.exp(-tt * 6)
    return y.astype(np.float32)
def sfx_whoosh(d=0.5):
    n = int(d * SR); env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return (0.25 * lowpass(noise(n, 9), 12) * env).astype(np.float32)
def add(y, s, t, g=1.0):
    i = int(t * SR); m = min(len(s), len(y) - i)
    if m > 0: y[i:i + m] += g * s[:m]
def resample(a, sr_in):
    if sr_in == SR: return a
    n = int(len(a) * SR / sr_in); return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)

def build_audio(tts, orig):   # tts(text, voice) -> (array, sr); orig = mono float32 at SR of source clip
    parts_t = []; t = LEAD; times = []; segs = []
    for tr, en, v in PAIRS:
        a, sr = tts(en, v); a = resample(a, sr) * 1.1
        times.append((t + 0.02, t + len(a) / SR - 0.05)); segs.append((t, a)); t += len(a) / SR + 0.85
    fin0 = t + 0.6
    fin_len = FIN_SRC1 - FIN_SRC0
    sl, ssr = tts(SLOGAN_EN, "am_michael"); sl = resample(sl, ssr)
    slogan_t = fin0 + fin_len + 0.1
    dur = slogan_t + len(sl) / SR + 1.6
    y = np.zeros(int(dur * SR) + SR, np.float32)
    o = lambda s0, s1: orig[int(s0 * SR): int(s1 * SR)]
    a = o(SRC_A, SRC_FREEZE).copy(); fo = int(0.15 * SR); a[-fo:] *= np.linspace(1, 0, fo); add(y, a, 0, 0.75)
    add(y, sfx_hit(), FREEZE_OUT, 0.9); add(y, sfx_whoosh(), FREEZE_OUT - 0.25, 1.0)
    for tx, st, ta in HOOK1 + HOOK2: add(y, sfx_click(), ta)
    amb = o(0.0, 6.3); lp = []
    k = 0
    while LEAD - 0.3 + k * 6.3 < fin0:
        add(y, amb, LEAD - 0.3 + k * 6.3, 0.10); k += 1
    for t0, a in segs: add(y, a, t0)
    add(y, sfx_whoosh(0.6), fin0 - 0.4, 1.2)
    f = o(FIN_SRC0, FIN_SRC1).copy(); fi_ = int(0.2 * SR); f[:fi_] *= np.linspace(0, 1, fi_); f[-fi_:] *= np.linspace(1, 0.2, fi_); add(y, f, fin0, 0.95)
    add(y, sl, slogan_t + 0.2, 1.0)
    return y[: int(dur * SR)], times, fin0, slogan_t, dur

# ---------------- main ----------------
