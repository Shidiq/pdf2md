#!/usr/bin/env python3
"""pdf2md - Convert PDF files to Markdown with image extraction."""

import argparse
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF is required. Install it with: pip install pymupdf", file=sys.stderr)
    sys.exit(1)


def extract_images(page: fitz.Page, page_num: int, images_dir: Path) -> list[dict]:
    """Extract images from a PDF page and save them to disk."""
    images_dir.mkdir(parents=True, exist_ok=True)
    extracted = []

    for img_index, img_ref in enumerate(page.get_images(full=True), start=1):
        xref = img_ref[0]
        doc = page.parent
        base_image = doc.extract_image(xref)
        if not base_image:
            continue

        ext = base_image["ext"]
        image_data = base_image["image"]
        filename = f"page{page_num}_img{img_index}.{ext}"
        image_path = images_dir / filename

        with open(image_path, "wb") as f:
            f.write(image_data)

        extracted.append({
            "path": image_path,
            "filename": filename,
            "index": img_index,
            "page": page_num,
        })

    return extracted


def get_heading_level(span_size: float, body_size: float) -> int | None:
    """Determine markdown heading level based on font size ratio."""
    ratio = span_size / body_size if body_size else 1.0
    if ratio >= 1.8:
        return 1
    elif ratio >= 1.5:
        return 2
    elif ratio >= 1.2:
        return 3
    return None


def detect_body_font_size(page: fitz.Page) -> float:
    """Find the most common font size on the page (body text size)."""
    size_counts: dict[float, int] = {}
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                size = round(span["size"], 1)
                size_counts[size] = size_counts.get(size, 0) + len(span["text"].strip())

    if not size_counts:
        return 12.0
    return max(size_counts, key=size_counts.get)


def page_to_markdown(page: fitz.Page, page_num: int, images: list[dict]) -> str:
    """Convert a single PDF page to Markdown text."""
    body_size = detect_body_font_size(page)
    lines: list[str] = []
    prev_block_type = None

    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    for block in blocks:
        # Image block placeholder — actual images appended at end of page section
        if block["type"] == 1:
            continue

        if block["type"] != 0:
            continue

        block_lines = block.get("lines", [])
        block_text_parts: list[str] = []

        for line in block_lines:
            line_parts: list[str] = []
            for span in line.get("spans", []):
                text = span["text"]
                if not text.strip():
                    line_parts.append(text)
                    continue

                size = span["size"]
                flags = span["flags"]  # bit flags: bold=16, italic=2
                bold = bool(flags & 16)
                italic = bool(flags & 2)

                heading = get_heading_level(size, body_size)
                if heading:
                    text = f"{'#' * heading} {text.strip()}"
                else:
                    if bold and italic:
                        text = f"***{text.strip()}***"
                    elif bold:
                        text = f"**{text.strip()}**"
                    elif italic:
                        text = f"*{text.strip()}*"

                line_parts.append(text)

            line_text = "".join(line_parts).strip()
            if line_text:
                block_text_parts.append(line_text)

        block_text = "\n".join(block_text_parts).strip()
        if block_text:
            if prev_block_type == "text":
                lines.append("")
            lines.append(block_text)
            prev_block_type = "text"

    # Append extracted images at the end of the page section
    for img in images:
        lines.append("")
        lines.append(f"![Figure {img['index']} (page {img['page']})]({img['filename']})")

    return "\n".join(lines)


def convert(pdf_path: Path, output_path: Path, images_dir_name: str = "images") -> None:
    """Convert a PDF file to Markdown."""
    doc = fitz.open(pdf_path)
    images_dir = output_path.parent / images_dir_name

    md_sections: list[str] = []

    for page_num, page in enumerate(doc, start=1):
        images = extract_images(page, page_num, images_dir)

        # Rewrite image paths to be relative to the markdown file
        for img in images:
            img["filename"] = f"{images_dir_name}/{img['filename']}"

        page_md = page_to_markdown(page, page_num, images)
        if page_md.strip():
            md_sections.append(page_md)

    doc.close()

    markdown = "\n\n---\n\n".join(md_sections)
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Converted: {pdf_path} -> {output_path}")
    if images_dir.exists():
        image_count = sum(1 for _ in images_dir.iterdir())
        if image_count:
            print(f"Extracted {image_count} image(s) to: {images_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pdf2md",
        description="Convert a PDF file to Markdown, extracting embedded images.",
    )
    parser.add_argument("pdf", type=Path, help="Path to the input PDF file")
    parser.add_argument(
        "-o", "--output",
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

    pdf_path: Path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if pdf_path.suffix.lower() != ".pdf":
        print(f"Error: Input must be a PDF file: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    output_path: Path = args.output if args.output else Path.cwd() / pdf_path.with_suffix(".md").name

    convert(pdf_path, output_path.resolve(), images_dir_name=args.images_dir)


if __name__ == "__main__":
    main()
