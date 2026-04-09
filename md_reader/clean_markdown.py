from __future__ import annotations

import argparse
import re
from pathlib import Path

from server import normalize_math_fragment


PROMPT_PATTERNS = [
    r"请尊重原意，保持原有格式(?:，|,)?(?:并)?(?:(?:以)?简体中文(?:重写|改写)|将以下内容改写为简体中文)(?:以下内容)?(?:（[^）]*）)?[。.]?",
    r"请尊重原文含义，保持原有格式(?:，|,)?(?:并)?(?:(?:以)?简体中文(?:重写|改写)|将以下内容改写为简体中文)(?:以下内容)?(?:（[^）]*）)?[。.]?",
    r"请尊重原文，保持原有格式(?:，|,)?(?:并)?(?:(?:以)?简体中文(?:重写|改写)|将以下内容改写为简体中文)(?:以下内容)?(?:（[^）]*）)?[。.]?",
]

INLINE_JUNK_PATTERNS = [
    (r"\$\s*\\\$\s*", ""),
    (r"\bto\b", "-"),
    (r"\. \. \.", "…"),
    (r"[ \t]+([，。；：？！%])", r"\1"),
    (r"([（(])[ \t]+", r"\1"),
    (r"[ \t]+([）)])", r"\1"),
    (r"[ \t]{2,}", " "),
]

MATH_FRAGMENT_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)


def clean_text(text: str) -> str:
    cleaned = text

    for pattern in PROMPT_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)

    cleaned = MATH_FRAGMENT_RE.sub(lambda m: normalize_math_fragment(m.group(0)), cleaned)

    for pattern, replacement in INLINE_JUNK_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned)

    lines = [clean_line(line) for line in cleaned.splitlines()]
    lines = collapse_blank_lines(lines)
    return "\n".join(lines).strip() + "\n"


def clean_line(line: str) -> str:
    stripped = line.strip()

    if not stripped:
        return ""

    if any(re.fullmatch(pattern, stripped) for pattern in PROMPT_PATTERNS):
        return ""

    stripped = re.sub(r"^\.\d+$", "", stripped)
    stripped = re.sub(r"^\$\s*\\S\s*\d+(?:\.\d+)?\s*$", "", stripped)
    stripped = re.sub(r"^\$\s*\\S\s*\d+(?:\.\d+)?\s*[。.]?$", "", stripped)
    stripped = re.sub(r"([^\s])\s*\.\s*([^\s])", r"\1.\2", stripped)
    stripped = re.sub(r"[ \t]{2,}", " ", stripped)
    return stripped.strip()


def collapse_blank_lines(lines: list[str]) -> list[str]:
    output: list[str] = []
    blank = False
    for line in lines:
        if line:
            output.append(line)
            blank = False
            continue
        if not blank:
            output.append("")
            blank = True
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="清洗被翻译污染的 Markdown 文档")
    parser.add_argument("input", help="输入 Markdown 路径")
    parser.add_argument("output", help="输出 Markdown 路径")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    text = input_path.read_text(encoding="utf-8")
    cleaned = clean_text(text)
    output_path.write_text(cleaned, encoding="utf-8")

    print(f"cleaned: {input_path}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
