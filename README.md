# pdf2md

A tool to convert PDF files to Markdown (`.md`), with automatic image extraction and inline citation. Available as both a CLI and a web app.

![pdf2md web interface](Assets/home.png)

## Features

- Converts text-based PDFs to clean Markdown
- Detects headings by font size (H1/H2/H3)
- Preserves **bold** and *italic* formatting
- Extracts embedded images and saves them as files
- Cites extracted images inline in the Markdown output
- Separates pages with horizontal rules (`---`)

## Requirements

- Python 3.10+
- [PyMuPDF](https://pymupdf.readthedocs.io/) (`pymupdf`)
- [Flask](https://flask.palletsprojects.com/) (`flask`) — for the web app only

## Installation

```bash
git clone https://github.com/Shidiq/pdf2md.git
cd pdf2md
pip install -r requirements.txt
```

## Usage

### CLI

```bash
python pdf2md.py <input.pdf>
```

The output `.md` file is written to the current directory with the same base name as the PDF.

#### Options

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Path for the output `.md` file (default: `<input>.md` in current dir) |
| `--images-dir` | Subdirectory name for extracted images (default: `images`) |

#### Examples

```bash
# Basic conversion
python pdf2md.py report.pdf

# Custom output path
python pdf2md.py report.pdf -o output/report.md

# Custom images directory
python pdf2md.py report.pdf --images-dir assets
```

### Web App

```bash
python app.py
```

Then open `http://localhost:5000` in your browser. Upload a PDF and download a `.zip` containing the Markdown file and any extracted images.

## Output Structure

```
output/
├── report.md         # Markdown output
└── images/           # Extracted images (if any)
    ├── page1_img1.png
    ├── page2_img1.jpeg
    └── ...
```

Images are cited in the Markdown like this:

```markdown
![Figure 1 (page 3)](images/page3_img1.png)
```

## Limitations

- Works only on **text-based PDFs** (not scanned/image-only PDFs). For scanned PDFs, OCR pre-processing is required.
- Heading detection is heuristic (based on font size ratios) and may not be perfect for all PDFs.

## License

MIT
