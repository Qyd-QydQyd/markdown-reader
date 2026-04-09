from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_MD_PATH = os.environ.get("MD_READER_DEFAULT_FILE")
PDF_HELPER_PATH = Path(
    os.environ.get(
        "MD_READER_PDF_HELPER",
        str(PROJECT_DIR / ("html_to_pdf.exe" if os.name == "nt" else "html_to_pdf")),
    )
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[(.*?)\]\((.*?)\)")
LINK_RE = re.compile(r"\[(.*?)\]\((.*?)\)")
HTML_IMG_SRC_RE = re.compile(r'(<img\b[^>]*\bsrc=["\'])([^"\']+)(["\'])', re.I)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
STRONG_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
EM_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
BLOCK_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$")
ESCAPED_BLOCK_MATH_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
ESCAPED_INLINE_MATH_RE = re.compile(r"\\\((.+?)\\\)")
PROMPT_LINE_RE = re.compile(
    r"请尊重原(?:意|文(?:含义)?)，保持原有格式(?:，|,)?(?:并)?(?:(?:以)?简体中文(?:重写|改写)|将以下内容改写为简体中文)(?:以下内容)?(?:（[^）]*）)?[。.]?"
)
HTML_BLOCK_START_RE = re.compile(r"^\s*<(table|thead|tbody|tr|td|th|figure|figcaption|img|div|p|span|ul|ol|li|blockquote)\b", re.I)
HTML_BLOCK_END_RE = re.compile(r"</(table|thead|tbody|tr|td|th|figure|figcaption|div|p|span|ul|ol|li|blockquote)>\s*$", re.I)
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
SPACED_LETTERS_RE = re.compile(r"(?<![A-Za-z])([A-Za-z])(?:\s+([A-Za-z]))+(?![A-Za-z])")
MATH_TEXT_COMMAND_RE = re.compile(r"\\(text|mathrm|mathbf|mathit|operatorname|mathrm|bf|rm)\s*\{([^{}]+)\}")
TABULAR_RE = re.compile(r"\\begin\{tabular\}\{([^}]*)\}(.*?)\\end\{tabular\}", re.DOTALL)
LATEX_ROW_SPLIT_RE = re.compile(r"(?<!\\)\\\\")
MULTICOLUMN_RE = re.compile(r"\\multicolumn\{(\d+)\}\{[^}]*\}\{(.*?)\}", re.DOTALL)
FIGURE_RE = re.compile(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", re.DOTALL)
INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
CAPTION_RE = re.compile(r"\\caption\{(.*?)\}", re.DOTALL)
REFERENCE_LINE_RE = re.compile(r"^\s*\[\d+\]\s+")
REFERENCE_SPLIT_RE = re.compile(r"^\s*(\[\d+\])\s+(.*)$")
CITATION_RE = re.compile(r"(?<!\!)\[(\d+(?:\s*,\s*\d+)*(?:\s*[–-]\s*\d+)?)\]")
TOC_LIKE_LINE_RE = re.compile(r"^\s*(?:\d+\.\s+|[A-Za-z]\.\s+|[•\-*]\s+)")
TOC_SECTION_TITLE_RE = re.compile(r"^(contents|content|目录|内容)$", re.I)
REFERENCE_SECTION_TITLE_RE = re.compile(r"^(references|reference|参考文献)$", re.I)
TOC_MAJOR_RE = re.compile(r"^#\s*(\d+)\s+(.+?)\s+(\d+)\s*$")
TOC_MINOR_RE = re.compile(r"^(\d+(?:\.\d+)+)\s+(.+?)\s+(\d+)\s*$")
TOC_ENTRY_START_RE = re.compile(r"(?:(?<=^)|(?<=\s))(?P<prefix>#\s*)?(?P<number>\d+(?:\.\d+)*)\s+(?=[^\d#])")

ASSET_SEARCH_CACHE: dict[tuple[str, str], Path | None] = {}


def find_browser_pdf_binary() -> Path | None:
    env_path = os.environ.get("MD_READER_BROWSER")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists():
            return candidate.resolve()

    executable_names = [
        "msedge",
        "microsoft-edge",
        "chrome",
        "google-chrome",
        "chromium",
        "chromium-browser",
    ]
    for name in executable_names:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()

    if sys.platform == "win32":
        program_files = [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LocalAppData"),
        ]
        candidates = [
            Path(root) / "Microsoft/Edge/Application/msedge.exe"
            for root in program_files
            if root
        ] + [
            Path(root) / "Google/Chrome/Application/chrome.exe"
            for root in program_files
            if root
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()

    return None


def export_pdf_with_browser(url: str, output_path: Path) -> subprocess.CompletedProcess[str]:
    browser = find_browser_pdf_binary()
    if not browser:
        raise RuntimeError("未找到可用于导出 PDF 的浏览器（Chrome / Edge / Chromium）")

    commands = [
        [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-features=Translate,BackForwardCache",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=12000",
            f"--print-to-pdf={output_path}",
            "--no-pdf-header-footer",
            url,
        ],
        [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=12000",
            f"--print-to-pdf={output_path}",
            "--no-pdf-header-footer",
            url,
        ],
    ]

    last_result: subprocess.CompletedProcess[str] | None = None
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        last_result = result
        if result.returncode == 0 and output_path.exists():
            return result

    assert last_result is not None
    return last_result


def slugify(text: str) -> str:
    normalized = re.sub(r"<[^>]+>", "", text).strip().lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    return normalized or "section"


def resolve_markdown_path(raw_path: str) -> Path:
    path = Path(os.path.expanduser(raw_path)).resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"未找到文件: {path}")
    return path


def preprocess_markdown(markdown_text: str) -> str:
    cleaned_lines: list[str] = []
    blank_pending = False

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if PROMPT_LINE_RE.fullmatch(stripped):
            continue

        cleaned_line = PROMPT_LINE_RE.sub("", line).rstrip()
        if not cleaned_line.strip():
            if not blank_pending:
                cleaned_lines.append("")
                blank_pending = True
            continue

        cleaned_lines.append(cleaned_line)
        blank_pending = False

    return replace_tabular_environments("\n".join(cleaned_lines))


def normalize_math_content(content: str) -> str:
    normalized = content.strip()

    def collapse_spaced_letters(text: str) -> str:
        previous = None
        current = text
        while previous != current:
            previous = current
            current = SPACED_LETTERS_RE.sub(lambda m: "".join(m.group(0).split()), current)
            current = re.sub(r"([A-Za-z])\s+\\_", r"\1\\_", current)
            current = re.sub(r"\\_\s+([A-Za-z])", r"\\_\1", current)
        return current

    normalized = collapse_spaced_letters(normalized)
    normalized = MATH_TEXT_COMMAND_RE.sub(
        lambda m: rf"\{m.group(1)}{{{collapse_spaced_letters(m.group(2))}}}",
        normalized,
    )

    normalized = re.sub(r"\\mathrm\s*\{\s*-\s*\}", "-", normalized)
    normalized = re.sub(r"\\mathrm\s*\{\s*([A-Za-z]+(?:\s+[A-Za-z]+)*)\s*\}", lambda m: rf"\mathrm{{{m.group(1).replace(' ', '')}}}", normalized)
    normalized = re.sub(r"\\([A-Za-z]+)\s+\{", r"\\\1{", normalized)
    normalized = re.sub(r"\{\s*\\([A-Za-z]+)\s*\}", r"\\\1", normalized)
    normalized = re.sub(r"\{\s+", "{", normalized)
    normalized = re.sub(r"\s+\}", "}", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\s*([=+\-/%])\s*", r"\1", normalized)
    normalized = re.sub(r"(?<=\d)\s+(?=\d)", "", normalized)
    normalized = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", normalized)
    normalized = re.sub(r"(?<=\d)\s+\\%", r"\\%", normalized)
    normalized = re.sub(r"(?<=\d)\s+\\mu", r"\\mu", normalized)
    normalized = re.sub(r"(?<=\\mu)\s+\\mathrm", r"\\mathrm", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_math_fragment(fragment: str) -> str:
    if fragment.startswith("$$") and fragment.endswith("$$"):
        return "$$" + normalize_math_content(fragment[2:-2]) + "$$"
    if fragment.startswith("$") and fragment.endswith("$"):
        return "$" + normalize_math_content(fragment[1:-1]) + "$"
    if fragment.startswith(r"\[") and fragment.endswith(r"\]"):
        return r"\[" + normalize_math_content(fragment[2:-2]) + r"\]"
    if fragment.startswith(r"\(") and fragment.endswith(r"\)"):
        return r"\(" + normalize_math_content(fragment[2:-2]) + r"\)"
    return fragment


def apply_inline_markup(text: str, doc_path: Path, render_citations: bool = True) -> str:
    math_placeholders: list[str] = []

    def stash_math(raw: str, display_mode: bool) -> str:
        normalized_raw = normalize_math_fragment(raw)
        math_placeholders.append(
            f'<span class="math-fragment{" math-display" if display_mode else ""}">{normalized_raw}</span>'
        )
        return f"@@MATH{len(math_placeholders) - 1}@@"

    text = BLOCK_MATH_RE.sub(lambda m: stash_math(m.group(0), True), text)
    text = ESCAPED_BLOCK_MATH_RE.sub(lambda m: stash_math(m.group(0), True), text)
    text = INLINE_MATH_RE.sub(lambda m: stash_math(m.group(0), False), text)
    text = ESCAPED_INLINE_MATH_RE.sub(lambda m: stash_math(m.group(0), False), text)

    escaped = html.escape(text)

    def replace_image(match: re.Match[str]) -> str:
        alt_text = html.escape(match.group(1))
        target = match.group(2).strip()
        asset_url = build_asset_url(doc_path, target)
        return f'<figure><img src="{asset_url}" alt="{alt_text}" loading="lazy"></figure>'

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        target = html.escape(match.group(2).strip(), quote=True)
        return f'<a href="{target}" target="_blank" rel="noreferrer">{label}</a>'

    escaped = IMAGE_RE.sub(replace_image, escaped)
    escaped = LINK_RE.sub(replace_link, escaped)
    if render_citations:
        escaped = CITATION_RE.sub(r"<sup class=\"citation\">[\1]</sup>", escaped)
    escaped = INLINE_CODE_RE.sub(lambda m: f"<code>{html.escape(m.group(1))}</code>", escaped)
    escaped = STRONG_RE.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", escaped)
    escaped = EM_RE.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", escaped)
    for index, fragment in enumerate(math_placeholders):
        escaped = escaped.replace(f"@@MATH{index}@@", fragment)
    return escaped


def build_asset_url(doc_path: Path, raw_target: str) -> str:
    encoded_doc = urllib.parse.quote(str(doc_path))
    encoded_target = urllib.parse.quote(raw_target)
    return f"/asset?doc={encoded_doc}&target={encoded_target}"


def resolve_asset_path(doc_path: Path, raw_target: str) -> Path | None:
    if raw_target.startswith(("http://", "https://", "data:")):
        return None

    candidate = (doc_path.parent / raw_target).resolve()
    if candidate.exists() and candidate.is_file():
        return candidate

    basename = Path(raw_target).name
    fallback_candidates = [
        doc_path.parent / "images" / basename,
        doc_path.parent / f"{doc_path.stem}_files" / "images" / basename,
        doc_path.parent / f"{doc_path.stem}_images" / basename,
        doc_path.parent / basename,
    ]

    for fallback in fallback_candidates:
        fallback = fallback.resolve()
        if fallback.exists() and fallback.is_file():
            return fallback

    cache_key = (str(doc_path.parent), basename)
    if cache_key in ASSET_SEARCH_CACHE:
        return ASSET_SEARCH_CACHE[cache_key]

    search_roots = [doc_path.parent, Path.home() / "Downloads", Path.home() / "Desktop"]
    seen: set[str] = set()
    for root in search_roots:
        root_str = str(root.resolve())
        if root_str in seen or not root.exists():
            continue
        seen.add(root_str)
        try:
            for match in root.rglob(basename):
                if match.is_file():
                    ASSET_SEARCH_CACHE[cache_key] = match.resolve()
                    return ASSET_SEARCH_CACHE[cache_key]
        except Exception:
            continue

    ASSET_SEARCH_CACHE[cache_key] = None
    return None


def rewrite_html_assets(html_block: str, doc_path: Path) -> str:
    def replace_img_src(match: re.Match[str]) -> str:
        raw_src = html.unescape(match.group(2).strip())
        if raw_src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        return f'{match.group(1)}{build_asset_url(doc_path, raw_src)}{match.group(3)}'

    return HTML_IMG_SRC_RE.sub(replace_img_src, html_block)


def inline_print_assets(article_html: str, doc_path: Path) -> str:
    def replace_img_src(match: re.Match[str]) -> str:
        raw_src = html.unescape(match.group(2).strip())
        if raw_src.startswith(("http://", "https://", "data:")):
            return match.group(0)

        parsed = urllib.parse.urlparse(raw_src)
        if parsed.path != "/asset":
            return match.group(0)

        query = urllib.parse.parse_qs(parsed.query)
        raw_doc = query.get("doc", [str(doc_path)])[0]
        raw_target = query.get("target", [""])[0]
        try:
            asset_doc = resolve_markdown_path(raw_doc)
            asset_path = resolve_asset_path(asset_doc, raw_target)
            if not asset_path:
                return match.group(0)
            mime_type, _ = mimetypes.guess_type(asset_path.name)
            mime_type = mime_type or "application/octet-stream"
            data = base64.b64encode(asset_path.read_bytes()).decode("ascii")
            return f'{match.group(1)}data:{mime_type};base64,{data}{match.group(3)}'
        except Exception:
            return match.group(0)

    return HTML_IMG_SRC_RE.sub(replace_img_src, article_html)


def replace_tabular_environments(markdown_text: str) -> str:
    markdown_text = replace_figure_environments(markdown_text)

    def render_tabular(match: re.Match[str]) -> str:
        body = match.group(2)
        rows = []
        for raw_row in LATEX_ROW_SPLIT_RE.split(body):
            row = raw_row.strip()
            if not row or row == r"\hline":
                continue
            row = row.replace(r"\hline", "").strip()
            if not row:
                continue
            raw_cells = [cell.strip() for cell in re.split(r"(?<!\\)&", row)]
            cells = []
            for cell in raw_cells:
                multi_match = MULTICOLUMN_RE.fullmatch(cell)
                if multi_match:
                    cells.append(
                        {
                            "text": multi_match.group(2).strip(),
                            "colspan": int(multi_match.group(1)),
                        }
                    )
                else:
                    cells.append({"text": cell, "colspan": 1})
            rows.append(cells)

        if not rows:
            return match.group(0)

        col_count = max(sum(cell["colspan"] for cell in row) for row in rows)
        header = rows[0]
        body_rows = rows[1:] if len(rows) > 1 else []
        table_html = ["<table>", "<thead><tr>"]
        for cell in header:
            colspan_attr = f' colspan="{cell["colspan"]}"' if cell["colspan"] > 1 else ""
            table_html.append(f'<th{colspan_attr}>{cell["text"]}</th>')
        table_html.append("</tr></thead><tbody>")
        for row in body_rows:
            table_html.append("<tr>")
            used_cols = 0
            for cell in row:
                colspan_attr = f' colspan="{cell["colspan"]}"' if cell["colspan"] > 1 else ""
                table_html.append(f'<td{colspan_attr}>{cell["text"]}</td>')
                used_cols += cell["colspan"]
            if used_cols < col_count:
                for _ in range(col_count - used_cols):
                    table_html.append("<td></td>")
            table_html.append("</tr>")
        table_html.append("</tbody></table>")
        return "".join(table_html)

    return TABULAR_RE.sub(render_tabular, markdown_text)


def replace_figure_environments(markdown_text: str) -> str:
    def render_figure(match: re.Match[str]) -> str:
        body = match.group(1)
        image_match = INCLUDEGRAPHICS_RE.search(body)
        if not image_match:
            return match.group(0)
        target = image_match.group(1).strip()
        caption_match = CAPTION_RE.search(body)
        caption = caption_match.group(1).strip() if caption_match else ""
        lines = [f"![{caption}]({target})"]
        if caption:
            lines.append(f"<figcaption>{caption}</figcaption>")
        return "\n".join(lines)

    return FIGURE_RE.sub(render_figure, markdown_text)


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def render_table(table_lines: list[str], doc_path: Path) -> str:
    header_cells = split_table_row(table_lines[0])
    body_lines = table_lines[2:] if len(table_lines) >= 2 and TABLE_SEPARATOR_RE.match(table_lines[1]) else table_lines[1:]

    head_html = "".join(f"<th>{apply_inline_markup(cell, doc_path)}</th>" for cell in header_cells)
    body_rows = []
    for line in body_lines:
        cells = split_table_row(line)
        row_html = "".join(f"<td>{apply_inline_markup(cell, doc_path)}</td>" for cell in cells)
        body_rows.append(f"<tr>{row_html}</tr>")

    return "<table><thead><tr>" + head_html + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"


def clean_toc_title(title: str) -> str:
    cleaned = re.sub(r"(?:\s*\.\s*){2,}$", "", title).strip()
    cleaned = re.sub(r"\s+\.\s+\d+$", "", cleaned).strip()
    cleaned = re.sub(r"(?:\s*\.){2,}\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s+\.\s*$", "", cleaned).strip()
    return cleaned


def parse_toc_entry(line: str) -> tuple[str, str, str] | None:
    stripped = line.strip()
    major = TOC_MAJOR_RE.match(stripped)
    if major:
        number, title, page = major.groups()
        return number, clean_toc_title(title), page
    minor = TOC_MINOR_RE.match(stripped)
    if minor:
        number, title, page = minor.groups()
        return number, clean_toc_title(title), page
    return None


def extract_toc_entries(line: str) -> list[tuple[str, str, str | None, str]]:
    stripped = line.strip()
    matches = list(TOC_ENTRY_START_RE.finditer(stripped))
    direct = parse_toc_entry(stripped)
    if direct and len(matches) <= 1:
        level = "major" if stripped.startswith("#") else "minor"
        number, title, page = direct
        return [(number, title, page, level)]

    entries: list[tuple[str, str, str | None, str]] = []
    for index, match in enumerate(matches):
        segment_start = match.start()
        segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
        segment = stripped[segment_start:segment_end].strip()
        segment_match = re.match(r"(?P<prefix>#\s*)?(?P<number>\d+(?:\.\d+)*)\s+(?P<body>.+)$", segment)
        if not segment_match:
            continue
        number = segment_match.group("number")
        body = segment_match.group("body").strip()
        page_match = re.match(r"^(?P<title>.+?)\s+(?P<page>\d+)$", body)
        if page_match:
            title = clean_toc_title(page_match.group("title"))
            page = page_match.group("page")
        else:
            title = clean_toc_title(body)
            page = None
        level = "major" if segment_match.group("prefix") or "." not in number else "minor"
        if title:
            entries.append((number, title, page, level))
    return entries


def render_toc_entry(number: str, title: str, page: str | None, level: str) -> str:
    anchor = slugify(f"{number} {title}")
    level_class = "toc-page-entry-major" if level == "major" else "toc-page-entry-minor"
    page_html = html.escape(page) if page else ""
    return (
        f'<a class="toc-page-entry {level_class}" href="#{anchor}">'
        f'<span class="toc-page-number">{html.escape(number)}</span>'
        f'<span class="toc-page-title">{html.escape(title)}</span>'
        f'<span class="toc-page-leader" aria-hidden="true"></span>'
        f'<span class="toc-page-page">{page_html}</span>'
        f"</a>"
    )


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.count("|") >= 2 and not stripped.startswith("<")


def render_markdown(markdown_text: str, doc_path: Path) -> tuple[str, list[dict[str, str]]]:
    lines = preprocess_markdown(markdown_text).splitlines()
    output: list[str] = []
    toc: list[dict[str, str]] = []
    paragraph_lines: list[str] = []
    html_block_lines: list[str] = []
    table_lines: list[str] = []
    in_code_block = False
    list_open = False
    in_html_block = False
    in_references = False
    in_contents = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph = " ".join(line.strip() for line in paragraph_lines).strip()
        if paragraph:
            output.append(f"<p>{apply_inline_markup(paragraph, doc_path)}</p>")
        paragraph_lines = []

    def flush_html_block() -> None:
        nonlocal html_block_lines, in_html_block
        if html_block_lines:
            output.append(rewrite_html_assets("\n".join(html_block_lines), doc_path))
        html_block_lines = []
        in_html_block = False

    def flush_table() -> None:
        nonlocal table_lines
        if table_lines:
            output.append(render_table(table_lines, doc_path))
        table_lines = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            output.append("</ul>")
            list_open = False

    for line in lines:
        stripped = line.rstrip()

        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            if in_code_block:
                output.append("</code></pre>")
            else:
                output.append("<pre><code>")
            in_code_block = not in_code_block
            continue

        if in_code_block:
            output.append(html.escape(line))
            continue

        if in_html_block:
            html_block_lines.append(stripped)
            if HTML_BLOCK_END_RE.search(stripped):
                flush_html_block()
            continue

        if not stripped.strip():
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            continue

        if TOC_SECTION_TITLE_RE.fullmatch(stripped):
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            in_contents = True
            in_references = False
            output.append(f'<h1 class="toc-heading">{html.escape(stripped)}</h1>')
            continue

        if REFERENCE_SECTION_TITLE_RE.fullmatch(stripped):
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            in_references = True
            in_contents = False
            output.append(f'<h1 class="toc-heading">{html.escape(stripped)}</h1>')
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            raw_title = heading_match.group(2).strip()
            if TOC_SECTION_TITLE_RE.fullmatch(raw_title):
                in_contents = True
                in_references = False
            elif in_contents:
                toc_entries = extract_toc_entries(stripped)
                if toc_entries:
                    flush_paragraph()
                    close_list()
                    flush_table()
                    flush_html_block()
                    for number, title, page, level_name in toc_entries:
                        output.append(render_toc_entry(number, title, page, level_name))
                    continue
                in_contents = False

            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            level = len(heading_match.group(1))
            title = raw_title
            anchor = slugify(title)
            toc.append({"level": str(level), "title": title, "anchor": anchor})
            in_references = "reference" in title.lower() or "参考文献" in title
            output.append(
                f'<h{level} id="{anchor}">{apply_inline_markup(title, doc_path)}</h{level}>'
            )
            continue

        if in_contents:
            toc_entries = extract_toc_entries(stripped)
            if toc_entries:
                flush_paragraph()
                close_list()
                flush_table()
                flush_html_block()
                for number, title, page, level_name in toc_entries:
                    output.append(render_toc_entry(number, title, page, level_name))
                continue

        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            flush_table()
            flush_html_block()
            if not list_open:
                output.append("<ul>")
                list_open = True
            item_text = stripped[2:].strip()
            output.append(f"<li>{apply_inline_markup(item_text, doc_path)}</li>")
            continue

        if in_references and REFERENCE_LINE_RE.match(stripped):
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            ref_match = REFERENCE_SPLIT_RE.match(stripped)
            if ref_match:
                ref_no, ref_body = ref_match.groups()
                output.append(
                    '<div class="reference-entry">'
                    f'<span class="reference-index">{html.escape(ref_no)}</span>'
                    f'<div class="reference-body">{apply_inline_markup(ref_body, doc_path, render_citations=False)}</div>'
                    '</div>'
                )
            else:
                output.append(f'<p class="reference-entry">{apply_inline_markup(stripped, doc_path, render_citations=False)}</p>')
            continue

        if stripped.startswith("> "):
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            output.append(f"<blockquote>{apply_inline_markup(stripped[2:].strip(), doc_path)}</blockquote>")
            continue

        if HTML_BLOCK_START_RE.match(stripped):
            flush_paragraph()
            close_list()
            flush_table()
            html_block_lines.append(stripped)
            if not HTML_BLOCK_END_RE.search(stripped):
                in_html_block = True
            else:
                flush_html_block()
            continue

        if stripped == "---":
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            output.append("<hr>")
            continue

        if is_table_line(stripped):
            flush_paragraph()
            close_list()
            flush_html_block()
            table_lines.append(stripped)
            continue

        if TOC_LIKE_LINE_RE.match(stripped):
            flush_paragraph()
            close_list()
            flush_table()
            flush_html_block()
            output.append(f'<p class="line-entry">{apply_inline_markup(stripped, doc_path)}</p>')
            continue

        flush_table()

        paragraph_lines.append(stripped)

    flush_paragraph()
    close_list()
    flush_table()
    flush_html_block()
    if in_code_block:
        output.append("</code></pre>")

    return "\n".join(output), toc


def analyze_document(markdown_text: str, doc_path: Path) -> dict[str, object]:
    markdown_images = IMAGE_RE.findall(markdown_text)
    html_images = HTML_IMG_SRC_RE.findall(markdown_text)
    all_image_targets = [target.strip() for _, target in markdown_images]
    all_image_targets.extend(target.strip() for _, target, _ in html_images)

    missing_images: list[str] = []
    resolved_images = 0
    for target in all_image_targets:
        if target.startswith(("http://", "https://", "data:")):
            resolved_images += 1
            continue
        if resolve_asset_path(doc_path, target):
            resolved_images += 1
        else:
            missing_images.append(target)

    block_math_count = len(BLOCK_MATH_RE.findall(markdown_text)) + len(ESCAPED_BLOCK_MATH_RE.findall(markdown_text))
    inline_math_count = len(INLINE_MATH_RE.findall(markdown_text)) + len(ESCAPED_INLINE_MATH_RE.findall(markdown_text))
    html_table_count = markdown_text.count("<table>")
    markdown_table_count = sum(1 for line in markdown_text.splitlines() if is_table_line(line))
    latex_tabular_count = len(TABULAR_RE.findall(markdown_text))
    latex_array_count = markdown_text.count(r"\begin{array}")
    latex_figure_count = len(FIGURE_RE.findall(markdown_text))
    suspicious_math = []
    for match in BLOCK_MATH_RE.finditer(markdown_text):
        fragment = match.group(0)
        if r"\text {" in fragment or r"\mathrm {" in fragment or re.search(r"[A-Za-z](?:\s+[A-Za-z]){2,}", fragment):
            suspicious_math.append(fragment[:140].replace("\n", " "))
        if len(suspicious_math) >= 5:
            break

    return {
        "image_total": len(all_image_targets),
        "image_resolved": resolved_images,
        "image_missing": missing_images[:12],
        "table_total": html_table_count + markdown_table_count + latex_tabular_count + latex_array_count,
        "html_table_count": html_table_count,
        "markdown_table_count": markdown_table_count,
        "latex_tabular_count": latex_tabular_count,
        "latex_array_count": latex_array_count,
        "latex_figure_count": latex_figure_count,
        "block_math_count": block_math_count,
        "inline_math_count": inline_math_count,
        "suspicious_math": suspicious_math,
    }


def build_html(doc_path: Path, markdown_text: str) -> str:
    article_html, toc = render_markdown(markdown_text, doc_path)
    diagnostics = analyze_document(markdown_text, doc_path)
    toc_html = "\n".join(
        f'<a class="toc-item level-{item["level"]}" href="#{item["anchor"]}">{html.escape(item["title"])}</a>'
        for item in toc
    ) or '<div class="empty">未识别到标题</div>'
    diagnostics_html = f"""
        <div class="diag-row"><span>图片</span><strong>{diagnostics['image_resolved']} / {diagnostics['image_total']}</strong></div>
        <div class="diag-row"><span>表格</span><strong>{diagnostics['table_total']}</strong></div>
        <div class="diag-row"><span>LaTeX 图环境</span><strong>{diagnostics['latex_figure_count']}</strong></div>
        <div class="diag-row"><span>块级公式</span><strong>{diagnostics['block_math_count']}</strong></div>
        <div class="diag-row"><span>行内公式</span><strong>{diagnostics['inline_math_count']}</strong></div>
    """
    if diagnostics["image_missing"]:
        missing_items = "".join(f"<li>{html.escape(item)}</li>" for item in diagnostics["image_missing"])
        diagnostics_html += f'<div class="diag-subtitle">缺失图片</div><ul class="diag-list">{missing_items}</ul>'
    if diagnostics["suspicious_math"]:
        math_items = "".join(f"<li><code>{html.escape(item)}</code></li>" for item in diagnostics["suspicious_math"])
        diagnostics_html += f'<div class="diag-subtitle">可疑公式</div><ul class="diag-list">{math_items}</ul>'

    title = html.escape(doc_path.name)
    doc_label = html.escape(str(doc_path))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
      }},
      svg: {{
        fontCache: 'global'
      }}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: rgba(255,255,255,0.72);
      --ink: #1f2937;
      --muted: #5f6b7a;
      --line: rgba(31,41,55,0.12);
      --accent: #b45309;
      --accent-soft: rgba(180,83,9,0.12);
      --content-width: 860px;
      --font-size: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Palatino Linotype", "Book Antiqua", Georgia, "Noto Serif SC", serif;
      background:
        radial-gradient(circle at top left, #f8ead6, transparent 28%),
        radial-gradient(circle at bottom right, #dbeafe, transparent 26%),
        linear-gradient(180deg, #f7f3ea 0%, #f1ede4 100%);
    }}
    .shell {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      padding: 28px 22px;
      border-right: 1px solid var(--line);
      background: rgba(250, 247, 240, 0.82);
      backdrop-filter: blur(16px);
    }}
    .content {{
      padding: 28px 32px 60px;
    }}
    .toolbar, .toc, .meta, .diagnostics {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    }}
    .meta {{
      padding: 16px 18px;
      margin-bottom: 18px;
    }}
    .meta h1 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}
    .meta p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      word-break: break-all;
    }}
    .toolbar {{
      padding: 16px 18px;
      margin-bottom: 18px;
    }}
    .toolbar label {{
      display: block;
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    .toolbar input {{
      width: 100%;
      margin-bottom: 14px;
    }}
    .toolbar button {{
      width: 100%;
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 0;
      border-radius: 12px;
      background: #1f2937;
      color: white;
      font: inherit;
      cursor: pointer;
    }}
    .toolbar button:hover {{
      background: #111827;
    }}
    .toc {{
      padding: 16px 12px;
    }}
    .diagnostics {{
      padding: 16px 14px;
      margin-top: 18px;
    }}
    .diag-row {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 2px;
      font-size: 14px;
    }}
    .diag-subtitle {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .diag-list {{
      margin: 8px 0 0;
      padding-left: 18px;
      font-size: 13px;
      color: var(--muted);
    }}
    .diag-list li {{
      margin-bottom: 6px;
      word-break: break-all;
    }}
    .toc-title {{
      padding: 0 6px 10px;
      font-size: 13px;
      letter-spacing: 0.08em;
      color: var(--muted);
      text-transform: uppercase;
    }}
    .toc-item {{
      display: block;
      padding: 7px 10px;
      border-radius: 10px;
      color: inherit;
      text-decoration: none;
      line-height: 1.4;
    }}
    .toc-item:hover {{
      background: var(--accent-soft);
    }}
    .level-2 {{ padding-left: 20px; }}
    .level-3 {{ padding-left: 32px; }}
    .level-4, .level-5, .level-6 {{ padding-left: 42px; }}
    .empty {{
      padding: 0 8px 8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .article {{
      max-width: var(--content-width);
      margin: 0 auto;
      padding: 42px 48px 72px;
      background: rgba(255,255,255,0.78);
      border: 1px solid rgba(255,255,255,0.7);
      border-radius: 28px;
      box-shadow: 0 22px 60px rgba(15, 23, 42, 0.08);
      font-size: var(--font-size);
      line-height: 1.9;
    }}
    .article h1, .article h2, .article h3, .article h4, .article h5, .article h6 {{
      line-height: 1.3;
      margin: 1.8em 0 0.7em;
      scroll-margin-top: 20px;
    }}
    .article h1:first-child {{ margin-top: 0; }}
    .article .toc-heading {{
      margin-top: 0;
      margin-bottom: 1.2em;
      font-size: 1.1em;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .article p, .article ul, .article blockquote, .article pre, .article hr {{
      margin: 0 0 1em;
    }}
    .article .line-entry {{
      margin: 0 0 0.45em;
      line-height: 1.65;
    }}
    .article .toc-page-entry {{
      display: flex;
      align-items: baseline;
      gap: 0.38em;
      width: 100%;
      color: inherit;
      text-decoration: none;
    }}
    .article .toc-page-entry-major {{
      margin: 0 0 0.42em;
      font-size: 1.22em;
      font-weight: 700;
      line-height: 1.55;
    }}
    .article .toc-page-entry-minor {{
      margin: 0 0 0.32em;
      font-size: 1.05em;
      line-height: 1.55;
    }}
    .article .toc-page-number {{
      flex: 0 0 auto;
      min-width: 3.1em;
      font-variant-numeric: tabular-nums;
    }}
    .article .toc-page-title {{
      flex: 0 1 auto;
      min-width: 0;
    }}
    .article .toc-page-leader {{
      flex: 1 1 auto;
      min-width: 1.2em;
      border-bottom: 0.14em dotted rgba(31,41,55,0.6);
      transform: translateY(-0.18em);
      margin: 0 0.14em;
    }}
    .article .toc-page-page {{
      flex: 0 0 auto;
      min-width: 2.6em;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .article .toc-page-entry-minor .toc-page-number {{
      padding-left: 0.8em;
    }}
    .article .reference-entry {{
      display: grid;
      grid-template-columns: 2.4em minmax(0, 1fr);
      column-gap: 0.95em;
      align-items: start;
      margin: 0 0 1.55em;
      line-height: 1.75;
    }}
    .article .reference-index {{
      display: block;
      font-weight: 600;
      white-space: nowrap;
      text-align: left;
    }}
    .article .reference-body {{
      min-width: 0;
      word-break: break-word;
    }}
    .article sup.citation {{
      font-size: 0.72em;
      line-height: 0;
      vertical-align: super;
      margin-left: 0.08em;
    }}
    .article table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0 0 1.2em;
      font-size: 0.95em;
      background: rgba(255,255,255,0.65);
      overflow: hidden;
      display: block;
      overflow-x: auto;
      border-radius: 14px;
      border: 1px solid rgba(31,41,55,0.12);
    }}
    .article thead {{
      background: rgba(180,83,9,0.10);
    }}
    .article th, .article td {{
      padding: 10px 12px;
      border: 1px solid rgba(31,41,55,0.10);
      text-align: left;
      vertical-align: top;
      white-space: normal;
    }}
    .article figure {{
      margin: 0 0 1.1em;
    }}
    .article figcaption {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.92em;
      text-align: center;
    }}
    .math-fragment.math-display {{
      display: block;
      overflow-x: auto;
      overflow-y: hidden;
      padding: 0.4em 0;
    }}
    .article img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 12px auto;
      border-radius: 14px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.10);
    }}
    .article blockquote {{
      padding: 10px 16px;
      border-left: 4px solid var(--accent);
      background: rgba(255,255,255,0.5);
      color: #374151;
    }}
    .article code {{
      padding: 0.15em 0.35em;
      border-radius: 6px;
      background: #f3f4f6;
      font-size: 0.92em;
    }}
    .article pre {{
      overflow: auto;
      padding: 16px;
      border-radius: 16px;
      background: #111827;
      color: #e5e7eb;
    }}
    .article pre code {{
      padding: 0;
      background: transparent;
      color: inherit;
    }}
    .article a {{
      color: var(--accent);
    }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{
        position: relative;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}
      .content {{ padding: 18px 14px 32px; }}
      .article {{ padding: 28px 20px 44px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <section class="meta">
        <h1>{title}</h1>
        <p>{doc_label}</p>
      </section>
      <section class="toolbar">
        <button id="openFileButton" type="button">打开别的论文</button>
        <button id="exportPdfButton" type="button">导出 PDF</button>
        <button id="repairAssetsButton" type="button">缺失资源修复</button>
        <input id="filePicker" type="file" accept=".md,.markdown,.txt" style="display:none">
        <label for="fontRange">字号</label>
        <input id="fontRange" type="range" min="15" max="24" step="1" value="18">
        <label for="widthRange">阅读宽度</label>
        <input id="widthRange" type="range" min="680" max="1100" step="10" value="860">
      </section>
      <nav class="toc">
        <div class="toc-title">目录</div>
        {toc_html}
      </nav>
      <section class="diagnostics">
        <div class="toc-title">资源检查</div>
        {diagnostics_html}
      </section>
    </aside>
    <main class="content">
      <article class="article" id="article">
        {article_html}
      </article>
    </main>
  </div>
  <script>
    const root = document.documentElement;
    const fontRange = document.getElementById('fontRange');
    const widthRange = document.getElementById('widthRange');
    const openFileButton = document.getElementById('openFileButton');
    const exportPdfButton = document.getElementById('exportPdfButton');
    const repairAssetsButton = document.getElementById('repairAssetsButton');
    const filePicker = document.getElementById('filePicker');
    const fontKey = 'md-reader-font-size';
    const widthKey = 'md-reader-content-width';

    const savedFont = localStorage.getItem(fontKey);
    const savedWidth = localStorage.getItem(widthKey);
    if (savedFont) {{
      fontRange.value = savedFont;
      root.style.setProperty('--font-size', savedFont + 'px');
    }}
    if (savedWidth) {{
      widthRange.value = savedWidth;
      root.style.setProperty('--content-width', savedWidth + 'px');
    }}

    fontRange.addEventListener('input', (event) => {{
      const value = event.target.value;
      root.style.setProperty('--font-size', value + 'px');
      localStorage.setItem(fontKey, value);
    }});

    widthRange.addEventListener('input', (event) => {{
      const value = event.target.value;
      root.style.setProperty('--content-width', value + 'px');
      localStorage.setItem(widthKey, value);
    }});

    openFileButton.addEventListener('click', () => {{
      filePicker.click();
    }});

    exportPdfButton.addEventListener('click', async () => {{
      const params = new URLSearchParams(window.location.search);
      const currentPath = params.get('path');
      if (!currentPath) {{
        return;
      }}
      exportPdfButton.disabled = true;
      exportPdfButton.textContent = '导出中...';
      try {{
        const response = await fetch('/export_pdf', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ path: currentPath }})
        }});
        const data = await response.json();
        if (data.ok && data.download_url) {{
          alert(`PDF 已生成：${{data.output_path}}`);
          window.open(data.download_url, '_blank');
        }} else {{
          alert(data.error || 'PDF 导出失败');
        }}
      }} finally {{
        exportPdfButton.disabled = false;
        exportPdfButton.textContent = '导出 PDF';
      }}
    }});

    repairAssetsButton.addEventListener('click', async () => {{
      const params = new URLSearchParams(window.location.search);
      const currentPath = params.get('path');
      if (!currentPath) {{
        return;
      }}
      repairAssetsButton.disabled = true;
      repairAssetsButton.textContent = '修复中...';
      try {{
        const response = await fetch('/repair_assets', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ path: currentPath }})
        }});
        const data = await response.json();
        if (data.ok) {{
          alert(`已修复 ${{data.repaired}} 个资源，缺失 ${{data.missing}} 个资源。`);
          window.location.reload();
        }} else {{
          alert(data.error || '修复失败');
        }}
      }} finally {{
        repairAssetsButton.disabled = false;
        repairAssetsButton.textContent = '缺失资源修复';
      }}
    }});

    filePicker.addEventListener('change', async (event) => {{
      const file = event.target.files[0];
      if (!file) {{
        return;
      }}

      const text = await file.text();
      const response = await fetch('/open', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ file_name: file.name, content: text }})
      }});
      const data = await response.json();
      if (data.path) {{
        window.location.href = '/?path=' + encodeURIComponent(data.path);
      }}
    }});

    if (window.MathJax && window.MathJax.typesetPromise) {{
      window.MathJax.typesetPromise();
    }}
  </script>
