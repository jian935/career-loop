# -*- coding: utf-8 -*-
"""career-loop 演示视频：真实网页界面 + 语音解说 + 逐词同步字幕（无弹幕）。

三个原则：
1. 画面 = 用 CDP 按 1280x720 视口截的**真实页面**（scripts/shoot_web_shots.mjs），
   与别人用浏览器打开看到的完全一致，不是画的模拟图；
2. 配音 = edge-tts，并取 **WordBoundary 词级时间戳**（offset + duration）；
3. 字幕 = 每个字的高亮由词级时间戳驱动，**念到哪个词哪个词变色**，
   不是按字数比例估算——所以音画严格对得上。

用法：
    python scripts/make_demo_video.py --dry-run     # 只合成音频、打印字幕时间轴
    python scripts/make_demo_video.py --out X.mp4   # 出片
"""

import argparse
import asyncio
import json
import re
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 24
VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+8%"

WORK = Path(r"E:\ps\工作区\35-career-loop视频v2")
SHOTS = Path(r"E:\Agent\career-loop\.tmp\vid\shots")
FF = imageio_ffmpeg.get_ffmpeg_exe()
URL_TEXT = "workbuddy.link/p/Jt3O7bi3SUFYI3SG1iOVDE"

C_CYAN = (125, 232, 255)
C_VIOLET = (167, 139, 250)
C_WHITE = (240, 244, 250)
C_SPOKEN = (132, 238, 255)   # 已念过的字（亮青）
C_PENDING = (146, 158, 176)  # 还没念的字（压暗，高亮才明显）

FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"


