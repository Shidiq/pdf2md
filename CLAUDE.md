# pdf2md — CLAUDE.md

## Project Overview
CLI tool that converts PDF files to Markdown (`.md`), extracting embedded images and citing them inline.

## Entry Point
- `pdf2md.py` — single-file CLI, run directly with `python pdf2md.py <file.pdf>`

## Core Dependency
- **PyMuPDF** (`fitz`, package name `pymupdf>=1.24.0`) — used for all PDF parsing, text extraction, and image extraction. Do not swap this out for another library without good reason.

## Key Design Decisions
- Single-file script (no package structure) — keeps it simple and portable.
- Images are saved to a subdirectory (`images/` by default, configurable via `--images-dir`) relative to the output `.md` file.
- Image citations in markdown use the format: `![Figure N (page P)](images/pageP_imgN.ext)`.
- Page breaks are separated in the output with `---` horizontal rules.
- Heading detection is heuristic: font size ratio relative to the most common body font size on each page (≥1.8× → H1, ≥1.5× → H2, ≥1.2× → H3).
- Bold/italic formatting is preserved using PyMuPDF span flags.

## CLI Usage
```
python pdf2md.py <input.pdf> [-o output.md] [--images-dir DIR]
```

## What to Avoid
- Do not add dependencies beyond `pymupdf` unless strictly necessary.
- Do not rewrite as a package/module unless the user explicitly asks.
- Do not OCR — this tool works only on text-based (non-scanned) PDFs.
