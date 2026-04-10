#!/usr/bin/env python3
"""pdf2md - Convert PDF files to Markdown with image extraction."""

import argparse
import re
import sys
from pathlib import Path

try:
    import fitz  # type: ignore # PyMuPDF
except ImportError:
    print(
        "Error: PyMuPDF is required. Install it with: pip install pymupdf",
        file=sys.stderr,
    )
    sys.exit(1)

# Font name fragments (lowercase) that indicate a math/symbol font
_MATH_FONT_FRAGMENTS = frozenset(
    {
        "cmmi",
        "cmsy",
        "cmex",
        "cmr",
        "msbm",
        "eufm",
        "symbol",
        "mt extra",
        "cambria math",
        "asana math",
        "stixmath",
        "stix",
        "latinmodern-math",
        "texgyre",
    }
)

# Unicode characters that strongly indicate math content
_MATH_CHARS = frozenset(
    "∫∑∏√∞±×÷≤≥≠≈→←↑↓∂∇∈∉⊂⊃∪∩⊆⊇⊕⊗"
    "αβγδεζηθικλμνξπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΠΡΣΤΥΦΧΨΩ"
    "∀∃∄∅∧∨¬⟹⟺ℝℂℕℤℚℏ°′″"
)


def _is_math_font(font_name: str) -> bool:
    name = font_name.lower()
    return any(f in name for f in _MATH_FONT_FRAGMENTS)


def _math_ratio(text: str) -> float:
    """Fraction of characters in text that are math/Greek symbols."""
    if not text:
        return 0.0
    return sum(1 for c in text if c in _MATH_CHARS) / len(text)


def _need_space(span_a: dict, span_b: dict) -> bool:
    """Return True if a space should be inserted between two consecutive spans.

    Uses the visual gap between their bounding boxes. A gap wider than
    ~25% of the font size is treated as a word boundary.
    """
    # If either span already carries a boundary space, no extra space needed
    if span_a["text"].endswith((" ", "\t")) or span_b["text"].startswith((" ", "\t")):
        return False
    gap = span_b["bbox"][0] - span_a["bbox"][2]
    return gap > span_a["size"] * 0.25


def _heading_level(span_size: float, body_size: float) -> int | None:
    ratio = span_size / body_size if body_size else 1.0
    if ratio >= 1.8:
        return 1
    elif ratio >= 1.5:
        return 2
    elif ratio >= 1.2:
        return 3
    return None


def _apply_formatting(text: str, span: dict, body_size: float) -> str:
    """Wrap text with markdown formatting based on font properties."""
    text = text.strip()
    if not text:
        return ""

    # Math span → inline equation
    if _is_math_font(span.get("font", "")) or _math_ratio(text) > 0.3:
        return f"${text}$"

    level = _heading_level(span["size"], body_size)
    if level:
        return f"{'#' * level} {text}"

    flags = span["flags"]
    bold = bool(flags & 16)
    italic = bool(flags & 2)
    if bold and italic:
        return f"***{text}***"
    if bold:
        return f"**{text}**"
    if italic:
        return f"*{text}*"
    return text


def _build_line_text(spans: list[dict], body_size: float) -> str:
    """Assemble a list of spans into a single line string.

    Inserts spaces between spans where the visual gap suggests a word
    boundary, preventing words from merging together.
    """
    parts: list[str] = []
    prev_content_idx = -1  # index of last span that had real text

    for i, span in enumerate(spans):
        raw = span["text"]
        if not raw:
            continue

        # Whitespace-only span: preserve it as a literal space
        if not raw.strip():
            parts.append(" ")
            continue

        # Check if we need to insert a space before this span
        if prev_content_idx >= 0:
            if _need_space(spans[prev_content_idx], span):
                # Avoid double-spacing
                if parts and not parts[-1].endswith(" "):
                    parts.append(" ")

        parts.append(_apply_formatting(raw, span, body_size))
        prev_content_idx = i

    return "".join(parts).strip()


def _is_display_equation(line_text: str) -> bool:
    """Heuristic: is this line a standalone display equation?

    Criteria: already wrapped as $...$ OR more than 40% math characters
    and short enough to be a formula (not prose).
    """
    stripped = line_text.strip()
    # Already an inline math span promoted from a math font
    if re.fullmatch(r"\$[^$]+\$", stripped):
        return True
    # High math-character density, not a long prose sentence
    if _math_ratio(stripped) > 0.35 and len(stripped) < 300:
        return True
    return False


def _promote_to_display(line_text: str) -> str:
    """Rewrap an equation line as a display (block) equation."""
    # Strip wrapping $...$ if present, then rewrap as $$...$$
    inner = re.sub(r"^\$(.+)\$$", r"\1", line_text.strip())
    return f"$$\n{inner}\n$$"


def extract_annotations(page: fitz.Page, page_num: int) -> list[dict]:
    """Extract annotations (comments, highlights, notes) from a PDF page."""
    results = []
    for annot in page.annots():
        info = annot.info
        kind_code, kind_name = annot.type  # e.g. (1, 'Text'), (8, 'Highlight')

        content = info.get("content", "").strip()
        author = info.get("title", "").strip()  # PyMuPDF stores author in 'title'
        subject = info.get("subject", "").strip()
        creation = info.get("creationDate", "").strip()

        # For highlight/underline/squiggly/strikeout: get the highlighted text
        highlighted_text = ""
        if kind_code in (8, 9, 10, 11):  # Highlight, Underline, Squiggly, StrikeOut
            try:
                highlighted_text = page.get_textbox(annot.rect).strip()
            except Exception:
                pass

        if not content and not highlighted_text:
            continue

        results.append(
            {
                "page": page_num,
                "type": kind_name,
                "author": author,
                "date": creation,
                "subject": subject,
                "content": content,
                "highlighted_text": highlighted_text,
            }
        )
    return results


