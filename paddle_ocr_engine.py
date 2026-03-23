"""
PaddleOCR Engine: Dual-language OCR (Tamil + English) with model caching.

Replaces EasyOCR for higher accuracy on Indian scripts.
Runs both English and Tamil models, merges outputs by removing duplicates
based on bounding box overlap.
"""
import logging
import numpy as np
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model cache (singleton per language)
# ---------------------------------------------------------------------------
_paddle_cache: dict = {}


def _get_paddle_model(lang: str):
    """Get or create a cached PaddleOCR model for the given language."""
    if lang in _paddle_cache:
        return _paddle_cache[lang]

    from paddleocr import PaddleOCR

    log.info("Initializing PaddleOCR model: lang=%s", lang)
    model = PaddleOCR(
        lang=lang,
        use_angle_cls=False,
        show_log=False,
    )
    _paddle_cache[lang] = model
    return model


# ---------------------------------------------------------------------------
# Core OCR function
# ---------------------------------------------------------------------------

def run_paddle_ocr(img_array: np.ndarray, languages: list[str] = None) -> list[dict]:
    """
    Run PaddleOCR on an image with dual-language support.

    Runs English model always. If Tamil (or other Indic language) is selected,
    runs that model too and merges results.

    Args:
        img_array: RGB numpy array of the image
        languages: List of language names (e.g. ["English", "Tamil"])

    Returns:
        List of dicts: [{"text": str, "x": int, "y": int, "w": int, "h": int, "conf": float}]
        Sorted by Y then X.
    """
    if languages is None:
        languages = ["English"]

    # Map language names to PaddleOCR codes
    lang_map = {
        "English": "en",
        "Tamil": "ta",
        "Hindi": "hi",
        "Telugu": "te",
        "Kannada": "ka",
        "Malayalam": "ml",
        "Bengali": "bn",
        "Gujarati": "gu",
        "Marathi": "mr",
        "Punjabi": "pa",
        "Urdu": "ur",
    }

    # Always run English
    paddle_langs = ["en"]
    for lang in languages:
        code = lang_map.get(lang)
        if code and code != "en":
            paddle_langs.append(code)

    # Run OCR for each language and collect results
    all_fragments = []

    for lang_code in paddle_langs:
        try:
            model = _get_paddle_model(lang_code)
            results = model.ocr(img_array, cls=False)

            if not results or not results[0]:
                log.info("PaddleOCR (%s): no results", lang_code)
                continue

            for entry in results[0]:
                bbox, (text, conf) = entry
                text = text.strip()
                if not text:
                    continue

                # bbox = [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                xs = [pt[0] for pt in bbox]
                ys = [pt[1] for pt in bbox]
                x = int(min(xs))
                y = int(min(ys))
                w = int(max(xs) - min(xs))
                h = int(max(ys) - min(ys))

                all_fragments.append({
                    "text": text,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "conf": round(float(conf), 3),
                    "_lang": lang_code,
                })

            log.info("PaddleOCR (%s): %d fragments",
                     lang_code, sum(1 for f in all_fragments if f["_lang"] == lang_code))

        except Exception as e:
            log.error("PaddleOCR (%s) failed: %s", lang_code, e)
            continue

    if not all_fragments:
        log.warning("PaddleOCR: no results from any language model")
        return []

    # Merge results from multiple languages (remove duplicates by overlap)
    if len(paddle_langs) > 1:
        merged = _merge_multilingual(all_fragments)
    else:
        merged = all_fragments

    # Remove internal _lang field
    for f in merged:
        f.pop("_lang", None)

    # Sort by Y then X
    merged.sort(key=lambda d: (d["y"], d["x"]))
    log.info("PaddleOCR total: %d unique fragments", len(merged))

    return merged


# ---------------------------------------------------------------------------
# Merge multilingual results (deduplicate overlapping bboxes)
# ---------------------------------------------------------------------------

def _iou(a: dict, b: dict) -> float:
    """Compute intersection-over-union of two bounding boxes."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def _merge_multilingual(fragments: list[dict]) -> list[dict]:
    """
    Merge OCR results from multiple language models.

    When two fragments from different languages overlap (IoU > 0.5),
    keep the one with higher confidence. This handles the case where
    both English and Tamil models detect the same text region.
    """
    # Group by language
    by_lang = {}
    for f in fragments:
        by_lang.setdefault(f["_lang"], []).append(f)

    if len(by_lang) <= 1:
        return fragments

    # Start with all fragments, mark duplicates
    merged = []
    used = set()

    # Sort all fragments by confidence descending
    all_sorted = sorted(fragments, key=lambda f: f["conf"], reverse=True)

    for i, frag in enumerate(all_sorted):
        if i in used:
            continue

        # Check if this overlaps with any already-accepted fragment
        is_dup = False
        for j, accepted in enumerate(merged):
            if _iou(frag, accepted) > 0.5:
                is_dup = True
                break

        if not is_dup:
            merged.append(frag)
            used.add(i)

    log.info("Merged %d → %d fragments (removed %d duplicates)",
             len(fragments), len(merged), len(fragments) - len(merged))

    return merged


# ---------------------------------------------------------------------------
# Flat lines output (backward compatibility)
# ---------------------------------------------------------------------------

def paddle_ocr_to_lines(fragments: list[dict], row_threshold: int = 0) -> list[str]:
    """
    Convert PaddleOCR fragments to flat text lines by grouping into rows.
    Quick version for backward compatibility with line-based parsers.
    """
    if not fragments:
        return []

    # Auto threshold from median height
    if row_threshold <= 0:
        heights = [f["h"] for f in fragments if f["h"] > 0]
        if heights:
            row_threshold = max(sorted(heights)[len(heights) // 2] // 2, 8)
        else:
            row_threshold = 15

    # Sort by Y
    sorted_frags = sorted(fragments, key=lambda f: f["y"])

    rows = []
    for frag in sorted_frags:
        placed = False
        for row in rows:
            avg_y = sum(f["y"] for f in row) / len(row)
            if abs(avg_y - frag["y"]) < row_threshold:
                row.append(frag)
                placed = True
                break
        if not placed:
            rows.append([frag])

    # Sort cells left-to-right, build lines
    lines = []
    for row in rows:
        row.sort(key=lambda f: f["x"])
        line = "  ".join(f["text"] for f in row)
        if line.strip():
            lines.append(line.strip())

    return lines


def avg_confidence(fragments: list[dict]) -> float:
    """Average OCR confidence across all fragments."""
    if not fragments:
        return 0.0
    return sum(f["conf"] for f in fragments) / len(fragments)
