#!/usr/bin/env python3
"""
search_pdfs.py — Search a folder of PDFs for a phrase.

Tries fast text-layer extraction first (pdfplumber).
Falls back to OCR (pytesseract) for scanned/image-only pages.

Usage:
    python search_pdfs.py /path/to/pdf/folder "both loved and hated"

Optional flags:
    --ext        File extension to scan (default: pdf)
    --dpi        DPI for OCR rasterization (default: 200)
    --no-ocr     Skip OCR fallback, text-layer only
    --output     Write results to a text file as well

Requirements:
    pip install pdfplumber pytesseract Pillow pymupdf
    brew install tesseract poppler          # macOS
    apt install tesseract-ocr poppler-utils # Linux
"""

import argparse
import sys
import os
from pathlib import Path

# ── Dependency check ────────────────────────────────────────────────────────
missing = []
try:
    import pdfplumber
except ImportError:
    missing.append("pdfplumber")
try:
    import pytesseract
    from PIL import Image
except ImportError:
    missing.append("pytesseract Pillow")
try:
    import fitz  # PyMuPDF — for rasterizing pages for OCR
except ImportError:
    missing.append("pymupdf")

if missing:
    print(f"Missing packages: {', '.join(missing)}")
    print(f"Install with: pip install {' '.join(missing)}")
    sys.exit(1)


def extract_text_layer(pdf_path: Path, page_num: int) -> str:
    """Extract text from a page using pdfplumber (fast, text-layer only)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num < len(pdf.pages):
                text = pdf.pages[page_num].extract_text() or ""
                return text
    except Exception:
        pass
    return ""


def ocr_page(pdf_path: Path, page_num: int, dpi: int) -> str:
    """Rasterize a page and run Tesseract OCR on it."""
    try:
        doc = fitz.open(str(pdf_path))
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_data = pix.tobytes("png")
        doc.close()

        from io import BytesIO
        img = Image.open(BytesIO(img_data))
        text = pytesseract.image_to_string(img, lang="eng")
        return text
    except Exception as e:
        return ""


def search_pdf(pdf_path: Path, phrase: str, dpi: int, use_ocr: bool) -> list[dict]:
    """
    Search a single PDF for phrase. Returns list of hits:
    [{"file": ..., "page": ..., "method": ..., "context": ...}]
    """
    hits = []
    phrase_lower = phrase.lower()

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
    except Exception as e:
        print(f"  ⚠ Could not open {pdf_path.name}: {e}")
        return hits

    for page_num in range(page_count):
        display_page = page_num + 1  # 1-indexed for humans

        # Try text layer first
        text = extract_text_layer(pdf_path, page_num)
        method = "text-layer"

        # If empty or very short, fall back to OCR
        if use_ocr and len(text.strip()) < 20:
            text = ocr_page(pdf_path, page_num, dpi)
            method = "OCR"

        if phrase_lower in text.lower():
            # Find context: 120 chars around the match
            idx = text.lower().find(phrase_lower)
            start = max(0, idx - 120)
            end = min(len(text), idx + len(phrase) + 120)
            context = text[start:end].replace("\n", " ").strip()
            # Clean up excessive whitespace
            import re
            context = re.sub(r"\s+", " ", context)

            hits.append({
                "file":    pdf_path.name,
                "path":    str(pdf_path),
                "page":    display_page,
                "method":  method,
                "context": f"...{context}...",
            })

    return hits


def main():
    parser = argparse.ArgumentParser(
        description="Search a folder of PDFs for a phrase."
    )
    parser.add_argument("folder",  help="Folder containing PDFs")
    parser.add_argument("phrase",  help="Phrase to search for (case-insensitive)")
    parser.add_argument("--ext",     default="pdf", help="File extension (default: pdf)")
    parser.add_argument("--dpi",     type=int, default=200, help="OCR rasterization DPI (default: 200)")
    parser.add_argument("--no-ocr",  action="store_true", help="Skip OCR, text-layer only")
    parser.add_argument("--output",  help="Write results to this file")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory.")
        sys.exit(1)

    pdfs = sorted(folder.rglob(f"*.{args.ext.lstrip('.')}"))
    if not pdfs:
        print(f"No .{args.ext} files found in {folder}")
        sys.exit(0)

    use_ocr = not args.no_ocr
    print(f"\nSearching {len(pdfs)} PDF(s) in '{folder}' for: \"{args.phrase}\"")
    print(f"OCR fallback: {'enabled' if use_ocr else 'disabled'} | DPI: {args.dpi}\n")
    print("─" * 70)

    all_hits = []

    for i, pdf_path in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf_path.name}", end="", flush=True)
        hits = search_pdf(pdf_path, args.phrase, args.dpi, use_ocr)
        if hits:
            print(f"  → {len(hits)} hit(s)")
            for h in hits:
                print(f"     p.{h['page']} [{h['method']}]")
                print(f"     {h['context']}")
                print()
            all_hits.extend(hits)
        else:
            print("  (no match)")

    print("─" * 70)
    print(f"\nDone. {len(all_hits)} hit(s) across {len(pdfs)} file(s).\n")

    if all_hits:
        print("RESULTS SUMMARY:")
        for h in all_hits:
            print(f"  {h['file']}  —  page {h['page']}  [{h['method']}]")

    # Optionally write to file
    if args.output:
        out_path = Path(args.output)
        with open(out_path, "w") as f:
            f.write(f'Search: "{args.phrase}"\n')
            f.write(f"Folder: {folder}\n")
            f.write(f"Files searched: {len(pdfs)}\n")
            f.write(f"Hits: {len(all_hits)}\n\n")
            f.write("─" * 70 + "\n\n")
            for h in all_hits:
                f.write(f"FILE: {h['file']}\n")
                f.write(f"PAGE: {h['page']}  |  METHOD: {h['method']}\n")
                f.write(f"CONTEXT:\n{h['context']}\n\n")
                f.write("─" * 40 + "\n\n")
        print(f"\nResults written to: {out_path}")


if __name__ == "__main__":
    main()