def extract_images(page: fitz.Page, page_num: int, images_dir: Path) -> list[dict]:
    """Extract images from a PDF page and save them to disk."""
    images_dir.mkdir(parents=True, exist_ok=True)
    extracted = []

    for img_index, img_ref in enumerate(page.get_images(full=True), start=1):
        xref = img_ref[0]
        base_image = page.parent.extract_image(xref)
        if not base_image:
            continue

        filename = f"page{page_num}_img{img_index}.{base_image['ext']}"
        (images_dir / filename).write_bytes(base_image["image"])
        extracted.append({"filename": filename, "index": img_index, "page": page_num})

    return extracted


def detect_body_font_size(page: fitz.Page) -> float:
    """Most common font size on the page, weighted by character count."""
    size_counts: dict[float, int] = {}
    for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if block["type"] != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                size = round(span["size"], 1)
                size_counts[size] = size_counts.get(size, 0) + len(span["text"].strip())
    return max(size_counts, key=size_counts.get) if size_counts else 12.0


def _format_annotation(annot: dict) -> str:
    """Render a single annotation as a Markdown blockquote."""
    kind = annot["type"]
    author = f"**{annot['author']}**" if annot["author"] else ""
    date = f" _{annot['date']}_" if annot["date"] else ""
    meta = f"{author}{date}".strip()
    header = f"> [{kind}]{' — ' + meta if meta else ''}"

    lines = [header]
    if annot["highlighted_text"]:
        lines.append(f"> > *\"{annot['highlighted_text']}\"*")
    if annot["content"]:
        lines.append(f"> {annot['content']}")
    return "\n".join(lines)


def page_to_markdown(page: fitz.Page, images: list[dict], annotations: list[dict] | None = None) -> str:
    """Convert a single PDF page to a Markdown string."""
    body_size = detect_body_font_size(page)
    output: list[str] = []
    prev_had_text = False
    hyphen_carry = ""  # fragment from a line-break hyphenated word

    for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if block["type"] != 0:
            continue

        block_lines: list[str] = []

        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s["text"]]
            if not spans:
                continue

            line_text = _build_line_text(spans, body_size)
            if not line_text:
                continue

            # Reattach hyphen-carry from previous line
            if hyphen_carry:
                line_text = hyphen_carry + line_text.lstrip()
                hyphen_carry = ""

            # Detect ASCII line-break hyphenation: word ends with "-" and next
            # char (start of next line) is lowercase → word was split for wrapping.
            if re.search(r"-$", line_text):
                hyphen_carry = line_text.rstrip("-")
                continue

            # Promote isolated equation lines to display math
            if _is_display_equation(line_text):
                block_lines.append(_promote_to_display(line_text))
            else:
                block_lines.append(line_text)

        # Flush any orphaned hyphen carry at block boundary
        if hyphen_carry:
            block_lines.append(hyphen_carry)
            hyphen_carry = ""

        block_text = "\n".join(block_lines).strip()
        if not block_text:
            continue

        if prev_had_text:
            output.append("")
        output.append(block_text)
        prev_had_text = True

    # Image citations
    for img in images:
        output.append("")
        output.append(
            f"![Figure {img['index']} (page {img['page']})]({img['filename']})"
        )

    # Annotations / comments
    if annotations:
        output.append("")
        output.append("**Comments & Annotations:**")
        for annot in annotations:
            output.append("")
            output.append(_format_annotation(annot))

    return "\n".join(output)


def convert(
    pdf_path: Path,
    output_path: Path,
    images_dir_name: str = "images",
    extract_comments: bool = True,
) -> dict:
    """Convert a PDF file to Markdown.

    Returns a summary dict with keys: output_path, images_count, annotation_count.
    """
    doc = fitz.open(pdf_path)
    images_dir = output_path.parent / images_dir_name
    sections: list[str] = []
    total_annotations = 0

    for page_num, page in enumerate(doc, start=1):
        images = extract_images(page, page_num, images_dir)
        for img in images:
            img["filename"] = f"{images_dir_name}/{img['filename']}"

        annotations = extract_annotations(page, page_num) if extract_comments else []
        total_annotations += len(annotations)

        page_md = page_to_markdown(page, images, annotations)
        if page_md.strip():
            sections.append(page_md)

    doc.close()

    output_path.write_text("\n\n---\n\n".join(sections), encoding="utf-8")

    images_count = 0
    if images_dir.exists():
        images_count = sum(1 for _ in images_dir.iterdir())

    return {
        "output_path": output_path,
        "images_count": images_count,
        "annotation_count": total_annotations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdf2md",
        description="Convert a PDF file to Markdown, extracting embedded images.",
    )
    parser.add_argument("pdf", type=Path, help="Path to the input PDF file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .md file path (default: same name as PDF in current directory)",
    )
    parser.add_argument(
        "--images-dir",
        default="images",
        metavar="DIR",
        help="Subdirectory name for extracted images (default: images)",
    )

    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: Input must be a PDF file: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    output_path = (
        args.output or Path.cwd() / pdf_path.with_suffix(".md").name
    ).resolve()
    result = convert(pdf_path, output_path, images_dir_name=args.images_dir)
    print(f"Converted: {pdf_path} -> {result['output_path']}")
    if result["images_count"]:
        print(f"Extracted {result['images_count']} image(s)")
    if result["annotation_count"]:
        print(f"Extracted {result['annotation_count']} annotation(s)/comment(s)")


if __name__ == "__main__":
    main()
