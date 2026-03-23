"""
Vendor Intelligence Engine: Self-learning vendor recognition system.

Features:
  - JSON-based vendor database (upgradeable to PostgreSQL)
  - Tamil → English transliteration for cross-language matching
  - Multi-signal scoring: GSTIN (5pts) + Phone (3pts) + Name fuzzy (2pts)
  - Auto-learning: new vendors added automatically
  - Self-improvement: aliases grow with each invoice
  - Fraud detection: same name + different GSTIN = flag
  - Confidence scoring per vendor
"""
import json
import os
import re
import logging
from datetime import date
from difflib import SequenceMatcher
from typing import Optional

log = logging.getLogger(__name__)

# Default DB path — next to this module
_DB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(_DB_DIR, "vendor_db.json")


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalize for fuzzy comparison: lowercase, strip noise."""
    if not text:
        return ""
    text = text.lower().strip()
    # Remove common suffixes/prefixes that don't help matching
    text = re.sub(r"\b(pvt|ltd|private|limited|co|inc)\b\.?", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Tamil → English transliteration
# ---------------------------------------------------------------------------

def _transliterate_tamil(text: str) -> str:
    """Convert Tamil script to approximate English letters for matching."""
    if not any("\u0B80" <= c <= "\u0BFF" for c in text):
        return text  # No Tamil — return as-is

    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate

        # Split into Tamil and non-Tamil segments, transliterate only Tamil
        result_parts = []
        current = []
        is_tamil = False

        for ch in text:
            ch_is_tamil = "\u0B80" <= ch <= "\u0BFF"
            if ch_is_tamil != is_tamil and current:
                segment = "".join(current)
                if is_tamil:
                    segment = transliterate(segment, sanscript.TAMIL, sanscript.ITRANS)
                result_parts.append(segment)
                current = []
            is_tamil = ch_is_tamil
            current.append(ch)

        if current:
            segment = "".join(current)
            if is_tamil:
                segment = transliterate(segment, sanscript.TAMIL, sanscript.ITRANS)
            result_parts.append(segment)

        return "".join(result_parts)

    except ImportError:
        log.debug("indic_transliteration not installed — skipping transliteration")
        return text
    except Exception as e:
        log.debug("Transliteration failed: %s", e)
        return text


def process_name(name: str) -> str:
    """Full name processing: transliterate + normalize."""
    if not name:
        return ""
    name = _transliterate_tamil(name)
    name = _normalize_text(name)
    return name


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    """String similarity 0.0–1.0 using SequenceMatcher."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Multi-signal vendor scoring
# ---------------------------------------------------------------------------

def _compute_score(input_name: str, phone: str | None, gstin: str | None,
                   vendor: dict) -> float:
    """
    Multi-signal match score:
      GSTIN match:  +5 (strongest signal — unique identifier)
      Phone match:  +3
      Name fuzzy:   +2 * similarity (per alias, take best)
    """
    score = 0.0

    # GSTIN match (strongest — unique per business)
    if gstin and gstin in vendor.get("gstins", []):
        score += 5.0

    # Phone match
    if phone and phone in vendor.get("phone_numbers", []):
        score += 3.0

    # Name similarity (check all aliases)
    processed_input = process_name(input_name)
    best_name_score = 0.0

    for alias in vendor.get("aliases", []):
        processed_alias = process_name(alias)
        sim = _similarity(processed_input, processed_alias)
        best_name_score = max(best_name_score, sim)

    score += best_name_score * 2.0

    return score


# ---------------------------------------------------------------------------
# Vendor DB operations
# ---------------------------------------------------------------------------

def load_db(path: str = DEFAULT_DB_PATH) -> list[dict]:
    """Load vendor database from JSON file."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.warning("Failed to load vendor DB: %s", e)
        return []


def save_db(db: list[dict], path: str = DEFAULT_DB_PATH):
    """Save vendor database to JSON file."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        log.info("Vendor DB saved: %d vendors", len(db))
    except IOError as e:
        log.error("Failed to save vendor DB: %s", e)