def F(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


# ---------------------------------------------------------------- 分镜
SCENES = [
    {
        "key": "hero",
        "img": "s1_hero.png",
        "vo": "投简历之前，先别急着投。这个工具只做一件事："
              "把「我适不适合这个岗位」这句感觉，变成可以证伪的数据。"
              "所有计算都在你的浏览器里完成，数据不上传。",
    },
    {
        "key": "app",
        "img": "s2_app.png",
        "vo": "左边贴岗位描述，右边贴你的经历，十秒钟出这个加权匹配分。"
              "这个例子是 AI 产品经理岗，三十八点九分。"
              "注意它没有只丢给你一个数字，它把每一项能力拆开，"
              "标出哪些缺失、哪些只是部分满足、哪些已经具备。",
    },
    {
        "key": "gap",
        "img": "s3_gap.png",
        "vo": "更关键的是下面这一块：最划算的补强。"
              "它算的是反事实——如果我把这一项补到已具备，分数会涨多少。"
              "大模型原理与边界，涨十一点一分。"
              "补哪一项最值得，是算出来的，不是感觉出来的。",
    },
    {
        "key": "decide",
        "img": "s4_decide.png",
        "vo": "同一份经历还可以横向比：现在就能投哪些，"
              "哪些岗位只差一项就够得着，差的那一项是什么，也写明白了。",
    },
    {
        "key": "evid",
        "img": "s5_evid.png",
        "vo": "接下来是最容易被质疑的地方，我把数字全部摊开。"
              "九十三点六，是英文岗位族的识别准确率；八十六点零，是中文的，都来自公开数据集。"
              "而 Pearson r 只有零点一九三，我不打算把它说漂亮。"
              "更低的那一格是我自己的坏消息：四十条真实投递，相关系数是负的，负零点零五九。"
              "失败区间也一起公开，这才叫可证伪。",
    },
    {
        "key": "reflow",
        "img": "s6_reflow.png",
        "vo": "这一份是真实回流报告：五十条投递记录，offer 率百分之十四。"
              "当相关系数接近零的时候，它不会硬解释成「分数没用」，"
              "而是先看分布——正反馈和负反馈的中位分几乎重叠，"
              "说明这批结果本来就跟岗位契合度无关。这才是数据该有的样子。",
    },
    {
        "key": "calib",
        "img": "s7_calib.png",
        "vo": "最后，这个工具需要你自己来校准。每投一次，"
              "把当时的匹配分和真实结果记下来。攒够十五条，"
              "它就会算出你的匹配分到底准不准。全部存在浏览器本地，不上传、不联网。",
    },
    {
        "key": "end",
        "img": "s1_hero.png",
        "vo": "career-loop：先看清差在哪，再决定投不投。链接就在下面。",
    },
]



# ---------------------------------------------------------------- TTS
async def _tts_one(text: str, mp3: Path) -> list:
    """合成一段，返回 [[起始秒, 时长秒, 词], ...]。

    注意：edge-tts 默认 boundary="SentenceBoundary" 只给句级时间戳，
    要逐词同步必须显式要 WordBoundary。
    """
    import edge_tts

    comm = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset / duration 的单位是 100 纳秒
                words.append([chunk["offset"] / 1e7, chunk["duration"] / 1e7, chunk["text"]])
    return words


def probe_duration(path: Path) -> float:
    """imageio_ffmpeg 只带 ffmpeg 没带 ffprobe，从 -i 的 stderr 里读时长。"""
    r = subprocess.run([FF, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError(f"读不出时长：{path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def tts_all(scenes):
    WORK.mkdir(parents=True, exist_ok=True)
    out = []
    for sc in scenes:
        mp3 = WORK / f"vo_{sc['key']}.mp3"
        words = asyncio.run(_tts_one(sc["vo"], mp3))
        dur = probe_duration(mp3)
        out.append({"scene": sc, "mp3": mp3, "duration": dur, "words": words})
        print(f"  ✓ {sc['key']:8s} {dur:6.2f}s  {len(words):3d} 词  {mp3.stat().st_size // 1024} KB")
    return out


# ---------------------------------------------------------------- 字幕时间轴
BREAK = "，。：；、！？"
MAXLEN = 24   # 单行字幕最多这么多字，30px 字号下正好排得下


def split_units(vo: str):
    """切成最小语义片段（在逗号/句号等标点处断开），返回字符区间。"""
    units, start = [], 0
    for i, ch in enumerate(vo):
        if ch in BREAK:
            units.append((start, i + 1))
            start = i + 1
    if start < len(vo):
        units.append((start, len(vo)))
    return [(a, b) for (a, b) in units if vo[a:b].strip()]


def build_lines(vo: str):
    """把片段贪心合并成字幕行：不超过 MAXLEN 字，句末标点强制断行。"""
    lines, cur_a, cur_b = [], None, None
    for a, b in split_units(vo):
        if cur_a is None:
            cur_a, cur_b = a, b
            continue
        prev_end = vo[cur_b - 1]
        if (b - cur_a) <= MAXLEN and prev_end not in "。！？；":
            cur_b = b
        else:
            lines.append((cur_a, cur_b))
            cur_a, cur_b = a, b
    if cur_a is not None:
        lines.append((cur_a, cur_b))
    return lines


def sentence_timeline(vo: str, words):
    """把词级时间戳落到字幕行上。

    做法：按顺序在原文里定位每个词，拿到它的字符区间；再把字幕行的字符区间
    和词区间相交，得到这一行由哪些词构成、从第几秒念到第几秒。
    """
    wranges = []
    pos = 0
    for t, d, w in words:
        i = vo.find(w, pos)
        if i < 0:
            i = vo.find(w)  # 标点/空白可能不在词序列里，退一步全局找
        if i < 0:
            continue
        wranges.append((i, i + len(w), t, d, w))
        pos = i + len(w)

    out = []
    for a, b in build_lines(vo):
        inside = [(t, t + d, w, c0, c1) for (c0, c1, t, d, w) in wranges
                  if c1 > a and c0 < b]
        if not inside:
            continue
        out.append({
            "text": vo[a:b].strip(),
            "vo": vo,
            "a": a,
            "b": b,
            "start": inside[0][0],
            "end": max(x[1] for x in inside),
            "words": inside,
        })
    return out


def caption_segments(sent):
    """把一行拆成绘制片段：词 + 词之间的标点/空白。

    只画词会把标点丢掉（TTS 的 WordBoundary 不含标点），字幕就成了
    「八十六点零是中文的都来自公开数据集」这种没逗号的怪句子。
    标点跟随它前面那个词的进度——念完前一个词，逗号就跟着高亮。
    """
    vo, a, b, words = sent["vo"], sent["a"], sent["b"], sent["words"]
    if not words:
        return [(vo[a:b], 0.0, 0.0)]

    segs, pos = [], a
    if words[0][3] > a:  # 行首残留（通常是引号）
        segs.append((vo[a:words[0][3]], words[0][0], words[0][0]))
        pos = words[0][3]

    for i, (t0, t1, w, c0, c1) in enumerate(words):
        if c0 > pos:  # 词与词之间的标点
            pt = words[i - 1][1] if i > 0 else t0
            segs.append((vo[pos:c0], pt, pt))
        segs.append((w, t0, t1))
        pos = c1

    if b > pos:  # 行尾残留（句号、引号）
        segs.append((vo[pos:b], words[-1][1], words[-1][1]))
    return segs


# ---------------------------------------------------------------- 画面
def draw_caption_karaoke(frame, sent, now_rel):
    """底部字幕：整行常显，念到的片段变青色（词级驱动，不是按字数估）。"""
    if not sent:
        return frame
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    segs = caption_segments(sent)
    if not segs:
        return frame

    text = "".join(s[0] for s in segs).strip()
    size = 30
    f = F(size, True)
    while d.textlength(text, font=f) > W - 150 and size > 20:
        size -= 1
        f = F(size, True)

    total_w = sum(d.textlength(s[0], font=f) for s in segs)
    x = (W - total_w) / 2
    y = H - 62

    d.rounded_rectangle([x - 26, y - 12, x + total_w + 26, y + size + 14],
                        radius=12, fill=(4, 6, 11, 212))

    # 逐片段绘制，按时间做连续渐变（不是突然跳色）
    cur = x
    for (chunk, t0, t1) in segs:
        if now_rel >= t1:
            color = C_SPOKEN
        elif now_rel <= t0:
            color = C_PENDING
        else:
            k = (now_rel - t0) / max(1e-6, t1 - t0)
            color = tuple(int(C_PENDING[i] + (C_SPOKEN[i] - C_PENDING[i]) * k) for i in range(3))
        d.text((cur, y), chunk, font=f, fill=color + (255,))
        cur += d.textlength(chunk, font=f)
    return Image.alpha_composite(frame.convert("RGBA"), layer)


def draw_progress(frame, prog):
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, W, 3], fill=(255, 255, 255, 26))
    d.rectangle([0, 0, int(W * prog), 3], fill=C_VIOLET + (255,))
    return Image.alpha_composite(frame.convert("RGBA"), layer)


def draw_endcard(frame, k):
    """收尾卡：解说里说「链接就在下面」，画面上就必须真有链接。"""
    if k <= 0:
        return frame
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, W, H], fill=(4, 6, 12, int(224 * k)))

    a = int(255 * k)
    f_name, f_sub, f_link, f_tiny = F(62, True), F(29), F(34, True), F(21)

    name = "career-loop"
    tw = d.textlength(name, font=f_name)
    d.text(((W - tw) / 2, 168), name, font=f_name, fill=C_WHITE + (a,))

    sub = "先看清差在哪，再决定投不投"
    tw = d.textlength(sub, font=f_sub)
    d.text(((W - tw) / 2, 256), sub, font=f_sub, fill=(152, 164, 182, a))

    tw = d.textlength(URL_TEXT, font=f_link)
    bx0, bx1 = (W - tw) / 2 - 34, (W + tw) / 2 + 34
    d.rounded_rectangle([bx0, 328, bx1, 400], radius=14,
                        fill=(24, 18, 48, int(238 * k)),
                        outline=C_VIOLET + (int(205 * k),), width=2)
    d.text(((W - tw) / 2, 344), URL_TEXT, font=f_link, fill=C_CYAN + (a,))

    tiny = "69 个岗位族 · 纯前端 · 数据不上传"
    tw = d.textlength(tiny, font=f_tiny)
    d.text(((W - tw) / 2, 438), tiny, font=f_tiny, fill=(124, 136, 154, a))
    return Image.alpha_composite(frame.convert("RGBA"), layer)


