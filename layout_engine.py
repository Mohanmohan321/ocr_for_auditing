"""
Layout Engine: Layout-aware OCR with Y-coordinate row clustering.

Uses PaddleOCR (dual-language: Tamil + English) for bounding box extraction,
then clusters text fragments into rows by Y-position and sorts left-to-right.

This gives the parser spatial awareness — it knows which text
fragments are on the same line, which is critical for bills where
item name, qty, price, total are in columns.
"""
import logging
import re
import numpy as np

from paddle_ocr_engine import run_paddle_ocr, avg_confidence as _avg_conf

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bilingual keyword dictionaries (language-agnostic matching)
# ---------------------------------------------------------------------------

KEYWORDS = {
    "vendor": {
        "tamil": ["கடை", "ஹோட்டல்", "உணவகம்", "மெஸ்", "ஸ்டோர்", "மார்ட்"],
        "english": ["hotel", "restaurant", "mess", "store", "mart", "shop",
                     "cafe", "bakery", "sweets", "enterprises", "traders"],
    },
    "total": {
        "tamil": ["மொத்தம்", "மொத்த தொகை", "செலுத்த வேண்டிய"],
        "english": ["total", "grand total", "total amount", "net payable",
                     "bill amount", "amount payable", "you pay"],
    },
    "subtotal": {
        "tamil": ["உட்கூட்டு", "தொகை"],
        "english": ["subtotal", "sub total", "sub-total", "net amount",
                     "taxable value", "taxable"],
    },
    "gst": {
        "tamil": ["வரி", "மத்திய வரி", "மாநில வரி"],
        "english": ["cgst", "sgst", "igst", "gst", "tax", "central tax",
                     "state tax"],
    },
    "item_header": {
        "tamil": ["பொருள்", "விவரம்", "எண்ணிக்கை"],
        "english": ["item", "description", "particular", "particulars",
                     "product", "qty", "quantity", "rate", "price",
                     "amount", "sl", "s.no", "sno", "hsn", "sac"],
    },
    "date": {
        "tamil": ["தேதி", "நாள்"],
        "english": ["date", "dt", "dated"],
    },
    "invoice": {
        "tamil": ["பில்", "இரசீது"],
        "english": ["invoice", "bill", "receipt", "voucher", "ref"],
    },
}


def match_keyword(text: str, category: str) -> bool:
    """Language-agnostic keyword match — checks both Tamil and English."""
    lower = text.lower()
    kw = KEYWORDS.get(category, {})
    tamil_words = kw.get("tamil", [])
    english_words = kw.get("english", [])
    return (any(w in lower for w in english_words) or
            any(w in text for w in tamil_words))


# ---------------------------------------------------------------------------
# Layout-aware OCR (PaddleOCR)
# ---------------------------------------------------------------------------

def run_ocr_with_layout(img_array: np.ndarray, languages: list[str]) -> list[dict]:
    """
    Run PaddleOCR with bounding boxes for layout-aware parsing.

    Returns list of dicts:
      [{"text": "...", "x": int, "y": int, "w": int, "h": int, "conf": float}, ...]
    Sorted by Y then X.
    """
    return run_paddle_ocr(img_array, languages)


# ---------------------------------------------------------------------------
# Row clustering by Y-coordinate
# ---------------------------------------------------------------------------

def group_rows(ocr_data: list[dict], threshold: int = 0) -> list[list[dict]]:
    """
    Cluster text fragments into rows by Y-coordinate proximity.

    If threshold=0, auto-compute from median text height.
    Fragments within `threshold` pixels of each other vertically
    are considered the same row.

    Returns list of rows, each row sorted left-to-right by X.
    """
    if not ocr_data:
        return []

    # Auto-compute threshold from median text height
    if threshold <= 0:
        heights = [d["h"] for d in ocr_data if d["h"] > 0]
        if heights:
            median_h = sorted(heights)[len(heights) // 2]
            threshold = max(int(median_h * 0.6), 8)
        else:
            threshold = 15

    # Sort by Y coordinate
    sorted_data = sorted(ocr_data, key=lambda d: d["y"])

    rows = []
    for item in sorted_data:
        placed = False
        for row in rows:
            avg_y = sum(c["y"] for c in row) / len(row)
            if abs(avg_y - item["y"]) < threshold:
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])

    # Sort cells left-to-right within each row
    for row in rows:
        row.sort(key=lambda d: d["x"])

    # Sort rows top-to-bottom
    rows.sort(key=lambda row: sum(c["y"] for c in row) / len(row))

    log.info("Layout clustering: %d rows (threshold=%dpx)", len(rows), threshold)
    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rows_to_lines(rows: list[list[dict]]) -> list[str]:
    """Convert layout rows to flat text lines."""
    lines = []
    for row in rows:
        line = "  ".join(cell["text"] for cell in row)
        if line.strip():
            lines.append(line.strip())
    return lines


def row_to_text(row: list[dict]) -> str:
    """Join a single row's cells into text."""
    return "  ".join(cell["text"] for cell in row)


def row_numbers(row: list[dict]) -> list[float]:
    """Extract all numeric values from a row's cells."""
    nums = []
    for cell in row:
        matches = re.findall(r"(\d+\.\d{1,2}|\d+)", cell["text"])
        for m in matches:
            try:
                nums.append(float(m))
            except ValueError:
                pass
    return nums


def row_text_cells(row: list[dict]) -> list[str]:
    """Extract text-only cells from a row."""
    texts = []
    for cell in row:
        alpha = sum(1 for c in cell["text"] if c.isalpha() or ord(c) > 0x0900)
        if alpha >= 2:
            texts.append(cell["text"])
    return texts


def avg_confidence(ocr_data: list[dict]) -> float:
    """Average OCR confidence across all fragments."""
    return _avg_conf(ocr_data)