# ---------------------------------------------------------------------------
# Find vendor (match against DB)
# ---------------------------------------------------------------------------

def find_vendor(input_name: str, phone: str | None, gstin: str | None,
                db: list[dict]) -> tuple[Optional[dict], float]:
    """
    Find best matching vendor from database.

    Returns:
        (vendor_dict, score) — vendor_dict is None if no match above threshold.
        Threshold: score > 4.0 for a confident match.
    """
    if not input_name and not phone and not gstin:
        return None, 0.0

    best_vendor = None
    best_score = 0.0

    for vendor in db:
        score = _compute_score(input_name or "", phone, gstin, vendor)
        if score > best_score:
            best_score = score
            best_vendor = vendor

    if best_score >= 4.0:
        return best_vendor, best_score

    return None, best_score


# ---------------------------------------------------------------------------
# Auto-learning: add new vendor
# ---------------------------------------------------------------------------

def _is_valid_vendor_name(name: str) -> bool:
    """
    Learning gate: reject invalid vendor names before storing.
    Rejects numeric-heavy strings, too-short names, garbage.
    """
    if not name or len(name.strip()) < 3:
        return False

    stripped = name.strip()

    # Count alpha vs digit chars
    alpha = sum(1 for c in stripped if c.isalpha() or ord(c) > 0x0900)
    digits = sum(1 for c in stripped if c.isdigit())

    # Reject if more digits than letters (numeric-heavy)
    if digits > alpha:
        return False

    # Reject if too few letters
    if alpha < 2:
        return False

    # Reject pure numbers
    if re.match(r"^[\d\s.,/\-:]+$", stripped):
        return False

    # Reject GSTIN-like strings
    if re.match(r"^\d{2}[A-Z0-9]{13}$", stripped):
        return False

    # Reject phone-like strings
    if re.match(r"^[\d\s+\-()]{8,}$", stripped):
        return False

    return True


def learn_vendor(input_name: str, phone: str | None, gstin: str | None,
                 db: list[dict]) -> Optional[dict]:
    """
    Auto-learn a new vendor. Called when no match found in DB.
    Returns the new vendor entry, or None if name is invalid.

    Learning gate: rejects numeric-heavy strings, garbage names.
    """
    if not _is_valid_vendor_name(input_name):
        log.info("Vendor learning gate rejected: '%s'", input_name)
        return None

    vendor_id = f"V{len(db) + 1:03d}"

    new_vendor = {
        "vendor_id": vendor_id,
        "canonical_name": input_name,
        "aliases": [input_name],
        "phone_numbers": [phone] if phone else [],
        "gstins": [gstin] if gstin else [],
        "last_seen": str(date.today()),
        "invoice_count": 1,
        "confidence": 0.6,
    }

    db.append(new_vendor)
    log.info("Learned new vendor: %s (ID: %s)", input_name, vendor_id)
    return new_vendor


# ---------------------------------------------------------------------------
# Self-improvement: update existing vendor
# ---------------------------------------------------------------------------

def update_vendor(vendor: dict, new_name: str | None,
                  phone: str | None, gstin: str | None):
    """
    Improve vendor data with new signals from this invoice.
    Adds aliases, phone numbers, GSTINs not already known.
    Increases confidence.
    """
    # Add new alias if not already known
    if new_name:
        processed = process_name(new_name)
        existing_processed = [process_name(a) for a in vendor.get("aliases", [])]
        if processed and processed not in existing_processed:
            vendor.setdefault("aliases", []).append(new_name)
            log.info("Vendor %s: new alias '%s'", vendor["vendor_id"], new_name)

    # Add new phone
    if phone and phone not in vendor.get("phone_numbers", []):
        vendor.setdefault("phone_numbers", []).append(phone)

    # Add new GSTIN (but flag fraud if different)
    if gstin and gstin not in vendor.get("gstins", []):
        vendor.setdefault("gstins", []).append(gstin)

    # Update metadata
    vendor["last_seen"] = str(date.today())
    vendor["invoice_count"] = vendor.get("invoice_count", 0) + 1
    vendor["confidence"] = min(vendor.get("confidence", 0.6) + 0.05, 1.0)