</body>
</html>"""


def build_print_html(doc_path: Path, markdown_text: str) -> str:
    article_html, _ = render_markdown(markdown_text, doc_path)
    article_html = inline_print_assets(article_html, doc_path)
    article_html = article_html.replace(' loading="lazy"', ' loading="eager"')
    title = html.escape(doc_path.stem)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
      }},
      svg: {{ fontCache: 'global' }}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
  <style>
    body {{
      margin: 0;
      color: #111827;
      font-family: "Palatino Linotype", "Book Antiqua", Georgia, "Noto Serif SC", serif;
      background: white;
    }}
    .article {{
      max-width: 860px;
      margin: 0 auto;
      padding: 28px 34px 40px;
      font-size: 17px;
      line-height: 1.8;
    }}
    h1, h2, h3, h4, h5, h6 {{ line-height: 1.25; margin: 1.5em 0 0.6em; }}
    h1:first-child {{ margin-top: 0; }}
    p, ul, blockquote, pre, hr {{ margin: 0 0 1em; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 0 0 1.1em;
      font-size: 0.95em;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    figure {{ margin: 0 0 1em; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 10px auto; }}
    figcaption {{ color: #4b5563; font-size: 0.92em; text-align: center; }}
    .line-entry {{ margin: 0 0 0.45em; line-height: 1.6; }}
    .reference-entry {{ display: grid; grid-template-columns: 2.4em minmax(0, 1fr); column-gap: 0.95em; align-items: start; margin: 0 0 1.3em; line-height: 1.7; }}
    .reference-index {{ display: block; font-weight: 600; white-space: nowrap; text-align: left; }}
    .reference-body {{ min-width: 0; word-break: break-word; }}
    .toc-page-entry {{ display: flex; align-items: baseline; gap: 0.38em; width: 100%; color: inherit; text-decoration: none; }}
    .toc-page-entry-major {{ margin: 0 0 0.38em; font-size: 1.18em; font-weight: 700; line-height: 1.5; }}
    .toc-page-entry-minor {{ margin: 0 0 0.24em; font-size: 1.02em; line-height: 1.5; }}
    .toc-page-number {{ flex: 0 0 auto; min-width: 3.1em; font-variant-numeric: tabular-nums; }}
    .toc-page-title {{ flex: 0 1 auto; min-width: 0; }}
    .toc-page-leader {{ flex: 1 1 auto; min-width: 1.2em; border-bottom: 0.14em dotted rgba(31,41,55,0.6); transform: translateY(-0.18em); margin: 0 0.14em; }}
    .toc-page-page {{ flex: 0 0 auto; min-width: 2.6em; text-align: right; font-variant-numeric: tabular-nums; }}
    .toc-page-entry-minor .toc-page-number {{ padding-left: 0.8em; }}
    sup.citation {{ font-size: 0.72em; line-height: 0; vertical-align: super; margin-left: 0.08em; }}
    @page {{ size: A4; margin: 18mm 16mm 18mm 16mm; }}
  </style>
</head>
<body>
  <article class="article">{article_html}</article>
  <script>
    window.__PDF_READY__ = false;

    async function waitForImages() {{
      const images = Array.from(document.images || []);
      await Promise.all(images.map((img) => {{
        img.loading = 'eager';
        if (img.complete && img.naturalWidth > 0) {{
          return Promise.resolve();
        }}
        return new Promise((resolve) => {{
          const done = () => resolve();
          img.addEventListener('load', done, {{ once: true }});
          img.addEventListener('error', done, {{ once: true }});
        }});
      }}));
    }}

    async function waitForMath() {{
      if (window.MathJax && window.MathJax.startup && window.MathJax.startup.promise) {{
        try {{
          await window.MathJax.startup.promise;
          if (window.MathJax.typesetPromise) {{
            await window.MathJax.typesetPromise();
          }}
        }} catch (err) {{
          console.error(err);
        }}
      }}
    }}

    window.addEventListener('load', async () => {{
      await waitForImages();
      await waitForMath();
      await waitForImages();
      window.__PDF_READY__ = true;
    }});
  </script>
</body>
</html>"""


