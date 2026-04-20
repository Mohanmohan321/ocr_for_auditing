"""
OCR Utilities: Text normalization, language detection, noise correction,
Tamil→English translation, and quality estimation.

Core principle: fix noise FIRST, then detect language, then translate.
"""
import re
import logging
import unicodedata

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unicode ranges for all supported Indic scripts
# ---------------------------------------------------------------------------
SCRIPT_RANGES = {
    "Hindi":     re.compile(r"[\u0900-\u097F]"),   # Devanagari
    "Tamil":     re.compile(r"[\u0B80-\u0BFF]"),
    "Telugu":    re.compile(r"[\u0C00-\u0C7F]"),
    "Kannada":   re.compile(r"[\u0C80-\u0CFF]"),
    "Malayalam": re.compile(r"[\u0D00-\u0D7F]"),
    "Bengali":   re.compile(r"[\u0980-\u09FF]"),
    "Gujarati":  re.compile(r"[\u0A80-\u0AFF]"),
    "Punjabi":   re.compile(r"[\u0A00-\u0A7F]"),   # Gurmukhi
    "Odia":      re.compile(r"[\u0B00-\u0B7F]"),
    "Urdu":      re.compile(r"[\u0600-\u06FF]"),    # Arabic script
    "Assamese":  re.compile(r"[\u0980-\u09FF]"),    # shares Bengali range
    "Nepali":    re.compile(r"[\u0900-\u097F]"),    # shares Devanagari
}

TAMIL_RANGE = SCRIPT_RANGES["Tamil"]
DEVANAGARI_RANGE = SCRIPT_RANGES["Hindi"]
NON_LATIN = re.compile(
    r"[\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF"
    r"\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF"
    r"\u0D00-\u0D7F\u0600-\u06FF]"
)

# ---------------------------------------------------------------------------
# Step 1: OCR noise correction map
# ---------------------------------------------------------------------------
# Common OCR misreads on Indian bills — applied BEFORE any extraction.
OCR_WORD_CORRECTIONS = {
    # GST family
    "6T600T": "GSTIN", "6STIN": "GSTIN", "G5TIN": "GSTIN",
    "GST1N": "GSTIN", "GSTLN": "GSTIN", "GS7IN": "GSTIN",
    "G$TIN": "GSTIN", "6ST": "GST", "G5T": "GST", "GS7": "GST",
    "C6ST": "CGST", "CG5T": "CGST", "CGSI": "CGST",
    "S6ST": "SGST", "SG5T": "SGST", "SGSI": "SGST",
    "I6ST": "IGST",
    # Invoice / bill
    "1nvoice": "Invoice", "lnvoice": "Invoice", "Inv0ice": "Invoice",
    "INVOI CE": "INVOICE", "INV0ICE": "INVOICE",
    "8ill": "Bill", "B1ll": "Bill",
    # Amount/total
    "T0tal": "Total", "Tota1": "Total", "TOTA1": "TOTAL",
    "TOT AL": "TOTAL", "Sub Total": "Subtotal", "Sub total": "Subtotal",
    "SUB TOTAL": "SUBTOTAL", "Sub-Total": "Subtotal",
    # Qty / price
    "0ty": "Qty", "Qly": "Qty",
    "Arnount": "Amount", "Arnout": "Amount", "Arnnt": "Amount",
    "Amourt": "Amount", "Amounl": "Amount",
    "Prlce": "Price", "Pr1ce": "Price",
    "Rs_": "Rs.", "Rs,": "Rs.",
    "ltem": "Item", "ltems": "Items",
    "Partlculars": "Particulars", "Descrlption": "Description",
}

# Single-character OCR fixes (applied only in specific contexts)
CHAR_FIXES_IN_NUMBERS = {
    "O": "0", "o": "0",
    "I": "1", "l": "1",
    "S": "5", "B": "8",
}


def _fix_word_noise(text: str) -> str:
    """Replace known OCR misread words."""
    result = text
    for wrong, right in OCR_WORD_CORRECTIONS.items():
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        result = pattern.sub(right, result)
    return result


def _fix_char_noise_in_numbers(text: str) -> str:
    """
    Fix O→0, I→1, l→1 ONLY inside number-like sequences.
    e.g. "Rs.1O5.OO" → "Rs.105.00", but "Invoice" stays "Invoice".
    """
    def replacer(m):
        segment = m.group(0)
        for wrong, right in CHAR_FIXES_IN_NUMBERS.items():
            segment = segment.replace(wrong, right)
        return segment

    # Match sequences that look like numbers with OCR errors mixed in
    # e.g. "1O5.OO" or "7,5OO.O0" or "1,2I5"
    return re.sub(
        r"\d[\d,.\sOoIlSB]*\d",
        replacer,
        text,
    )


def _normalize_number_format(text: str) -> str:
    """Remove commas from numbers so '1,234.56' becomes '1234.56' for parsing."""
    return re.sub(r"(\d),(\d)", r"\1\2", text)


