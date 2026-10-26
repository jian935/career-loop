#!/usr/bin/env python3
"""生成小红书用的 3:4 竖版首图（1080x1440）。

设计语言与 docs/og-cover.png 保持一致（深色底 + 紫青渐变 + 细网格），
只改变画幅与文案断行——小红书信息流是竖图，横版 1200x630 会被裁掉两侧。

用法：
    python scripts/make_social_cover.py            # 生成 docs/xhs-cover.png
    python scripts/make_social_cover.py --check    # 只校验已存在且尺寸正确
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "xhs-cover.png"

W, H = 1080, 1440
MARGIN = 84

BG = (11, 13, 20)
GRID = (255, 255, 255)
PURPLE = (168, 150, 255)
CYAN = (120, 224, 224)
WHITE = (245, 247, 252)
MUTED = (150, 158, 178)

FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
]
FONT_CANDIDATES_REG = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
]


def _pick(cands: list[str]) -> str:
    for c in cands:
        if Path(c).exists():
            return c
    raise SystemExit("找不到可用中文字体，请检查 " + " / ".join(cands))


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)

    # 两团柔光：左上偏紫、右下偏青，做出 og-cover 的冷暖对撞
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-360, -420, 620, 460], fill=(56, 34, 108))
    gd.ellipse([W - 520, H - 640, W + 320, H + 220], fill=(16, 66, 74))
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    img = Image.blend(img, Image.blend(img, glow, 0.55), 0.9)

    # 细网格，alpha 极低，避免"脏"
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdr = ImageDraw.Draw(grid)
    for x in range(0, W, 54):
        gdr.line([(x, 0), (x, H)], fill=GRID + (9,))
    for y in range(0, H, 54):
        gdr.line([(0, y), (W, y)], fill=GRID + (9,))
    img = Image.alpha_composite(img.convert("RGBA"), grid).convert("RGB")
    return img


def _gradient_text(img: Image.Image, xy: tuple[int, int], text: str,
                   font: ImageFont.FreeTypeFont, c1: tuple[int, int, int],
                   c2: tuple[int, int, int]) -> None:
    """按文字包围盒铺横向渐变，再贴回底图（只作用在字上）。"""
    bbox = font.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    mask = Image.new("L", (tw + 8, th + 8), 0)
    ImageDraw.Draw(mask).text((4 - bbox[0], 4 - bbox[1]), text, font=font, fill=255)

    grad = Image.new("RGB", (tw + 8, th + 8))
    gp = grad.load()
    for x in range(tw + 8):
        t = x / max(1, tw + 7)
        col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        for y in range(th + 8):
            gp[x, y] = col
    img.paste(grad, (xy[0], xy[1]), mask)


def build() -> Image.Image:
    bold = _pick(FONT_CANDIDATES_BOLD)
    reg = _pick(FONT_CANDIDATES_REG)

    img = _background()
    d = ImageDraw.Draw(img)

    y = 132
    _gradient_text(img, (MARGIN, y), "career-loop",
                   _font(bold, 96), PURPLE, CYAN)

    # 主标题：小红书竖版，一行一个信息点，字数越少越大
    y = 290
    for line, color, size in [
        ("投简历前，", WHITE, 104),
        ("先花 10 秒", WHITE, 104),
        ("看清你差在哪", CYAN, 104),
    ]:
        d.text((MARGIN, y), line, font=_font(bold, size), fill=color)
        y += 126

    # 一句话说明（两行，每行 ≤16 字，保证 1080 宽内不溢出不压卡片）
    y = 712
    for line in ("粘贴 JD + 经历，10 秒拿到",
                 "匹配分、逐项缺口、补强优先级"):
        d.text((MARGIN, y), line, font=_font(reg, 42), fill=MUTED)
        y += 58

    # 三个数据条：竖版三行，高度压到 108 以免顶到底部页脚
    y = 880
    cards = [
        ("69 个岗位族", "AI / 技术 / 财务 / 销售 / 人力 / 设计…"),
        ("180 个能力项", "词表外要求按文本相似度兜底，不丢"),
        ("匹配分可证伪", "用你真实投递结果回算相关系数 r"),
    ]
    for title, sub in cards:
        box = [MARGIN, y, W - MARGIN, y + 112]
        d.rounded_rectangle(box, radius=20, fill=(20, 24, 38), outline=(44, 50, 72), width=2)
        d.text((MARGIN + 40, y + 14), title, font=_font(bold, 44), fill=WHITE)
        d.text((MARGIN + 40, y + 70), sub, font=_font(reg, 26), fill=MUTED)
        y += 132

    # 页脚
    d.line([(MARGIN, H - 150), (W - MARGIN, H - 150)], fill=(46, 52, 74), width=2)
    d.text((MARGIN, H - 118), "纯前端 · 零依赖 · 数据不上传",
           font=_font(reg, 32), fill=MUTED)
    foot = "可打开即用"
    fb = _font(reg, 32).getbbox(foot)
    d.text((W - MARGIN - (fb[2] - fb[0]), H - 118), foot,
           font=_font(reg, 32), fill=(110, 118, 140))

    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验产物尺寸")
    args = ap.parse_args()

    if args.check:
        if not OUT.exists():
            print(f"MISSING {OUT}")
            return 1
        with Image.open(OUT) as im:
            ok = im.size == (W, H)
            print(f"{'OK' if ok else 'BAD'} {OUT.name} {im.size[0]}x{im.size[1]}")
            return 0 if ok else 1

    img = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)}  {W}x{H}  {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
