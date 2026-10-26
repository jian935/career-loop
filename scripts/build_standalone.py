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

#: 页面里指向本地文件的链接 → 目标地址。
#: 当前只有 reflow 样例，但它唯一的落点是仓库（尚未推送），
#: 因此不在这里改写成 URL，而是由 STANDALONE_REWRITES 降级成纯文本。
#: 保留这个映射是为了将来有真正可用的落点时直接加一条即可。
LINK_REWRITES: dict[str, str] = {}

#: 单文件分发版要去掉的 GitHub 死链。
#: 仓库尚未推送时，页面上「Star on GitHub / 查看源码 / Benchmark / Docs」点了都是 404，
#: 投稿评审一旦点开就是负面印象。发布版把它们换成页内锚点或直接移除；
#: `docs/index.html` 保持原样——等仓库推上去，Pages 版这些链接自然可用。
STANDALONE_REWRITES: list[tuple[str, str]] = [
    # 导航里两个指向仓库目录的入口
    (
        '    <a href="https://github.com/jian935/career-loop/tree/main/benchmark">Benchmark</a>\n'
        '    <a href="https://github.com/jian935/career-loop/tree/main/docs">Docs</a>\n',
        "",
    ),
    # 右上角主行动按钮：从「去给仓库点星」改成「看证据墙」（本页就有）
    (
        '<a class="star-btn" href="https://github.com/jian935/career-loop" '
        'target="_blank" rel="noopener">★ Star on GitHub</a>',
        '<a class="star-btn" href="#evidence">★ 看证据墙</a>',
    ),
    # hero 次按钮：查看源码 → 看证据墙
    (
        '<a class="btn-ghost" href="https://github.com/jian935/career-loop" '
        'target="_blank" rel="noopener">查看源码</a>',
        '<a class="btn-ghost" href="#evidence">看证据墙</a>',
    ),
    # 页脚：两个仓库链接去掉，保留「复制本页链接」
    (
        '<a href="https://github.com/jian935/career-loop">GitHub</a> · '
        '<a href="https://github.com/jian935/career-loop/tree/main/docs">方法论</a> · ',
        "",
    ),
    # 证据墙里的脱敏样例报告：仓库未推送前没有公开地址，降级成纯文本，不留死链
    (
        '<a href="reflow_sample.md">docs/reflow_sample.md</a>',
        "<code>docs/reflow_sample.md</code>",
    ),
]

BANNER = (
    "<!-- 由 scripts/build_standalone.py 从 docs/index.html 生成，请勿直接编辑；"
    "改 index.html 后重跑脚本。 -->\n"
)

#: 资料库发布态的公开地址（node Jt3O7bi3SUFYI3SG1iOVDE）。
#: 重新发布到新节点时要同步改这里，否则 og:url 会指向旧页面。
PUBLISH_URL = "https://workbuddy.link/p/Jt3O7bi3SUFYI3SG1iOVDE"

#: 封面图的公网直链（资源库静态域，1200×630）。
#: 社媒抓取要求 og:image 是绝对 URL —— 相对路径 `og-cover.png` 会导致卡片无图。
#: 注：实测 workbuddy.link 发布态会覆写 og:image 为平台默认图标，这里的值实际不生效；
#: 仍然写对是为了平台策略变化时不用回头改，且不影响页面本身的渲染。
OG_IMAGE_URL = "https://workbuddy-space-static.codebuddy.work/image/YQRodiSCInA07aGtmqhThx.png"


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

    # 2b) 去掉/替换 GitHub 死链（仓库未推送前，发布版不该出现点了 404 的入口）
    for old, new in STANDALONE_REWRITES:
        html = html.replace(old, new)

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


def _missed_rewrites(src: Path = SRC) -> list[str]:
    """返回在 index.html 里找不到的 GitHub 死链规则。

    页面结构一旦变动，规则可能悄悄失效——死链就会无声地回到发布版。
    所以每次构建都报一次，而不是等评审点开发现 404。
    """
    raw = src.read_text(encoding="utf-8")
    return [old.strip().splitlines()[0][:60] for old, _ in STANDALONE_REWRITES if old not in raw]


def _leftover_github(html: str) -> list[str]:
    """发布版里还剩哪些 github.com 链接（应当只剩 reflow_sample 那个公开文档地址）。"""
    urls = re.findall(r'href="(https://github\.com/[^"]+)"', html)
    return sorted(set(urls))


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
        missed = _missed_rewrites()
        if missed:
            print(f"✗ 有 {len(missed)} 条 GitHub 死链规则没匹配上（页面结构变了？死链会回归）：")
            for m in missed:
                print(f"    - {m}")
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

    missed = _missed_rewrites()
    if missed:
        print(f"  ⚠️ {len(missed)} 条 GitHub 死链规则未命中（页面结构可能变了）：")
        for m in missed:
            print(f"     - {m}")
    remaining = _leftover_github(html)
    if remaining:
        print(f"  发布版保留的 github.com 链接（应只有公开文档）：{remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
