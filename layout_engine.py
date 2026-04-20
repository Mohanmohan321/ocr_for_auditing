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
        "tamil":     ["கடை", "ஹோட்டல்", "உணவகம்", "மெஸ்", "ஸ்டோர்", "மார்ட்"],
        "hindi":     ["दुकान", "होटल", "रेस्टोरेंट", "भंडार", "स्टोर", "मार्ट"],
        "telugu":    ["దుకాణం", "హోటల్", "రెస్టారెంట్", "స్టోర్", "మార్ట్"],
        "kannada":   ["ಅಂಗಡಿ", "ಹೋಟೆಲ್", "ರೆಸ್ಟೋರೆಂಟ್", "ಸ್ಟೋರ್", "ಮಾರ್ಟ್"],
        "malayalam": ["കട", "ഹോട്ടൽ", "റെസ്റ്റോറന്റ്", "സ്റ്റോർ", "മാർട്ട്"],
        "bengali":   ["দোকান", "হোটেল", "রেস্টুরেন্ট", "স্টোর", "মার্ট"],
        "gujarati":  ["દુકાન", "હોટેલ", "રેસ્ટોરન્ટ", "સ્ટોર", "માર્ટ"],
        "english":   ["hotel", "restaurant", "mess", "store", "mart", "shop",
                      "cafe", "bakery", "sweets", "enterprises", "traders"],
    },
    "total": {
        "tamil":     ["மொத்தம்", "மொத்த தொகை", "செலுத்த வேண்டிய"],
        "hindi":     ["कुल", "कुल राशि", "कुल योग", "भुगतान योग्य"],
        "telugu":    ["మొత్తం", "చెల్లించవలసిన"],
        "kannada":   ["ಒಟ್ಟು", "ಒಟ್ಟು ಮೊತ್ತ"],
        "malayalam": ["ആകെ", "മൊത്തം"],
        "bengali":   ["মোট", "সর্বমোট", "প্রদেয়"],
        "gujarati":  ["કુલ", "કુલ રકમ"],
        "english":   ["total", "grand total", "total amount", "net payable",
                      "bill amount", "amount payable", "you pay"],
    },
    "subtotal": {
        "tamil":     ["உட்கூட்டு", "தொகை"],
        "hindi":     ["उप योग", "उप कुल", "कर योग्य"],
        "telugu":    ["ఉప మొత్తం", "పన్ను విలువ"],
        "kannada":   ["ಉಪ ಮೊತ್ತ", "ತೆರಿಗೆ ಮೌಲ್ಯ"],
        "malayalam": ["ഉപ ആകെ", "നികുതി മൂല്യം"],
        "bengali":   ["উপমোট", "করযোগ্য"],
        "gujarati":  ["ઉપ કુલ", "કરપાત્ર"],
        "english":   ["subtotal", "sub total", "sub-total", "net amount",
                      "taxable value", "taxable"],
    },
    "gst": {
        "tamil":     ["வரி", "மத்திய வரி", "மாநில வரி"],
        "hindi":     ["कर", "केंद्रीय कर", "राज्य कर", "जीएसटी"],
        "telugu":    ["పన్ను", "కేంద్ర పన్ను", "రాష్ట్ర పన్ను"],
        "kannada":   ["ತೆರಿಗೆ", "ಕೇಂದ್ರ ತೆರಿಗೆ", "ರಾಜ್ಯ ತೆರಿಗೆ"],
        "malayalam": ["നികുതി", "കേന്ദ്ര നികുതി", "സംസ്ഥാന നികുതി"],
        "bengali":   ["কর", "কেন্দ্রীয় কর", "রাজ্য কর"],
        "gujarati":  ["કર", "કેન્દ્રીય કર", "રાજ્ય કર"],
        "english":   ["cgst", "sgst", "igst", "gst", "tax", "central tax",
                      "state tax"],
    },
    "item_header": {
        "tamil":     ["பொருள்", "விவரம்", "எண்ணிக்கை"],
        "hindi":     ["वस्तु", "विवरण", "मात्रा", "दर", "राशि"],
        "telugu":    ["వస్తువు", "వివరణ", "పరిమాణం"],
        "kannada":   ["ವಸ್ತು", "ವಿವರಣೆ", "ಪ್ರಮಾಣ"],
        "malayalam": ["ഇനം", "വിവരണം", "അളവ്"],
        "bengali":   ["পণ্য", "বিবরণ", "পরিমাণ"],
        "gujarati":  ["વસ્તુ", "વિગત", "જથ્થો"],
        "english":   ["item", "description", "particular", "particulars",
                      "product", "qty", "quantity", "rate", "price",
                      "amount", "sl", "s.no", "sno", "hsn", "sac"],
    },
    "date": {
        "tamil":     ["தேதி", "நாள்"],
        "hindi":     ["तारीख", "दिनांक"],
        "telugu":    ["తేదీ"],
        "kannada":   ["ದಿನಾಂಕ"],
        "malayalam": ["തീയതി"],
        "bengali":   ["তারিখ"],
        "gujarati":  ["તારીખ"],
        "english":   ["date", "dt", "dated"],
    },
    "invoice": {
        "tamil":     ["பில்", "இரசீது"],
        "hindi":     ["बिल", "चालान", "रसीद"],
        "telugu":    ["బిల్లు", "రసీదు"],
        "kannada":   ["ಬಿಲ್", "ರಸೀದಿ"],
        "malayalam": ["ബിൽ", "രസീത്"],
        "bengali":   ["বিল", "চালান", "রসিদ"],
        "gujarati":  ["બિલ", "ચલણ", "રસીદ"],
        "english":   ["invoice", "bill", "receipt", "voucher", "ref"],
    },
}


def match_keyword(text: str, category: str) -> bool:
    """Language-agnostic keyword match — checks ALL supported languages."""
    lower = text.lower()
    kw = KEYWORDS.get(category, {})
    for lang, words in kw.items():
        if lang == "english":
            if any(w in lower for w in words):
                return True
        else:
            # Non-Latin scripts: match against original text (case-insensitive N/A)
            if any(w in text for w in words):
                return True
    return False


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
