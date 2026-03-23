"""
Hybrid Parser v2: Layout-aware, language-agnostic bill extraction.

Pipeline: OCR → Clean → Layout Clustering → Hybrid Parsing → Validation → Output

Core principles:
  - Language-agnostic: Tamil & English treated equally via bilingual keyword dicts
  - Layout-first: use row position (Y-coordinate) as primary signal
  - Numbers are universal: qty * price = total is the same in any language
  - Strict validation: better to miss than to extract wrong data
  - Hybrid filter: reject items where total > bill total
"""
import re
from layout_engine import (
    match_keyword, row_numbers, row_text_cells, row_to_text,
    rows_to_lines, KEYWORDS,
)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

GSTIN_STRICT = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]\d[Zz][A-Z0-9])\b")
GSTIN_RELAXED = re.compile(r"\b(\d{2}[A-Z0-9]{5}\d{4}[A-Z0-9]{1,2}[Zz][A-Z0-9])\b")

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b"),
    re.compile(r"\b(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})\b"),
]
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?)\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(?<!\.)(?:\+91[\s-]?|0)?([6-9]\d{9})(?!\d)(?!\.)")

INVOICE_KW_PATTERN = re.compile(
    r"(?:invoice|inv|bill|receipt|voucher|ref)[\s.:#\-]*(?:no|num|number)?[\s.:#\-]*([A-Z0-9/\-]{3,20})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Meta line detection
# ---------------------------------------------------------------------------

def _is_meta_line(line: str) -> bool:
    """Lines with dates or times — never parse as items."""
    if re.search(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}", line):
        return True
    if re.search(r"\d{1,2}:\d{2}", line):
        return True
    return False


def _is_skip_row(row_text: str) -> bool:
    """Should this row be skipped during item extraction?"""
    if _is_meta_line(row_text):
        return True
    lower = row_text.lower()
    if re.match(r"^(?:date|dt|phone|mobile|tel|gstin|gst\s*no|bill|invoice)", lower):
        return True
    if PHONE_PATTERN.search(row_text):
        return True
    if GSTIN_STRICT.search(row_text) or GSTIN_RELAXED.search(row_text):
        return True
    if re.search(r"\b\d{6}\b", row_text) and not re.search(r"\d+\.\d{2}", row_text):
        return True
    return False


# ---------------------------------------------------------------------------
# Strict validation
# ---------------------------------------------------------------------------

def _math_validates(qty: float, price: float, total: float) -> bool:
    """qty * price ≈ total within Rs.5 or 2%."""
    if qty <= 0 or price <= 0 or total <= 0:
        return False
    expected = qty * price
    tolerance = max(total * 0.02, 5.0)
    return abs(expected - total) <= tolerance


def _is_valid_item(item: dict) -> bool:
    """Strict validation gate. Reject garbage aggressively."""
    qty = item.get("qty")
    price = item.get("price")
    total = item.get("total")

    if total is None and price is None:
        return False

    if qty is not None and (qty <= 0 or qty > 50):
        return False

    if qty is not None and price is not None and total is not None:
        if not _math_validates(qty, price, total):
            return False

    if price is not None and total is not None and qty is None:
        if total < price * 0.5:
            return False

    return True


# ---------------------------------------------------------------------------
# LAYOUT-AWARE VENDOR DETECTION
# ---------------------------------------------------------------------------

def detect_vendor(rows: list[list[dict]]) -> str | None:
    """
    Hybrid vendor detection from top rows.
    Scores lines by: Tamil text presence, vendor keywords, text length.
    """
    best = None
    best_score = 0

    skip_keywords = {"tax", "invoice", "bill", "receipt", "gstin", "gst",
                     "date", "phone", "mobile", "tel", "email", "fax",
                     "original", "duplicate", "copy"}

    for row in rows[:5]:
        line = row_to_text(row)
        stripped = line.strip()
        if not stripped or len(stripped) < 2:
            continue

        lower = stripped.lower()

        # Skip meta lines
        if _is_meta_line(stripped):
            continue
        if any(kw in lower for kw in skip_keywords):
            continue
        if GSTIN_STRICT.search(stripped):
            continue
        if re.match(r"^[\d\s/\-.,:()+]+$", stripped):
            continue

        score = 0

        # Tamil text bonus
        if any("\u0B80" <= c <= "\u0BFF" for c in stripped):
            score += 3

        # Vendor keyword bonus
        if match_keyword(stripped, "vendor"):
            score += 3

        # Length bonus (real names are usually 3+ chars)
        if len(stripped) > 5:
            score += 2
        elif len(stripped) > 2:
            score += 1

        # Position bonus (first row is most likely vendor)
        row_idx = rows.index(row)
        if row_idx == 0:
            score += 2
        elif row_idx == 1:
            score += 1

        if score > best_score:
            best_score = score
            best = stripped

    return best if best_score >= 2 else None


# ---------------------------------------------------------------------------
# LAYOUT-AWARE ITEM EXTRACTION
# ---------------------------------------------------------------------------

def _find_item_rows(rows: list[list[dict]]) -> tuple[int, int]:
    """
    Find start and end indices of the items section using layout rows.
    Returns (start_idx, end_idx) — the item rows are rows[start:end].
    """
    start_idx = None
    end_idx = None

    for i, row in enumerate(rows):
        text = row_to_text(row)

        if start_idx is None:
            # Look for header row (has 2+ column keywords)
            if match_keyword(text, "item_header"):
                words = re.findall(r"[a-zA-Z.]+", text.lower())
                header_kw = {"sl", "sno", "s.no", "no", "description", "particular",
                             "particulars", "item", "product", "qty", "quantity",
                             "rate", "price", "amount", "total", "hsn", "sac", "uom"}
                hits = sum(1 for w in words if w.rstrip(".") in header_kw)
                if hits >= 2:
                    start_idx = i + 1
        else:
            # Look for end
            if match_keyword(text, "subtotal") or match_keyword(text, "gst"):
                end_idx = i
                break
            if match_keyword(text, "total") and row_numbers(row):
                end_idx = i
                break

    return start_idx, end_idx


def extract_items_from_rows(rows: list[list[dict]]) -> list[dict]:
    """
    Layout-aware item extraction.

    Uses row structure: each row's cells are already spatially grouped.
    Extract numbers from each row, validate with qty * price = total.
    """
    start, end = _find_item_rows(rows)

    if start is not None:
        item_rows = rows[start:end] if end else rows[start:]
    elif len(rows) > 8:
        item_rows = rows[3:-3]
    elif len(rows) > 5:
        item_rows = rows[2:-1]
    else:
        item_rows = rows[1:-1] if len(rows) > 2 else rows

    raw_items = []

    for row in item_rows:
        text = row_to_text(row)

        # Skip meta/header/total rows
        if _is_skip_row(text):
            continue
        if match_keyword(text, "total") and row_numbers(row):
            break
        if match_keyword(text, "subtotal") or match_keyword(text, "gst"):
            break

        nums = row_numbers(row)
        text_cells = row_text_cells(row)
        name = " ".join(text_cells) if text_cells else None

        if not nums:
            continue

        item = {"name": name}

        # Try to assign qty, price, total with math validation
        if len(nums) >= 3:
            q, p, t = nums[-3], nums[-2], nums[-1]
            if _math_validates(q, p, t):
                item.update({"qty": q, "price": p, "total": t})
            else:
                # Try all combos
                found = False
                for i in range(len(nums)):
                    for j in range(i + 1, len(nums)):
                        if _math_validates(nums[i], nums[j], nums[-1]):
                            item.update({"qty": nums[i], "price": nums[j], "total": nums[-1]})
                            found = True
                            break
                    if found:
                        break
                if not found:
                    # Fallback: use last two as price, total
                    item["price"] = nums[-2]
                    item["total"] = nums[-1]

        elif len(nums) == 2:
            price, total = nums[-2], nums[-1]
            qty = round(total / price) if price > 0 else 1
            if _math_validates(qty, price, total):
                item.update({"qty": qty, "price": price, "total": total})
            else:
                item["price"] = price
                item["total"] = total

        elif len(nums) == 1:
            item["total"] = nums[0]

        raw_items.append(item)

    # Strict validation gate
    return [item for item in raw_items if _is_valid_item(item)]


# ---------------------------------------------------------------------------
# FALLBACK: line-based extraction (when layout data unavailable)
# ---------------------------------------------------------------------------

def extract_items_from_lines(lines: list[str]) -> list[dict]:
    """Line-based item extraction with positional clustering (fallback)."""
    # Find section boundaries
    start_idx = None
    end_idx = None
    header_kw = {"sl", "sno", "s.no", "no", "description", "particular",
                 "particulars", "item", "product", "qty", "quantity",
                 "rate", "price", "amount", "total", "hsn", "sac", "uom"}

    for i, line in enumerate(lines):
        words = re.findall(r"[a-zA-Z.]+", line.lower())
        hits = sum(1 for w in words if w.rstrip(".") in header_kw)
        nums = re.findall(r"\d+\.\d{1,2}|\d+", line)

        if start_idx is None and hits >= 2 and not nums:
            start_idx = i + 1
        elif start_idx is not None:
            if match_keyword(line, "subtotal") or match_keyword(line, "gst"):
                end_idx = i
                break
            if match_keyword(line, "total") and nums:
                end_idx = i
                break

    if start_idx is not None:
        section = lines[start_idx:end_idx] if end_idx else lines[start_idx:]
    elif len(lines) > 10:
        section = lines[3:-3]
    elif len(lines) > 5:
        section = lines[2:-1]
    else:
        section = lines[1:-1] if len(lines) > 2 else lines

    # Cluster lines into items
    raw_items = []
    pending_text = []
    pending_nums = []

    for line in section:
        stripped = line.strip()
        if _is_skip_row(stripped):
            continue
        if stripped and match_keyword(stripped, "subtotal"):
            break
        if stripped and match_keyword(stripped, "total") and re.findall(r"\d+", stripped):
            break
        if not stripped:
            if pending_text or pending_nums:
                _flush(raw_items, pending_text, pending_nums)
                pending_text, pending_nums = [], []
            continue

        nums = re.findall(r"(\d+\.\d{1,2}|\d+)", stripped)
        nums = [float(n) for n in nums]
        alpha = sum(1 for c in stripped if c.isalpha() or ord(c) > 0x0900)
        text = re.sub(r"[\d,.\s₹]+$", "", stripped).strip()

        if nums and alpha == 0:
            pending_nums.extend(nums)
        elif text and len(text) >= 2 and len(nums) >= 2:
            if pending_text or pending_nums:
                _flush(raw_items, pending_text, pending_nums)
                pending_text, pending_nums = [], []
            item = {"name": text}
            item.update(_assign_nums(nums))
            raw_items.append(item)
        elif text and len(text) >= 2:
            if pending_nums:
                _flush(raw_items, pending_text, pending_nums)
                pending_text, pending_nums = [], []
            pending_text.append(text)
        elif nums:
            pending_nums.extend(nums)

    if pending_text or pending_nums:
        _flush(raw_items, pending_text, pending_nums)

    return [item for item in raw_items if _is_valid_item(item)]


def _flush(items, text_parts, numbers):
    if not numbers:
        return
    name = " ".join(t for t in text_parts if t) if text_parts else None
    if name and len(name) < 2:
        name = None
    item = {"name": name}
    item.update(_assign_nums(numbers))
    if item.get("total") is not None or item.get("price") is not None:
        items.append(item)


def _assign_nums(numbers):
    if len(numbers) >= 3:
        q, p, t = numbers[-3], numbers[-2], numbers[-1]
        if _math_validates(q, p, t):
            return {"qty": q, "price": p, "total": t}
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                if _math_validates(numbers[i], numbers[j], numbers[-1]):
                    return {"qty": numbers[i], "price": numbers[j], "total": numbers[-1]}
        return {"qty": numbers[-3], "price": numbers[-2], "total": numbers[-1]}
    elif len(numbers) == 2:
        a, b = numbers[0], numbers[1]
        if a == int(a) and a >= 1 and a <= 50 and b > 0:
            if _math_validates(a, b / a, b):
                return {"qty": a, "price": b / a, "total": b}
        return {"price": a, "total": b}
    elif len(numbers) == 1:
        return {"total": numbers[0]}
    return {}


# ---------------------------------------------------------------------------
# SMART TOTAL DETECTION (GST cross-validated)
# ---------------------------------------------------------------------------

def _strip_non_monetary(line: str) -> str:
    cleaned = line
    for pat in DATE_PATTERNS:
        cleaned = pat.sub("", cleaned)
    cleaned = TIME_PATTERN.sub("", cleaned)
    cleaned = PHONE_PATTERN.sub("", cleaned)
    cleaned = GSTIN_STRICT.sub("", cleaned)
    cleaned = GSTIN_RELAXED.sub("", cleaned)
    cleaned = re.sub(r"\b\d{6}\b", "", cleaned)
    return cleaned


def _extract_amounts_from_rows(rows: list[list[dict]]) -> list[float]:
    """Extract all clean monetary amounts from layout rows."""
    amounts = []
    for row in rows:
        text = row_to_text(row)
        if _is_meta_line(text):
            continue
        cleaned = _strip_non_monetary(text)
        nums = re.findall(r"(\d+\.\d{1,2}|\d+)", cleaned)
        for n in nums:
            try:
                v = float(n)
                if v > 0:
                    amounts.append(v)
            except ValueError:
                pass
    return amounts


def _kw_amount(rows: list[list[dict]], category: str) -> float | None:
    """Find amount on a row matching a keyword category."""
    for row in rows:
        text = row_to_text(row)
        if match_keyword(text, category):
            cleaned = _strip_non_monetary(text)
            nums = re.findall(r"(\d+\.\d{1,2}|\d+)", cleaned)
            if nums:
                return float(nums[-1])
    return None


def find_totals(rows: list[list[dict]], items: list[dict]) -> dict:
    """
    Smart total detection using GST cross-validation.

    1. Keyword extraction for subtotal, CGST, SGST, total
    2. GST pair finding: find (subtotal, total) where subtotal + GST ≈ total
    3. Cross-validate with item sum
    4. Hybrid filter: remove items where item.total > bill total
    """
    # Keyword-based
    subtotal = _kw_amount(rows, "subtotal")
    total = _kw_amount(rows, "total")

    # GST extraction
    cgst = None
    sgst = None
    for row in rows:
        text = row_to_text(row).lower()
        cleaned = _strip_non_monetary(row_to_text(row))
        nums = re.findall(r"(\d+\.\d{1,2}|\d+)", cleaned)
        if nums:
            val = float(nums[-1])
            if "cgst" in text or "central" in text:
                cgst = val
            elif "sgst" in text or "state" in text:
                sgst = val

    gst = (cgst or 0) + (sgst or 0)

    # All monetary amounts for fallback
    all_amounts = sorted(set(_extract_amounts_from_rows(rows)), reverse=True)

    # GST pair finding: subtotal + GST ≈ total
    if total is None and gst > 0 and all_amounts:
        for t in all_amounts:
            for s in all_amounts:
                if abs(s - t) < 0.01:
                    continue
                if abs((s + gst) - t) < 5:
                    total = t
                    subtotal = s
                    break
            if total is not None:
                break

    # Positional fallback: largest near bottom
    if total is None and all_amounts:
        total = all_amounts[0]

    # Item sum as subtotal ground truth
    item_sum = sum(it.get("total", 0) for it in items if it.get("total"))
    if item_sum > 0:
        if subtotal is None:
            subtotal = item_sum
        elif abs(subtotal - item_sum) > max(item_sum * 0.05, 5.0):
            subtotal = item_sum

    # Subtotal from amounts if missing
    if subtotal is None and total is not None and all_amounts:
        others = [a for a in all_amounts if abs(a - total) > 0.01]
        if gst > 0:
            for c in others:
                if abs(c + gst - total) < 5:
                    subtotal = c
                    break
        if subtotal is None and others:
            subtotal = others[0]

    # Cross-validate: if subtotal + gst ≠ total, try alt total
    if total is not None and subtotal is not None and gst > 0:
        expected = subtotal + gst
        if abs(expected - total) > 5:
            for candidate in all_amounts:
                if abs(candidate - total) < 0.01:
                    continue
                if abs(expected - candidate) < 5:
                    total = candidate
                    break

    return {
        "subtotal": subtotal,
        "cgst": cgst,
        "sgst": sgst,
        "total_amount": total,
    }


# ---------------------------------------------------------------------------
# HYBRID FILTER: remove items exceeding total
# ---------------------------------------------------------------------------

def filter_items(items: list[dict], total: float | None) -> list[dict]:
    """Remove items where item total > bill total (obvious garbage)."""
    if total is None or total <= 0:
        return items
    return [it for it in items if (it.get("total") or 0) <= total * 1.05]


# ---------------------------------------------------------------------------
# Field extractors (language-agnostic)
# ---------------------------------------------------------------------------

def extract_date(rows: list[list[dict]]) -> str | None:
    for row in rows:
        text = row_to_text(row)
        for pat in DATE_PATTERNS:
            m = pat.search(text)
            if m:
                return m.group(1)
    return None


def extract_time(rows: list[list[dict]]) -> str | None:
    for row in rows:
        text = row_to_text(row)
        m = TIME_PATTERN.search(text)
        if m:
            return m.group(1)
    return None


def extract_gstin(rows: list[list[dict]]) -> str | None:
    full = " ".join(row_to_text(r) for r in rows)
    m = GSTIN_STRICT.search(full)
    if m and len(m.group(1)) == 15:
        return m.group(1)
    m = GSTIN_RELAXED.search(full)
    if m and len(m.group(1)) == 15:
        return m.group(1)
    return None


def extract_phone(rows: list[list[dict]]) -> str | None:
    for row in rows:
        text = row_to_text(row)
        if re.search(r"\d+\.\d{2}", text):
            clean = re.sub(r"\d+\.\d+", "", text)
            m = PHONE_PATTERN.search(clean)
        else:
            m = PHONE_PATTERN.search(text)
        if m:
            return m.group(1)
    return None


def extract_invoice(rows: list[list[dict]]) -> str | None:
    for row in rows:
        text = row_to_text(row)
        m = INVOICE_KW_PATTERN.search(text)
        if m:
            return m.group(1).strip()
    for row in rows[:10]:
        text = row_to_text(row)
        m = re.search(r"(?:No|#)[\s.:]*([A-Z0-9/\-]{3,20})", text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if not re.match(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$", candidate):
                return candidate
    return None


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def parse_bill_layout(rows: list[list[dict]]) -> dict:
    """
    Layout-aware bill parser. Uses row structure from layout_engine.

    Pipeline: Layout Rows → Hybrid Parsing → Validation → Audit Output
    """
    # Extract items
    items = extract_items_from_rows(rows)

    # Extract amounts with GST cross-validation
    amounts = find_totals(rows, items)

    # Hybrid filter: remove items exceeding total
    items = filter_items(items, amounts["total_amount"])

    return {
        "vendor_name": detect_vendor(rows),
        "invoice_number": extract_invoice(rows),
        "date": extract_date(rows),
        "time": extract_time(rows),
        "gstin": extract_gstin(rows),
        "phone_number": extract_phone(rows),
        "items": items,
        "subtotal": amounts["subtotal"],
        "cgst": amounts["cgst"],
        "sgst": amounts["sgst"],
        "total_amount": amounts["total_amount"],
    }


def parse_bill_lines(lines: list[str]) -> dict:
    """
    Line-based fallback parser. Used when layout data is unavailable.
    """
    from layout_engine import group_rows as _unused

    items = extract_items_from_lines(lines)

    # Build pseudo-rows for amount extraction
    pseudo_rows = [[{"text": ln, "x": 0, "y": i * 20, "w": 100, "h": 18, "conf": 0.5}]
                   for i, ln in enumerate(lines)]

    amounts = find_totals(pseudo_rows, items)
    items = filter_items(items, amounts["total_amount"])

    # Field extraction from flat lines
    full = " ".join(lines)

    vendor = None
    skip_kw = {"tax", "invoice", "bill", "receipt", "gstin", "gst", "date",
               "phone", "mobile", "tel", "email"}
    for line in lines[:5]:
        s = line.strip()
        if not s or len(s) < 2:
            continue
        if sum(1 for c in s if c.isalpha()) < 2:
            continue
        if any(kw in s.lower() for kw in skip_kw):
            continue
        if _is_meta_line(s) or GSTIN_STRICT.search(s):
            continue
        vendor = s
        break

    date = None
    for line in lines:
        for pat in DATE_PATTERNS:
            m = pat.search(line)
            if m:
                date = m.group(1)
                break
        if date:
            break

    time = None
    for line in lines:
        m = TIME_PATTERN.search(line)
        if m:
            time = m.group(1)
            break

    gstin = None
    m = GSTIN_STRICT.search(full)
    if m and len(m.group(1)) == 15:
        gstin = m.group(1)

    phone = None
    for line in lines:
        m = PHONE_PATTERN.search(line)
        if m:
            phone = m.group(1)
            break

    invoice = None
    m = INVOICE_KW_PATTERN.search(full)
    if m:
        invoice = m.group(1).strip()

    return {
        "vendor_name": vendor,
        "invoice_number": invoice,
        "date": date,
        "time": time,
        "gstin": gstin,
        "phone_number": phone,
        "items": items,
        "subtotal": amounts["subtotal"],
        "cgst": amounts["cgst"],
        "sgst": amounts["sgst"],
        "total_amount": amounts["total_amount"],
    }
