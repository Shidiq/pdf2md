#!/usr/bin/env python3
"""pdf2md web app — upload a PDF, get back a Markdown zip."""

import io
import zipfile
from pathlib import Path

try:
    from flask import (
        Flask,
        render_template_string,
        request,
        send_file,
        jsonify,
    )
except ImportError:
    raise SystemExit("Flask is required. Install it with: pip install flask")

from pdf2md import convert

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit

OUTPUT_DIR = Path(__file__).parent / "output"

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>pdf2md</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }

    .card {
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 4px 24px rgba(0,0,0,.08);
      padding: 2.5rem 2rem;
      width: 100%;
      max-width: 540px;
    }

    h1 {
      font-size: 1.6rem;
      font-weight: 700;
      margin-bottom: .35rem;
      color: #111;
    }
    .subtitle {
      font-size: .9rem;
      color: #666;
      margin-bottom: 2rem;
    }

    /* Drop zone */
    .drop-zone {
      border: 2px dashed #ccc;
      border-radius: 8px;
      padding: 2.5rem 1rem;
      text-align: center;
      cursor: pointer;
      transition: border-color .2s, background .2s;
      position: relative;
    }
    .drop-zone.hover {
      border-color: #4f46e5;
      background: #f0f0ff;
    }
    .drop-zone input[type="file"] {
      position: absolute;
      inset: 0;
      opacity: 0;
      cursor: pointer;
      width: 100%;
      height: 100%;
    }
    .drop-zone .icon {
      font-size: 2.5rem;
      margin-bottom: .5rem;
      display: block;
    }
    .drop-zone .label {
      font-size: .95rem;
      color: #555;
    }
    .drop-zone .label strong { color: #4f46e5; }
    #file-name {
      margin-top: .6rem;
      font-size: .85rem;
      color: #333;
      min-height: 1.2em;
    }

    /* Options */
    .options {
      margin-top: 1.25rem;
      display: flex;
      align-items: center;
      gap: .5rem;
      font-size: .9rem;
      color: #444;
    }
    .options input[type="checkbox"] { width: 16px; height: 16px; accent-color: #4f46e5; }

    /* Button */
    button[type="submit"] {
      margin-top: 1.5rem;
      width: 100%;
      padding: .75rem;
      background: #4f46e5;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background .2s;
    }
    button[type="submit"]:hover { background: #4338ca; }
    button[type="submit"]:disabled { background: #a5a0f0; cursor: not-allowed; }

    /* Progress */
    #progress-wrap {
      margin-top: 1.25rem;
      display: none;
    }
    .progress-bar-bg {
      background: #e5e7eb;
      border-radius: 999px;
      height: 6px;
      overflow: hidden;
    }
    .progress-bar-fill {
      height: 100%;
      width: 0%;
      background: #4f46e5;
      border-radius: 999px;
      transition: width .3s ease;
    }
    #progress-label {
      margin-top: .4rem;
      font-size: .82rem;
      color: #666;
    }

    /* Result */
    #result {
      margin-top: 1.5rem;
      display: none;
    }
    .result-box {
      border-radius: 8px;
      padding: 1rem 1.25rem;
      font-size: .9rem;
    }
    .result-box.success {
      background: #f0fdf4;
      border: 1px solid #86efac;
      color: #166534;
    }
    .result-box.error {
      background: #fef2f2;
      border: 1px solid #fca5a5;
      color: #991b1b;
    }
    .result-box .stats { margin-top: .4rem; font-size: .82rem; opacity: .8; }
    .download-btn {
      display: inline-block;
      margin-top: .9rem;
      padding: .55rem 1.2rem;
      background: #166534;
      color: #fff;
      border-radius: 6px;
      font-size: .9rem;
      font-weight: 600;
      text-decoration: none;
      transition: background .2s;
    }
    .download-btn:hover { background: #14532d; }
  </style>
</head>
<body>
  <div class="card">
    <h1>pdf2md</h1>
    <p class="subtitle">Convert a PDF to Markdown — extracts text, images, and comments.</p>

    <form id="upload-form" enctype="multipart/form-data">
      <div class="drop-zone" id="drop-zone">
        <input type="file" name="pdf" id="pdf-input" accept=".pdf" required />
        <span class="icon">📄</span>
        <div class="label"><strong>Click to browse</strong> or drag &amp; drop a PDF</div>
      </div>
      <div id="file-name"></div>

      <label class="options">
        <input type="checkbox" name="extract_comments" id="extract-comments" checked />
        Extract annotations &amp; comments
      </label>

      <button type="submit" id="submit-btn">Convert</button>
    </form>

    <div id="progress-wrap">
      <div class="progress-bar-bg"><div class="progress-bar-fill" id="progress-fill"></div></div>
      <div id="progress-label">Uploading…</div>
    </div>

    <div id="result"></div>
  </div>

  <script>
    const dropZone   = document.getElementById('drop-zone');
    const fileInput  = document.getElementById('pdf-input');
    const fileLabel  = document.getElementById('file-name');
    const form       = document.getElementById('upload-form');
    const submitBtn  = document.getElementById('submit-btn');
    const progWrap   = document.getElementById('progress-wrap');
    const progFill   = document.getElementById('progress-fill');
    const progLabel  = document.getElementById('progress-label');
    const resultDiv  = document.getElementById('result');

    // Drag-and-drop styling
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('hover'); });
    ['dragleave', 'drop'].forEach(ev => dropZone.addEventListener(ev, () => dropZone.classList.remove('hover')));

    fileInput.addEventListener('change', () => {
      fileLabel.textContent = fileInput.files[0]?.name ?? '';
    });

    form.addEventListener('submit', async e => {
      e.preventDefault();
      const file = fileInput.files[0];
      if (!file) return;

      const fd = new FormData(form);

      submitBtn.disabled = true;
      progWrap.style.display = 'block';
      resultDiv.style.display = 'none';
      progFill.style.width = '0%';
      progLabel.textContent = 'Uploading…';

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/convert');

      xhr.upload.addEventListener('progress', ev => {
        if (!ev.lengthComputable) return;
        const pct = Math.round(ev.loaded / ev.total * 60);
        progFill.style.width = pct + '%';
        progLabel.textContent = pct < 60 ? 'Uploading…' : 'Converting…';
      });

      xhr.addEventListener('load', () => {
        progFill.style.width = '100%';
        progLabel.textContent = 'Done';

        let data;
        try { data = JSON.parse(xhr.responseText); } catch { data = { error: 'Unexpected server response.' }; }

        resultDiv.style.display = 'block';
        if (xhr.status === 200 && data.download_url) {
          resultDiv.innerHTML = `
            <div class="result-box success">
              <strong>Conversion complete!</strong>
              <div class="stats">
                ${data.images_count} image(s) extracted &nbsp;·&nbsp;
                ${data.annotation_count} annotation(s)/comment(s) found
              </div>
              <a class="download-btn" href="${data.download_url}" download>Download ZIP</a>
            </div>`;
        } else {
          resultDiv.innerHTML = `<div class="result-box error"><strong>Error:</strong> ${data.error ?? 'Unknown error.'}</div>`;
        }
        submitBtn.disabled = false;
      });

      xhr.addEventListener('error', () => {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = '<div class="result-box error">Network error. Is the server running?</div>';
        submitBtn.disabled = false;
      });

      xhr.send(fd);
    });
  </script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(_HTML)


