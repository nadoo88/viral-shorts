"""9:16 쇼츠 렌더러 (PIL + NumPy + FFmpeg stdin 스트리밍)

장면 구성:  배경(스톡 영상 / 켄번스 사진 / 카테고리 그라데이션 카드)
          + 상단 카테고리 배지·제목 바 + 예능 자막(핵심어 노란색, 팝인)
          + 하단 진행바·핸들 워터마크
오디오:    NumPy 합성 BGM (저작권 무관)
"""
from __future__ import annotations

import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIRS = ["/usr/share/fonts/opentype/noto", "/usr/share/fonts/noto-cjk",
             "C:/Windows/Fonts", "/System/Library/Fonts"]
FONT_CANDIDATES = [("NotoSansCJK-Black.ttc", 1), ("NotoSansCJK-Bold.ttc", 1),
                   ("NotoSansKR-Black.otf", 0), ("malgunbd.ttf", 0), ("AppleSDGothicNeo.ttc", 0)]

PALETTE = {  # 카테고리별 (그라데이션 상단, 하단, 배지색)
    "diet": ((255, 94, 98), (255, 153, 102), (255, 70, 90)),
    "workout": ((33, 150, 243), (0, 201, 167), (0, 150, 255)),
    "world": ((58, 28, 113), (215, 109, 119), (130, 80, 255)),
    "home": ((17, 153, 142), (56, 239, 125), (0, 170, 120)),
    "health": ((20, 30, 48), (36, 59, 85), (230, 60, 60)),
}
LABEL = {"diet": "다이어트", "workout": "살빼는운동", "world": "해외이슈", "home": "살림꿀템", "health": "건강"}
YELLOW = (255, 221, 0)


def font(size: int):
    for d in FONT_DIRS:
        for name, idx in FONT_CANDIDATES:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size, index=idx)
    return ImageFont.load_default()


