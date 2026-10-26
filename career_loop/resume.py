"""简历文本抽取：.txt/.md 直读，.docx 零依赖（zip+xml），.pdf 走可选依赖 pypdf。

设计取舍
--------
1. **核心依赖保持 `[]`**。`.docx` 是国内简历最主流的格式，而它本质就是一个
   ZIP 包里的 `word/document.xml`，用标准库 `zipfile` + `xml.etree` 就能解，
   不必为此引入 `python-docx`。
2. **`.pdf` 留作可选依赖**（`pip install career-loop[resume]`）。PDF 要处理压缩流
   与字体编码映射，标准库做不可靠；硬做出来的半吊子解析器比不做更危险——
   它会在没有报错的情况下输出乱码文本，然后静默污染匹配分。
3. **抽不出文字时不猜、不编**。扫描件/图片型 PDF 会抽出空字符串，此时明确报错
   并建议换格式，而不是返回一个空 profile 让引擎打出"全部缺失"的假结论。
4. **解析结果必须可被人工复核**。CLI 的 `parse-resume` 会先把抽到的文本打印出来，
   人看完再决定要不要喂给 `add-profile` / `match`。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

__all__ = [
    "ResumeError",
    "MissingDependency",
    "UnsupportedFormat",
    "extract_text",
    "describe",
    "SUPPORTED_SUFFIXES",
]


class ResumeError(Exception):
    """简历抽取失败（格式不支持 / 文件损坏 / 抽不出文字）。"""


class MissingDependency(ResumeError):
    """该格式需要可选依赖，但当前环境没装。"""


class UnsupportedFormat(ResumeError):
    """后缀不被支持（例如老式二进制 .doc）。"""


#: 直接按纯文本读的后缀
TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".text", ".csv", ".jsonl", ".json"})
#: 全部支持的后缀
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".docx", ".pdf"}

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_INSTALL_HINT = (
    "PDF 解析需要可选依赖 pypdf。装法任选其一：\n"
    "  pip install 'career-loop[resume]'\n"
    "  pip install pypdf\n"
    "或者把简历另存为 .docx / .txt 后用零依赖路径解析。"
)


def _read_plain(path: Path) -> str:
    """按常见中文编码依次尝试，避免一句 UnicodeDecodeError 挡死。"""
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ResumeError(
        f"无法识别文件编码（已试 utf-8 / utf-8-sig / gb18030）：{path.name}。"
        "请另存为 UTF-8 文本后重试。"
    )


def _paragraph_text(par) -> str:
    """按文档顺序拼一个 w:p 里的文字，把 tab/br 还原成制表符与换行。"""
    parts: list[str] = []
    for node in par.iter():
        tag = node.tag
        if tag == _W + "t":
            parts.append(node.text or "")
        elif tag == _W + "tab":
            parts.append("\t")
        elif tag in (_W + "br", _W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _xml_paragraphs(blob: bytes) -> list[str]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(blob)
    except ET.ParseError as exc:  # 损坏的 docx
        raise ResumeError(f"docx 内部 XML 解析失败：{exc}") from exc
    out: list[str] = []
    for par in root.iter(_W + "p"):
        text = _paragraph_text(par).strip()
        if text:
            out.append(text)
    return out


def _read_docx(path: Path) -> str:
    """零依赖解 .docx：读 word/document.xml（含页眉，姓名常放页眉）。"""
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "word/document.xml" not in names:
                raise UnsupportedFormat(
                    f"{path.name} 不是标准 .docx（缺 word/document.xml）。"
                    "若是 WPS 专有格式或 .doc 改名而来，请用 Word/WPS 另存为 .docx。"
                )
            blocks: list[str] = []
            # 页眉/页脚里常有姓名、联系方式，放在正文前
            for name in sorted(n for n in names if n.startswith("word/header")):
                blocks.extend(_xml_paragraphs(zf.read(name)))
            blocks.extend(_xml_paragraphs(zf.read("word/document.xml")))
            # 页脚多是页码，跳过（噪声大于信息）
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormat(
            f"{path.name} 不是有效的 .docx（ZIP 解析失败）。"
            "老式 .doc 是二进制格式，不受支持，请另存为 .docx。"
        ) from exc
    return "\n".join(blocks)


def _read_pdf(path: Path) -> str:
    reader_cls = None
    for mod in ("pypdf", "PyPDF2"):
        try:
            reader_cls = __import__(mod, fromlist=["PdfReader"]).PdfReader
            break
        except ImportError:
            continue
    if reader_cls is None:
        raise MissingDependency(_INSTALL_HINT)

    try:
        reader = reader_cls(str(path))
    except Exception as exc:  # pypdf 的异常类型跨版本不稳定
        raise ResumeError(f"PDF 打开失败（{path.name}）：{exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            ok = reader.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            raise ResumeError(
                f"{path.name} 是加密 PDF，需要密码才能抽取。请提供未加密版本。"
            )

    chunks: list[str] = []
    try:
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
    except Exception as exc:
        raise ResumeError(f"PDF 文本抽取失败（{path.name}）：{exc}") from exc

    text = "\n".join(chunks)
    if not text.strip():
        raise ResumeError(
            f"{path.name} 抽不出任何文字——这通常是扫描件或图片型 PDF（内容是一张图）。\n"
            "请改用 Word 版（.docx）、或在 Word/WPS 里『另存为 PDF』时选择可搜索文本，"
            "或直接粘贴简历正文。"
        )
    return text


def _compress_blank_lines(text: str) -> str:
    """把连续空行压成一个，去掉行尾空白——PDF 抽取常见毛病。"""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(ln)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def extract_text(path: str | Path) -> str:
    """从简历文件抽出纯文本。不支持的后缀抛 :class:`UnsupportedFormat`。"""
    p = Path(path).expanduser()
    if not p.exists():
        raise ResumeError(f"文件不存在：{p}")
    if p.is_dir():
        raise ResumeError(f"这是目录不是文件：{p}")

    suffix = p.suffix.lower()
    if suffix in ({".doc"}):
        raise UnsupportedFormat(
            f"{p.name} 是老的二进制 .doc 格式，不受支持。"
            "请用 Word/WPS 打开后『另存为 .docx』再试——docx 走零依赖解析。"
        )
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFormat(
            f"不支持的文件类型 {suffix or '(无后缀)'}。"
            f"支持：{', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    if suffix in TEXT_SUFFIXES:
        method, text = "text", _read_plain(p)
    elif suffix == ".docx":
        method, text = "docx-stdlib", _read_docx(p)
    else:
        method, text = "pdf-pypdf", _read_pdf(p)

    text = _compress_blank_lines(text)
    if not text.strip():
        raise ResumeError(
            f"{p.name} 解析结果为空。请打开确认文件里确有文字内容。"
        )
    return text


def describe(path: str | Path) -> dict:
    """抽取并返回可展示的元信息（供 CLI --json 与自检使用）。"""
    p = Path(path).expanduser()
    suffix = p.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        method = "text"
    elif suffix == ".docx":
        method = "docx-stdlib"
    elif suffix == ".pdf":
        method = "pdf-pypdf"
    else:
        method = "unsupported"

    text = extract_text(p)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    return {
        "path": str(p),
        "suffix": suffix,
        "method": method,
        "chars": len(text),
        "lines": len(lines),
        "zero_dependency": method in {"text", "docx-stdlib"},
        "text": text,
    }