@app.route("/convert", methods=["POST"])
def convert_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    pdf_file = request.files["pdf"]
    if not pdf_file.filename or not pdf_file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file."}), 400

    extract_comments = "extract_comments" in request.form

    # Sanitise the stem (strip path components from browser-supplied filename)
    pdf_stem = Path(pdf_file.filename).stem
    safe_stem = "".join(c if c.isalnum() or c in "-_ " else "_" for c in pdf_stem).strip() or "output"

    # Output folder: output/{safe_stem}/
    out_dir = OUTPUT_DIR / safe_stem
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = out_dir / f"{safe_stem}.pdf"
    pdf_file.save(str(pdf_path))

    md_path = out_dir / f"{safe_stem}.md"

    try:
        result = convert(
            pdf_path=pdf_path,
            output_path=md_path,
            images_dir_name="images",
            extract_comments=extract_comments,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "download_url": f"/download/{safe_stem}",
            "images_count": result["images_count"],
            "annotation_count": result["annotation_count"],
        }
    )


@app.route("/download/<name>")
def download(name: str):
    # Prevent path traversal
    safe_name = Path(name).name
    folder = OUTPUT_DIR / safe_name
    if not folder.is_dir():
        return "Not found", 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder.rglob("*"):
            if f.is_file() and f.suffix.lower() != ".pdf":
                zf.write(f, f.relative_to(folder))
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{safe_name}.zip",
    )


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    app.run(debug=True, port=5000)