def build_empty_html() -> bytes:
    payload = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Paper Reader</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f3ec; color: #111827; }
    main { max-width: 720px; margin: 10vh auto; padding: 32px 36px; background: white; border-radius: 22px; box-shadow: 0 20px 48px rgba(15,23,42,0.08); }
    h1 { margin: 0 0 0.6em; font-size: 2rem; }
    p { line-height: 1.7; margin: 0 0 1em; }
    code { background: #f3f4f6; padding: 0.15em 0.35em; border-radius: 6px; }
  </style>
</head>
<body>
  <main>
    <h1>Paper Reader</h1>
    <p>当前没有打开文档。请通过启动器选择文件，或使用 <code>?path=/absolute/path/to/file.md</code> 打开 Markdown 文档。</p>
    <p>命令行示例：<code>python3 md_reader/server.py --file "/absolute/path/to/document.md"</code></p>
  </main>
</body>
</html>"""
    return payload.encode("utf-8")


class MarkdownReaderHandler(BaseHTTPRequestHandler):
    server_version = "MarkdownReader/0.1"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if route == "/":
            self.serve_document(query)
            return

        if route == "/asset":
            self.serve_asset(query)
            return
        if route == "/print":
            self.serve_print_document(query)
            return
        if route == "/generated":
            self.serve_generated_file(query)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/open":
            self.receive_uploaded_markdown()
            return
        if parsed.path == "/export_pdf":
            self.export_pdf()
            return
        if parsed.path == "/repair_assets":
            self.repair_missing_assets()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def serve_document(self, query: dict[str, list[str]]) -> None:
        raw_path = query.get("path", [str(self.server.default_md_path) if self.server.default_md_path else ""])[0]
        try:
            if not raw_path:
                payload = build_empty_html()
            else:
                doc_path = resolve_markdown_path(raw_path)
                markdown_text = doc_path.read_text(encoding="utf-8")
                payload = build_html(doc_path, markdown_text).encode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive error surface
            payload = (
                "<!doctype html><meta charset='utf-8'><title>读取失败</title>"
                f"<body><h1>读取失败</h1><p>{html.escape(str(exc))}</p></body>"
            ).encode("utf-8")

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_asset(self, query: dict[str, list[str]]) -> None:
        raw_doc = query.get("doc", [""])[0]
        raw_target = query.get("target", [""])[0]
        try:
            doc_path = resolve_markdown_path(raw_doc)
            asset_path = resolve_asset_path(doc_path, raw_target)
            if not asset_path:
                raise FileNotFoundError("未找到图片资源")
            mime_type, _ = mimetypes.guess_type(asset_path.name)
            mime_type = mime_type or "application/octet-stream"
            data = asset_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(HTTPStatus.NOT_FOUND, "Asset Not Found")

    def serve_print_document(self, query: dict[str, list[str]]) -> None:
        raw_path = query.get("path", [str(self.server.default_md_path) if self.server.default_md_path else ""])[0]
        try:
            if not raw_path:
                raise FileNotFoundError("未指定导出文档")
            doc_path = resolve_markdown_path(raw_path)
            markdown_text = doc_path.read_text(encoding="utf-8")
            payload = build_print_html(doc_path, markdown_text).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_error(HTTPStatus.NOT_FOUND, "Print View Not Found")

    def serve_generated_file(self, query: dict[str, list[str]]) -> None:
        raw_path = query.get("path", [""])[0]
        try:
            file_path = Path(raw_path).expanduser().resolve()
            if not file_path.exists() or not file_path.is_file():
                raise FileNotFoundError("未找到生成文件")
            mime_type, _ = mimetypes.guess_type(file_path.name)
            mime_type = mime_type or "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(HTTPStatus.NOT_FOUND, "Generated File Not Found")

    def receive_uploaded_markdown(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            file_name = payload["file_name"]
            content = payload["content"]
            safe_name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", Path(file_name).name) or "paper.md"
            temp_path = self.server.upload_dir / safe_name
            temp_path.write_text(content, encoding="utf-8")
            response = json.dumps({"path": str(temp_path)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except Exception as exc:
            response = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    def repair_missing_assets(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            doc_path = resolve_markdown_path(payload["path"])
            markdown_text = doc_path.read_text(encoding="utf-8")
            image_targets = [target.strip() for _, target in IMAGE_RE.findall(markdown_text)]
            image_targets.extend(target.strip() for _, target, _ in HTML_IMG_SRC_RE.findall(markdown_text))

            images_dir = doc_path.parent / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            repaired = 0
            missing = 0
            seen: set[str] = set()
            for target in image_targets:
                if target.startswith(("http://", "https://", "data:")):
                    continue
                basename = Path(target).name
                if basename in seen:
                    continue
                seen.add(basename)
                destination = images_dir / basename
                if destination.exists():
                    repaired += 1
                    continue
                source = resolve_asset_path(doc_path, target)
                if not source:
                    missing += 1
                    continue
                try:
                    os.symlink(source, destination)
                except Exception:
                    shutil.copy2(source, destination)
                repaired += 1

            response = json.dumps({"ok": True, "repaired": repaired, "missing": missing}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except Exception as exc:
            response = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    def export_pdf(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            doc_path = resolve_markdown_path(payload["path"])
            output_path = doc_path.with_suffix(".pdf")
            print_url = f"http://127.0.0.1:{self.server.server_port}/print?path={urllib.parse.quote(str(doc_path))}"

            if PDF_HELPER_PATH.exists():
                result = subprocess.run(
                    [str(PDF_HELPER_PATH), print_url, str(output_path)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            else:
                result = export_pdf_with_browser(print_url, output_path)
            if result.returncode != 0 or not output_path.exists():
                stderr = result.stderr.strip() or result.stdout.strip() or "未知错误"
                raise RuntimeError(stderr)

            response = json.dumps(
                {
                    "ok": True,
                    "output_path": str(output_path),
                    "download_url": f"/generated?path={urllib.parse.quote(str(output_path))}",
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except Exception as exc:
            response = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地 Markdown 阅读器")
    parser.add_argument("--file", default=DEFAULT_MD_PATH, help="默认打开的 Markdown 文件路径")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    return parser.parse_args()


def run_server(file_path: str | None, host: str, port: int) -> None:
    default_md_path = resolve_markdown_path(file_path) if file_path else None
    server = ThreadingHTTPServer((host, port), MarkdownReaderHandler)
    server.default_md_path = default_md_path
    server.upload_dir = Path("/tmp/md_reader_uploads")
    server.upload_dir.mkdir(parents=True, exist_ok=True)
    print(f"Markdown reader running at http://{host}:{port}")
    print(f"Opening: {default_md_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    args = parse_args()
    run_server(args.file, args.host, args.port)


if __name__ == "__main__":
    main()