# ---------------------------------------------------------------------------
# Fraud detection
# ---------------------------------------------------------------------------

def detect_fraud(vendor: dict, gstin: str | None) -> list[dict]:
    """
    Check for fraud signals:
    - Same vendor name but different GSTIN
    - Multiple GSTINs for one vendor
    """
    flags = []

    vendor_gstins = vendor.get("gstins", [])

    # Multiple GSTINs for one vendor — suspicious
    if gstin and vendor_gstins and gstin not in vendor_gstins:
        flags.append({
            "type": "gstin_mismatch",
            "severity": "high",
            "detail": (
                f"Vendor '{vendor['canonical_name']}' has GSTIN {vendor_gstins[0]} "
                f"on record, but this invoice shows {gstin}"
            ),
        })

    if len(vendor_gstins) > 1:
        flags.append({
            "type": "multiple_gstins",
            "severity": "medium",
            "detail": (
                f"Vendor '{vendor['canonical_name']}' has {len(vendor_gstins)} "
                f"different GSTINs: {', '.join(vendor_gstins)}"
            ),
        })

    return flags


# ---------------------------------------------------------------------------
# Main pipeline function
# ---------------------------------------------------------------------------

def resolve_vendor(raw_name: str | None, phone: str | None, gstin: str | None,
                   db_path: str = DEFAULT_DB_PATH) -> dict:
    """
    Full vendor resolution pipeline:
    1. Load DB
    2. Match against known vendors (multi-signal scoring)
    3. If matched: update vendor with new signals, check fraud
    4. If not matched: auto-learn new vendor
    5. Save DB
    6. Return resolution result

    Returns:
        {
            "canonical_name": "...",
            "match_type": "matched" | "learned",
            "match_score": float,
            "vendor_id": "V001",
            "confidence": float,
            "fraud_flags": [],
            "invoice_count": int,
        }
    """
    db = load_db(db_path)

    # Try to match
    matched_vendor, score = find_vendor(raw_name, phone, gstin, db)

    if matched_vendor:
        # Match found — update and check fraud
        update_vendor(matched_vendor, raw_name, phone, gstin)
        fraud_flags = detect_fraud(matched_vendor, gstin)
        save_db(db, db_path)

        return {
            "canonical_name": matched_vendor["canonical_name"],
            "match_type": "matched",
            "match_score": round(score, 2),
            "vendor_id": matched_vendor["vendor_id"],
            "confidence": matched_vendor["confidence"],
            "fraud_flags": fraud_flags,
            "invoice_count": matched_vendor.get("invoice_count", 1),
            "aliases": matched_vendor.get("aliases", []),
        }
    else:
        # No match — try to learn new vendor (learning gate filters garbage)
        if raw_name:
            new_vendor = learn_vendor(raw_name, phone, gstin, db)
            if new_vendor:
                save_db(db, db_path)
                return {
                    "canonical_name": raw_name,
                    "match_type": "learned",
                    "match_score": round(score, 2),
                    "vendor_id": new_vendor["vendor_id"],
                    "confidence": 0.6,
                    "fraud_flags": [],
                    "invoice_count": 1,
                    "aliases": [raw_name],
                }
            else:
                # Learning gate rejected this name
                return {
                    "canonical_name": raw_name,
                    "match_type": "rejected",
                    "match_score": 0.0,
                    "vendor_id": None,
                    "confidence": 0.0,
                    "fraud_flags": [],
                    "invoice_count": 0,
                    "aliases": [],
                }

        return {
            "canonical_name": None,
            "match_type": "unknown",
            "match_score": 0.0,
            "vendor_id": None,
            "confidence": 0.0,
            "fraud_flags": [],
            "invoice_count": 0,
            "aliases": [],
        }