def build_timeline(tts_items, gap=0.45):
    tl, t = [], 0.0
    for it in tts_items:
        d = it["duration"] + gap
        tl.append({"item": it, "start": t, "end": t + d, "dur": d})
        t += d
    return tl, t


def render(timeline, total, out_path):
    imgs = {}
    for it in timeline:
        p = SHOTS / it["item"]["scene"]["img"]
        imgs[p.name] = Image.open(p).convert("RGB")

    writer = imageio.get_writer(
        str(out_path), fps=FPS, codec="libx264", quality=8,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20"],
    )

    for it in timeline:
        sc = it["item"]["scene"]
        sents = sentence_timeline(sc["vo"], it["item"]["words"])
        f0 = int(round(it["start"] * FPS))
        f1 = int(round(it["end"] * FPS))
        base = imgs[Path(sc["img"]).name]
        last_end = sents[-1]["end"] if sents else 0.0

        for fi in range(f0, f1):
            p = (fi - f0) / max(1, f1 - f0)
            now_rel = fi / FPS - it["start"]

            # Ken Burns：1.00 -> 1.05 缓慢推近
            z = 1.0 + 0.05 * p
            cw, ch = W / z, H / z
            x0, y0 = (W - cw) / 2, (H - ch) * 0.42
            frame = base.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)

            if sc["key"] == "end":
                frame = draw_endcard(frame, min(1.0, max(0.0, (p - 0.26) / 0.22)))

            # 当前句：念完再留 0.35s，方便看清最后几个字
            cur_sent = None
            for s in sents:
                if s["start"] <= now_rel < s["end"] + 0.35:
                    cur_sent = s
                    break
            if cur_sent is None and sents and now_rel < last_end + 0.45:
                cur_sent = sents[-1]

            frame = draw_caption_karaoke(frame, cur_sent, now_rel)
            frame = draw_progress(frame, min(1.0, fi / max(1, total * FPS)))

            if now_rel < 0.28:  # 场景开头淡入
                frame = Image.blend(Image.new("RGB", (W, H), (7, 9, 14)),
                                    frame.convert("RGB"), now_rel / 0.28)

            writer.append_data(np.asarray(frame.convert("RGB")))
            if fi % 240 == 0:
                print(f"    渲染 {fi}/{int(total * FPS)}  ({fi / FPS:.0f}s)", flush=True)

    writer.close()
    print(f"  ✓ 画面完成 {out_path}")