# ---------------------------------------------------------------------------
# Step 1 (public): Full text normalization
# ---------------------------------------------------------------------------

def normalize_ocr_text(raw_lines: list[str]) -> list[str]:
    """
    Step 1 of pipeline: Normalize raw OCR text.
    - Unicode NFC normalization (critical for Tamil combining chars)
    - Fix known word-level OCR mistakes
    - Fix character-level noise in number sequences
    - Normalize number formatting
    - Collapse whitespace
    - Drop empty lines
    """
    cleaned = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        line = unicodedata.normalize("NFC", line)
        line = _fix_word_noise(line)
        line = _fix_char_noise_in_numbers(line)
        line = _normalize_number_format(line)
        line = re.sub(r"\s{2,}", " ", line)
        if line:
            cleaned.append(line)
    return cleaned


# ---------------------------------------------------------------------------
# Step 2: Language detection
# ---------------------------------------------------------------------------

def detect_languages(text: str) -> list[str]:
    """
    Auto-detect all languages present in text using Unicode script ranges.
    Checks all supported Indic scripts plus English.
    """
    detected = []

    for lang_name, pattern in SCRIPT_RANGES.items():
        if pattern.search(text) and lang_name not in detected:
            detected.append(lang_name)

    # Deduplicate shared ranges: Assamese/Bengali, Nepali/Hindi
    if "Assamese" in detected and "Bengali" in detected:
        detected.remove("Assamese")
    if "Nepali" in detected and "Hindi" in detected:
        detected.remove("Nepali")

    latin_count = sum(1 for c in text if c.isascii() and c.isalpha())
    if latin_count > 0:
        detected.append("English")

    return detected if detected else ["Unknown"]


def has_tamil(text: str) -> bool:
    return bool(TAMIL_RANGE.search(text))


def has_non_latin(text: str) -> bool:
    return bool(NON_LATIN.search(text))


# ---------------------------------------------------------------------------
# Step 3: Tamil → English translation
# ---------------------------------------------------------------------------

def translate_to_english(lines: list[str]) -> tuple[list[str], list[str]]:
    """
    Auto-translate any non-Latin text to English.
    Uses deep-translator with source='auto' so it works for ALL languages
    (Tamil, Hindi, Telugu, Kannada, Malayalam, Bengali, Gujarati, Urdu, etc.)

    Returns:
        (original_lines, translated_lines)
        If no non-Latin text found, translated_lines == original_lines.
    """
    has_indic = any(has_non_latin(line) for line in lines)

    if not has_indic:
        log.info("All text is Latin/English — skipping translation")
        return lines, lines

    detected = detect_languages("\n".join(lines))
    non_english = [l for l in detected if l != "English" and l != "Unknown"]
    log.info("Non-Latin text detected (%s) — auto-translating to English",
             ", ".join(non_english) if non_english else "unknown script")

    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        log.warning("deep-translator not installed — skipping translation")
        return lines, lines

    translated = []
    for line in lines:
        if has_non_latin(line):
            try:
                result = GoogleTranslator(source="auto", target="en").translate(line)
                translated.append(result if result else line)
            except Exception as e:
                log.debug("Translation failed for '%s': %s", line[:40], e)
                translated.append(line)
        else:
            translated.append(line)

    return lines, translated


# ---------------------------------------------------------------------------
# OCR quality / noise estimation
# ---------------------------------------------------------------------------

def estimate_ocr_noise(lines: list[str]) -> float:
    """
    Estimate how noisy the OCR output is (0.0 = clean, 1.0 = garbage).
    Used for the -10 noise deduction in confidence scoring.
    """
    if not lines:
        return 1.0

    full_text = "\n".join(lines)

    # Characters that are normal in bills
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789 .,;:/-()@#&%*+='\"!?\n\t₹$€£"
    )

    total_latin = 0
    suspicious = 0
    for c in full_text:
        # Skip Tamil / Indic chars — they are expected
        if NON_LATIN.match(c):
            continue
        total_latin += 1
        if c not in allowed:
            suspicious += 1

    return suspicious / total_latin if total_latin > 0 else 0.0


def estimate_ocr_quality(lines: list[str]) -> float:
    """OCR quality as 0–100 score. Higher = better."""
    if not lines:
        return 0.0

    full_text = "\n".join(lines)
    score = 100.0

    noise = estimate_ocr_noise(lines)
    score -= noise * 100

    if len(full_text) < 20:
        score -= 30
    elif len(full_text) < 50:
        score -= 15

    if len(lines) < 3:
        score -= 20

    # Reward bill-related keywords
    keywords = ["total", "amount", "invoice", "bill", "gst", "date",
                "qty", "price", "rs", "subtotal", "tax"]
    text_lower = full_text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    score += hits * 2

    return max(0.0, min(100.0, score))
