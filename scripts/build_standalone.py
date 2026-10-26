#!/usr/bin/env python3
"""从 docs/index.html 生成可独立分发的单文件版本（docs/standalone.html）。

为什么需要
----------
`docs/index.html` 是配合 GitHub Pages 用的：它用相对路径引用 `evidence-scatter.png`
和 `reflow_sample.md`。这类页面一旦被上传成「资料库网页作品」或任何单文件托管，
相对资源就取不到了——散点图会变成裂图。

本脚本把本地图片内联成 data URI，并改写指向本地文件的链接，产出一个
**自包含**的 HTML（双击就能跑、上传到任何单文件托管都不丢内容）。

设计约束
--------
- 不修改 `docs/index.html` 本体：它与 GitHub Pages 的多文件布局绑定，
  且 `scripts/sync_web_vocab.py` 会往里注入词表，两边各管各的。
- 幂等：重复运行输出一致（无时间戳、无随机量），可在 CI 里比对。
- 只内联图片；不改任何 JS / CSS，避免与词表同步机制漂移。

用法：
    python scripts/build_standalone.py            # 生成
    python scripts/build_standalone.py --check    # 只校验是否已是最新（CI 用）
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SRC = DOCS / "index.html"
OUT = DOCS / "standalone.html"

#: 图片后缀 → MIME
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}

#: 页面里指向本地文件的链接 → 改写成指向仓库里的公开地址。
#: 单文件分发时点这些链接会 404，所以给它们一个不依赖托管布局的落点。
LINK_REWRITES = {
    "reflow_sample.md": "https://github.com/jian935/career-loop/blob/main/docs/reflow_sample.md",
}

BANNER = (
    "<!-- 由 scripts/build_standalone.py 从 docs/index.html 生成，请勿直接编辑；"
    "改 index.html 后重跑脚本。 -->\n"
)

#: 资料库发布态的公开地址（node Jt3O7bi3SUFYI3SG1iOVDE）。
#: 重新发布到新节点时要同步改这里，否则 og:url 会指向旧页面。
PUBLISH_URL = "https://workbuddy.link/p/Jt3O7bi3SUFYI3SG1iOVDE"

#: 封面图的公网直链（资源库静态域，1200×630）。
#: 社媒抓取要求 og:image 是绝对 URL —— 相对路径 `og-cover.png` 会导致卡片无图。
OG_IMAGE_URL = "https://workbuddy-space-static.codebuddy.work/image/yj1WAybxQJLPzXVC8kBIih.png"


def _set_meta(html: str, key: str, value: str) -> str:
    """改写 <meta property|name="key" content="..."> 的 content。"""
    pat = re.compile(
        r'(<meta\s+(?:property|name)="' + re.escape(key) + r'"\s+content=")[^"]*(")'
    )
    return pat.sub(lambda m: m.group(1) + value + m.group(2), html)


def _data_uri(path: Path) -> str:
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def build(src: Path = SRC) -> str:
    html = src.read_text(encoding="utf-8")

    # 1) 内联本地图片：src="foo.png" → src="data:image/png;base64,..."
    def _inline(m: re.Match[str]) -> str:
        quote, name = m.group(1), m.group(2)
        if name.startswith(("http://", "https://", "data:", "//")):
            return m.group(0)
        target = (src.parent / name).resolve()
        if not target.is_file():
            raise SystemExit(f"引用的图片不存在：{name}（期望 {target}）")
        return f"src={quote}{_data_uri(target)}{quote}"

    html = re.sub(
        r'src=(["\'])([^"\']+\.(?:png|jpe?g|gif|svg|webp))\1',
        _inline,
        html,
        flags=re.IGNORECASE,
    )

    # 2) 改写指向本地文本文件的链接
    for local, remote in LINK_REWRITES.items():
        html = html.replace(f'href="{local}"', f'href="{remote}"')

    # 3) 修正社媒元信息（单文件分发后页面换了地址，元数据必须跟着换）
    html = _set_meta(html, "og:url", PUBLISH_URL)
    html = _set_meta(html, "og:image", OG_IMAGE_URL)
    html = _set_meta(html, "twitter:url", PUBLISH_URL)
    html = _set_meta(html, "twitter:image", OG_IMAGE_URL)

    # 4) 标注来源（放在 doctype 之后，不影响渲染）
    if "<!DOCTYPE html>" in html.split("\n", 1)[0]:
        head, _, rest = html.partition("\n")
        html = f"{head}\n{BANNER}{rest}"
    else:
        html = BANNER + html

    return html


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成自包含单文件网页（资料库投稿用）")
    ap.add_argument("--check", action="store_true", help="只校验是否最新，不写文件")
    args = ap.parse_args(argv)

    html = build()
    if args.check:
        if not OUT.is_file():
            print(f"✗ 缺少 {OUT.relative_to(ROOT)}，请先运行 scripts/build_standalone.py")
            return 1
        if OUT.read_text(encoding="utf-8") != html:
            print(f"✗ {OUT.relative_to(ROOT)} 已过期，请重新运行 scripts/build_standalone.py")
            return 1
        print(f"OK {OUT.relative_to(ROOT)} 与 index.html 同步")
        return 0

    OUT.write_text(html, encoding="utf-8")
    src_size = SRC.stat().st_size
    out_size = OUT.stat().st_size
    leftover = re.findall(r'src="(?!data:|https?://)([^"]+)"', html)
    print(f"已生成 {OUT.relative_to(ROOT)}")
    print(f"  index.html      {src_size / 1024:6.1f} KB")
    print(f"  standalone.html {out_size / 1024:6.1f} KB（图片已内联）")
    print(f"  残留外部图片引用：{leftover or '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