# ── 배경 ───────────────────────────────────────────────────
class Background:
    def __init__(self, media, category, W, H, n_frames, fps):
        self.W, self.H, self.n, self.fps = W, H, n_frames, fps
        self.kind = "card"
        self.frames = None
        if media and media["type"] == "video":
            self.frames = self._decode_video(media["path"])
            if self.frames:
                self.kind = "video"
        elif media and media["type"] == "image":
            self.img = self._cover(Image.open(media["path"]).convert("RGB"), 1.14)
            self.kind = "image"
        if self.kind == "card":
            self._make_card(category)

    def _cover(self, img, zoom=1.0):
        W, H = int(self.W * zoom), int(self.H * zoom)
        s = max(W / img.width, H / img.height)
        img = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
        l, t = (img.width - W) // 2, (img.height - H) // 2
        return img.crop((l, t, l + W, t + H))

    def _decode_video(self, path):
        dur = self.n / self.fps
        cmd = ["ffmpeg", "-v", "error", "-stream_loop", "-1", "-i", path, "-t", f"{dur:.2f}",
               "-vf", f"scale={self.W}:{self.H}:force_original_aspect_ratio=increase,"
                      f"crop={self.W}:{self.H},fps={self.fps}",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        try:
            raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        except subprocess.CalledProcessError:
            return None
        fsz = self.W * self.H * 3
        k = len(raw) // fsz
        return [raw[i * fsz:(i + 1) * fsz] for i in range(k)] or None

    def _make_card(self, category):
        top, bot, _ = PALETTE.get(category, PALETTE["diet"])
        y = np.linspace(0, 1, self.H)[:, None, None]
        grad = (np.array(top) * (1 - y) + np.array(bot) * y).astype(np.uint8)
        self.grad = Image.fromarray(np.repeat(grad, self.W, axis=1))
        big = font(330)
        wm = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(wm)
        word = LABEL.get(category, "")[:2]
        d.text((self.W // 2, self.H // 2 - 80), word, font=big, fill=(255, 255, 255, 38), anchor="mm")
        self.wm = wm

    def frame(self, i):
        if self.kind == "video":
            b = self.frames[min(i, len(self.frames) - 1)]
            return Image.frombytes("RGB", (self.W, self.H), b)
        if self.kind == "image":
            p = i / max(self.n - 1, 1)
            z = 1.14 - 0.10 * p                       # 서서히 줌아웃
            cw = int(self.img.width * (z / 1.14))
            ch = int(self.img.height * (z / 1.14))
            l = int((self.img.width - cw) * (0.5 + 0.3 * (p - 0.5)))
            t = (self.img.height - ch) // 2
            return self.img.crop((l, t, l + cw, t + ch)).resize((self.W, self.H), Image.BILINEAR)
        # 카드: 떠다니는 원 2개
        im = self.grad.copy()
        d = ImageDraw.Draw(im, "RGBA")
        t = i / self.fps
        for k, (r, a) in enumerate([(260, 40), (180, 30)]):
            cx = self.W * (0.25 + 0.5 * k) + 90 * math.sin(t * 0.9 + k)
            cy = self.H * (0.3 + 0.4 * k) + 120 * math.cos(t * 0.7 + k * 2)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, a))
        im.paste(self.wm, (0, 0), self.wm)
        return im


# ── 자막 레이어 ────────────────────────────────────────────
def subtitle_layer(text: str, highlight: str, W: int) -> Image.Image:
    f = font(96)
    lines = [ln for ln in text.split("\n") if ln.strip()][:2] or [" "]
    # 너무 길면 폰트 축소
    maxw = max(f.getlength(ln) for ln in lines)
    if maxw > W - 120:
        f = font(int(96 * (W - 120) / maxw))
    lh = int(f.size * 1.3)
    layer = Image.new("RGBA", (W, lh * len(lines) + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for li, ln in enumerate(lines):
        segs = _split_highlight(ln, highlight)
        total = sum(f.getlength(s) for s, _ in segs)
        x = (W - total) / 2
        y = 30 + li * lh
        for s, hl in segs:
            d.text((x, y), s, font=f, fill=YELLOW if hl else (255, 255, 255),
                   stroke_width=10, stroke_fill=(0, 0, 0))
            x += f.getlength(s)
    shadow = layer.filter(ImageFilter.GaussianBlur(8))
    base = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    base.paste((0, 0, 0, 120), (0, 0), shadow.split()[3])
    base.alpha_composite(layer)
    return base


def _split_highlight(line, hl):
    if not hl or hl not in line:
        return [(line, False)]
    out, rest = [], line
    while hl in rest:
        a, rest = rest.split(hl, 1)
        if a:
            out.append((a, False))
        out.append((hl, True))
    if rest:
        out.append((rest, False))
    return out


def header_layer(category: str, title: str, W: int) -> Image.Image:
    _, _, badge = PALETTE.get(category, PALETTE["diet"])
    layer = Image.new("RGBA", (W, 330), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fb, ft = font(44), font(62)
    lab = LABEL.get(category, category)
    bw = int(fb.getlength(lab)) + 56
    d.rounded_rectangle((60, 120, 60 + bw, 190), 35, fill=badge + (255,))
    d.text((60 + bw / 2, 155), lab, font=fb, fill="white", anchor="mm")
    t = title
    while ft.getlength(t) > W - 120 and len(t) > 4:
        t = t[:-2] + "…"
    d.text((60, 215), t, font=ft, fill="white", stroke_width=6, stroke_fill=(0, 0, 0))
    return layer


# ── BGM 합성 ──────────────────────────────────────────────
def synth_bgm(path: str, seconds: float, sr=44100, bpm=112):
    t = np.arange(int(seconds * sr)) / sr
    beat = 60 / bpm
    chords = [[220.0, 277.18, 329.63], [196.0, 246.94, 293.66],
              [174.61, 220.0, 261.63], [196.0, 246.94, 311.13]]
    out = np.zeros_like(t)
    bar = beat * 4
    for i, ch in enumerate(chords * int(seconds / bar / 4 + 2)):
        s, e = i * bar, (i + 1) * bar
        m = (t >= s) & (t < e)
        if not m.any():
            break
        env = np.clip((t[m] - s) / 0.08, 0, 1) * np.clip((e - t[m]) / 0.2, 0, 1)
        for fq in ch:
            out[m] += 0.08 * env * (np.sin(2 * np.pi * fq * t[m]) + 0.3 * np.sin(4 * np.pi * fq * t[m]))
    # 킥 + 하이햇
    for k in np.arange(0, seconds, beat):
        i0 = int(k * sr)
        n = int(0.18 * sr)
        tt = np.arange(min(n, len(t) - i0)) / sr
        out[i0:i0 + len(tt)] += 0.5 * np.sin(2 * np.pi * (110 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 14)
        h0 = int((k + beat / 2) * sr)
        hn = min(int(0.04 * sr), max(len(t) - h0, 0))
        if hn > 0:
            out[h0:h0 + hn] += 0.05 * np.random.randn(hn) * np.exp(-np.arange(hn) / sr * 90)
    fade = np.clip(np.minimum(t / 0.5, (seconds - t) / 1.2), 0, 1)
    out = np.tanh(out * fade * 1.4) * 0.5
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ── 메인 렌더 ─────────────────────────────────────────────
def render(post: dict, media: list, out_path: str, cfg: dict, handle="@luffynod00", poster_path=None):
    vc = cfg["video"]
    W, H, fps = vc["width"], vc["height"], vc["fps"]
    per = int(vc["seconds_per_scene"] * fps)
    scenes = post["scenes"]
    total = per * len(scenes)
    cat = post["category"]

    header = header_layer(cat, post["title"], W)
    dim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(dim).rectangle((0, 0, W, H), fill=(0, 0, 0, 70))
    grad_top = Image.linear_gradient("L").resize((W, 520)).transpose(Image.FLIP_TOP_BOTTOM)
    top_shade = Image.new("RGBA", (W, 520), (0, 0, 0, 0))
    top_shade.putalpha(grad_top.point(lambda v: int(v * 0.65)))
    fh = font(38)

    audio = out_path.replace(".mp4", ".wav")
    if vc.get("bgm", True):
        synth_bgm(audio, total / fps)

    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if vc.get("bgm", True):
        cmd += ["-i", audio, "-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    for si, sc in enumerate(scenes):
        bg = Background(media[si] if si < len(media) else None, cat, W, H, per, fps)
        sub = subtitle_layer(sc["text"], sc.get("highlight", ""), W)
        for fi in range(per):
            frame = bg.frame(fi).convert("RGBA")
            if bg.kind != "card":
                frame.alpha_composite(dim)
            frame.alpha_composite(top_shade, (0, 0))
            frame.alpha_composite(header, (0, 0))
            # 팝인: 처음 6프레임 스케일 1.25→1.0
            p = min(fi / 6, 1)
            sc_ = 1 + 0.25 * (1 - p) ** 2
            s_img = sub if sc_ == 1 else sub.resize((int(sub.width * sc_), int(sub.height * sc_)), Image.BILINEAR)
            y = int(H * 0.60 - s_img.height / 2)
            frame.alpha_composite(s_img, ((W - s_img.width) // 2, y))
            # 진행바 + 핸들
            g = (si * per + fi + 1) / total
            d = ImageDraw.Draw(frame)
            d.rectangle((0, H - 14, W, H), fill=(255, 255, 255, 60))
            d.rectangle((0, H - 14, int(W * g), H), fill=YELLOW + (255,))
            d.text((W - 50, H - 70), handle, font=fh, fill=(255, 255, 255, 200), anchor="rm",
                   stroke_width=3, stroke_fill=(0, 0, 0))
            rgb = frame.convert("RGB")
            if poster_path and si == 0 and fi == min(per - 1, 12):
                rgb.resize((W // 2, H // 2)).save(poster_path, quality=85)
            proc.stdin.write(rgb.tobytes())
    proc.stdin.close()
    proc.wait()
    if os.path.exists(audio):
        os.remove(audio)
    return out_path


def thumbnail(post: dict, media: list, out_path: str, cfg: dict):
    """X 첨부용 1:1(1080) 이미지 — 영상 못 올릴 때 대체."""
    W = H = 1080
    m0 = next((m for m in media if m), None)
    if m0 and m0["type"] == "image":
        im = Background(m0, post["category"], W, H, 1, 30).frame(0)
    elif m0 and m0["type"] == "video":
        bg = Background(m0, post["category"], W, H, 1, 30)
        im = bg.frame(0)
    else:
        im = Background(None, post["category"], W, H, 1, 30).frame(0)
    im = im.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 90))
    im.alpha_composite(shade)
    im.alpha_composite(header_layer(post["category"], "", W), (0, -60))
    f = font(92)
    words, lines, cur = post["title"].split(" "), [], ""
    for w_ in words:
        if f.getlength((cur + " " + w_).strip()) > W - 140:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    lines.append(cur)
    d = ImageDraw.Draw(im)
    y0 = H / 2 - len(lines) * 60
    hl = post["scenes"][0].get("highlight", "") if post.get("scenes") else ""
    for i, ln in enumerate(lines[:4]):
        segs = _split_highlight(ln, hl)
        x = (W - sum(f.getlength(s) for s, _ in segs)) / 2
        for s, h in segs:
            d.text((x, y0 + i * 120), s, font=f, fill=YELLOW if h else "white",
                   stroke_width=9, stroke_fill=(0, 0, 0))
            x += f.getlength(s)
    im.convert("RGB").save(out_path, quality=92)
    return out_path