def build_audio(timeline, total, out_wav):
    seg_dir = WORK / "segs"
    seg_dir.mkdir(exist_ok=True)
    seg_files = []
    for i, it in enumerate(timeline):
        seg = seg_dir / f"seg{i:02d}.wav"
        subprocess.run([
            FF, "-v", "error", "-y", "-i", str(it["item"]["mp3"]),
            "-af", f"apad=whole_dur={it['dur']:.3f}",
            "-ar", "44100", "-ac", "1", str(seg),
        ], check=True)
        seg_files.append(seg)
    lst = WORK / "segs.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_files), encoding="utf-8")
    subprocess.run([
        FF, "-v", "error", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lst), "-c", "copy", str(out_wav),
    ], check=True)
    print(f"  ✓ 音轨 {out_wav.name}  {probe_duration(out_wav):.2f}s（目标 {total:.2f}s）")


def mux(video, audio, out):
    subprocess.run([
        FF, "-v", "error", "-y", "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", str(out),
    ], check=True)
    print(f"  ✓ 成片 {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WORK / "demo.mp4"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("[1/5] 合成语音")
    tts_items = tts_all(SCENES)

    timeline, total = build_timeline(tts_items)
    print(f"\n[2/5] 字幕时间轴  共 {total:.1f}s / {len(timeline)} 段")
    dbg = []
    for it in timeline:
        sc = it["item"]["scene"]
        sents = sentence_timeline(sc["vo"], it["item"]["words"])
        print(f"  {sc['key']}")
        for s in sents:
            print(f"    {s['start']:6.2f}→{s['end']:6.2f}  {s['text']}")
        dbg.append({"key": sc["key"], "start": it["start"], "sentences": sents})

    (WORK / "timeline.json").write_text(
        json.dumps({"total": total, "scenes": dbg}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    if args.dry_run:
        print("\n--dry-run：只合成音频，不渲染画面")
        return

    print("\n[3/5] 音轨")
    wav = WORK / "mix.wav"
    build_audio(timeline, total, wav)

    print("\n[4/5] 渲染画面")
    silent = WORK / "silent.mp4"
    render(timeline, total, silent)

    print("\n[5/5] 混流")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    mux(silent, wav, out)
    print(f"\n完成：{out}  {probe_duration(out):.1f}s  {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
