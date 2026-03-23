"""
Audit Engine: Validates extracted bill data, flags risks, computes confidence.

Audit status logic (from spec):
  - If ANY high_risk  → REJECTED
  - If only medium_risk → NEEDS REVIEW
  - If no risks → APPROVED

Confidence scoring (from spec):
  Start at 100, deductions:
    missing vendor    : -15
    missing invoice   : -15
    missing gstin     : -20
    missing items     : -20
    missing total     : -15
    ocr noise detected: -10
  Clamp to [0, 100].
"""
import re


# ---------------------------------------------------------------------------
# GSTIN format validation
# ---------------------------------------------------------------------------

GSTIN_FORMAT = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Zz][A-Z0-9]$")


def validate_gstin(gstin: str | None) -> tuple[bool, str]:
    """Validate GSTIN format. Returns (is_valid, message)."""
    if not gstin:
        return False, "GSTIN is missing"

    if len(gstin) != 15:
        return False, f"GSTIN length is {len(gstin)}, expected 15"

    try:
        state = int(gstin[:2])
        if state < 1 or state > 37:
            return False, f"Invalid state code: {gstin[:2]}"
    except ValueError:
        return False, f"State code not numeric: {gstin[:2]}"

    if not GSTIN_FORMAT.match(gstin):
        return False, f"GSTIN format invalid: {gstin}"

    return True, "Valid"


# ---------------------------------------------------------------------------
# GST math validation
# ---------------------------------------------------------------------------

def validate_gst_math(subtotal: float | None,
                      cgst: float | None,
                      sgst: float | None,
                      total: float | None) -> list[dict]:
    """
    Check:
    - CGST + SGST = total GST
    - Subtotal + GST == total_amount
    Returns list of issues found.
    """
    issues = []
    tolerance = 1.5  # Rs.1.50 rounding tolerance

    # CGST should equal SGST for intra-state
    if cgst is not None and sgst is not None:
        if abs(cgst - sgst) > tolerance:
            issues.append({
                "level": "high",
                "rule": "GST Split Mismatch",
                "detail": f"CGST ({cgst}) != SGST ({sgst}) — should be equal for intra-state",
            })

    # Subtotal + CGST + SGST should equal total
    if subtotal is not None and total is not None:
        gst_sum = (cgst or 0) + (sgst or 0)
        expected = subtotal + gst_sum
        if abs(expected - total) > tolerance:
            issues.append({
                "level": "high",
                "rule": "Total Amount Mismatch",
                "detail": (
                    f"Subtotal ({subtotal}) + GST ({gst_sum}) = {expected:.2f}, "
                    f"but total is {total}"
                ),
            })

    return issues


# ---------------------------------------------------------------------------
# Main audit runner
# ---------------------------------------------------------------------------

def run_audit(structured_data: dict, ocr_noise_ratio: float) -> dict:
    """
    Run all audit rules.

    Args:
        structured_data: Output from parser.parse_bill()
        ocr_noise_ratio: 0.0 (clean) to 1.0 (garbage) from ocr_utils

    Returns:
        {
            "high_risk": [...],
            "medium_risk": [...],
            "audit_status": "APPROVED" | "NEEDS REVIEW" | "REJECTED",
            "confidence_score": 0-100
        }
    """
    high_risk = []
    medium_risk = []

    # ── HIGH RISK RULES ───────────────────────────────────────────────────

    # 1. Missing vendor_name
    if not structured_data.get("vendor_name"):
        high_risk.append({
            "rule": "Missing Vendor Name",
            "detail": "No vendor/shop name could be identified in the bill",
        })

    # 2. Missing invoice_number
    if not structured_data.get("invoice_number"):
        high_risk.append({
            "rule": "Missing Invoice Number",
            "detail": "No invoice/bill number found",
        })

    # 3. Missing or invalid GSTIN
    gstin = structured_data.get("gstin")
    gstin_valid, gstin_msg = validate_gstin(gstin)
    if not gstin_valid:
        high_risk.append({
            "rule": "Invalid or Missing GSTIN",
            "detail": gstin_msg,
        })

    # 4. No items extracted
    items = structured_data.get("items", [])
    if not items:
        high_risk.append({
            "rule": "No Items Extracted",
            "detail": "Could not extract any line items from the bill",
        })

    # 5. Missing total_amount
    if structured_data.get("total_amount") is None:
        high_risk.append({
            "rule": "Missing Total Amount",
            "detail": "No total/grand total amount found",
        })

    # 6. GST math mismatch
    gst_issues = validate_gst_math(
        structured_data.get("subtotal"),
        structured_data.get("cgst"),
        structured_data.get("sgst"),
        structured_data.get("total_amount"),
    )
    for issue in gst_issues:
        if issue["level"] == "high":
            high_risk.append({"rule": issue["rule"], "detail": issue["detail"]})

    # ── MEDIUM RISK RULES ─────────────────────────────────────────────────

    # 7. OCR noise detected
    if ocr_noise_ratio > 0.05:
        medium_risk.append({
            "rule": "OCR Noise Detected",
            "detail": f"Suspicious character ratio: {ocr_noise_ratio:.1%}",
        })

    # 8. Missing HSN/SAC codes
    has_hsn = False
    for item in items:
        name = str(item.get("name") or "")
        if re.search(r"\b\d{4}\b|\b\d{8}\b", name):
            has_hsn = True
            break
    if items and not has_hsn:
        medium_risk.append({
            "rule": "Missing HSN/SAC Codes",
            "detail": "No HSN or SAC codes found in line items",
        })

    # 9. Unusual character patterns
    # (items with no readable names)
    if items:
        unreadable = [it for it in items if not it.get("name")]
        if unreadable:
            medium_risk.append({
                "rule": "Unreadable Item Names",
                "detail": f"{len(unreadable)} item(s) have no readable name — possible OCR noise",
            })

    # 10. Low extraction confidence (missing date, no GST breakup)
    if not structured_data.get("date"):
        medium_risk.append({
            "rule": "Missing Date",
            "detail": "No date found on the bill",
        })

    if gstin and structured_data.get("cgst") is None and structured_data.get("sgst") is None:
        medium_risk.append({
            "rule": "Missing GST Breakup",
            "detail": "GSTIN present but no CGST/SGST amounts found",
        })

    # ── CONFIDENCE SCORE ──────────────────────────────────────────────────
    score = _compute_confidence(structured_data, ocr_noise_ratio)

    # ── AUDIT STATUS ──────────────────────────────────────────────────────
    # Spec: any high_risk → REJECTED, only medium → NEEDS REVIEW, none → APPROVED
    if high_risk:
        status = "REJECTED"
    elif medium_risk:
        status = "NEEDS REVIEW"
    else:
        status = "APPROVED"

    return {
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "audit_status": status,
        "confidence_score": score,
    }


# ---------------------------------------------------------------------------
# Confidence scoring — exact spec deductions
# ---------------------------------------------------------------------------

def _compute_confidence(data: dict, ocr_noise_ratio: float) -> int:
    """
    Start at 100, apply spec deductions:
      missing vendor    : -15
      missing invoice   : -15
      missing gstin     : -20
      missing items     : -20
      missing total     : -15
      ocr noise detected: -10
    Clamp to [0, 100].
    """
    score = 100

    if not data.get("vendor_name"):
        score -= 15

    if not data.get("invoice_number"):
        score -= 15

    if not data.get("gstin"):
        score -= 20

    items = data.get("items", [])
    if not items:
        score -= 20

    if data.get("total_amount") is None:
        score -= 15

    if ocr_noise_ratio > 0.05:
        score -= 10

    return max(0, min(100, score))
