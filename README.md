# cozdil-reels

Free, automated "Gerçek Anlarla İngilizce" Reels for [@cozdil_ingilizce](https://www.instagram.com/cozdil_ingilizce/).

- `tools/commons.py` + **analyze** workflow: find and preview free-licensed (CC0 / PD / CC BY / CC BY-SA) clips on Wikimedia Commons.
- `engine/` + **render** workflow: turn a JSON config in `configs/pending/` into a 1080x1920 reel in `videos/` with a review sheet in `qa/`.
- `used_clips.txt`: clips already used (never reused).

Source clips belong to their authors; every published reel credits the clip, author and license in its caption.
