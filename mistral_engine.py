"""
Mistral AI Engine: Send raw OCR text to Mistral, get structured bill JSON back.

Mistral understands noisy OCR, mixed Tamil+English, and returns clean parsed output.
This replaces regex-based parsing as the primary extraction method.
"""
import json
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"

SYSTEM_PROMPT = """You are a bill/invoice data extraction AI. You receive raw OCR text from scanned bills (which may be noisy, mixed Tamil+English, or have broken characters).

Your job: extract structured data and return ONLY valid JSON — no markdown, no explanation, no code fences.

Return this exact JSON structure:
{
  "vendor_name": "string or null",
  "invoice_number": "string or null",
  "date": "string or null",
  "time": "string or null",
  "gstin": "string or null",
  "phone_number": "string or null",
  "items": [
    {"name": "string", "qty": number, "price": number, "total": number}
  ],
  "subtotal": number or null,
  "cgst": number or null,
  "sgst": number or null,
  "total_amount": number or null
}

Rules:
- Return null for fields you cannot confidently extract
- For items, only include items where qty * price ≈ total (math must validate)
- Fix obvious OCR noise (6T600T = GST, O = 0 in numbers, etc.)
- GSTIN must be exactly 15 characters matching format: 2-digit state + PAN + entity + Z + check
- Phone numbers are 10 digits starting with 6-9
- Dates should be in DD/MM/YYYY format
- Do NOT hallucinate — if unsure, return null
- Tamil text: extract the meaning, don't transliterate
- Return ONLY the JSON object, nothing else"""


def extract_with_mistral(raw_ocr_text: str, api_key: str) -> Optional[dict]:
    """
    Send raw OCR text to Mistral API and get structured bill data back.

    Args:
        raw_ocr_text: The raw OCR output (may be noisy, mixed language)
        api_key: Mistral API key

    Returns:
        Parsed bill dict or None if failed
    """
    import requests

    if not api_key:
        log.warning("No Mistral API key provided")
        return None

    if not raw_ocr_text or len(raw_ocr_text.strip()) < 10:
        log.warning("OCR text too short for Mistral extraction")
        return None

    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract structured data from this bill OCR text:\n\n{raw_ocr_text}"},
        ],
        "temperature": 0.0,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        log.info("Sending OCR text to Mistral (%d chars)...", len(raw_ocr_text))
        response = requests.post(
            MISTRAL_API_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            log.error("Mistral API error %d: %s", response.status_code, response.text[:200])
            return None

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Parse JSON from response
        result = _parse_mistral_response(content)
        if result:
            log.info("Mistral extraction successful: %d items found",
                     len(result.get("items", [])))
        return result

    except requests.exceptions.Timeout:
        log.error("Mistral API timeout")
        return None
    except requests.exceptions.ConnectionError:
        log.error("Mistral API connection failed")
        return None
    except Exception as e:
        log.error("Mistral extraction failed: %s", e)
        return None


def _parse_mistral_response(content: str) -> Optional[dict]:
    """Parse and validate Mistral's JSON response."""
    try:
        # Try direct JSON parse
        result = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code fences
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(1))
            except json.JSONDecodeError:
                log.error("Failed to parse Mistral JSON response")
                return None
        else:
            log.error("No valid JSON in Mistral response: %s", content[:200])
            return None

    # Validate and normalize the structure
    return _normalize_result(result)


def _normalize_result(raw: dict) -> dict:
    """Ensure the result matches our expected schema."""
    result = {
        "vendor_name": raw.get("vendor_name"),
        "invoice_number": raw.get("invoice_number"),
        "date": raw.get("date"),
        "time": raw.get("time"),
        "gstin": raw.get("gstin"),
        "phone_number": raw.get("phone_number"),
        "items": [],
        "subtotal": _to_float(raw.get("subtotal")),
        "cgst": _to_float(raw.get("cgst")),
        "sgst": _to_float(raw.get("sgst")),
        "total_amount": _to_float(raw.get("total_amount")),
    }

    # Normalize string fields — convert "null" strings to None
    for field in ["vendor_name", "invoice_number", "date", "time", "gstin", "phone_number"]:
        val = result[field]
        if isinstance(val, str) and val.lower() in ("null", "none", "n/a", ""):
            result[field] = None

    # Validate GSTIN format
    gstin = result["gstin"]
    if gstin and (len(gstin) != 15 or not re.match(r"\d{2}[A-Z0-9]{10}[A-Z0-9]Z[A-Z0-9]", gstin)):
        result["gstin"] = None

    # Validate and filter items
    raw_items = raw.get("items", [])
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized = {
                "name": item.get("name"),
                "qty": _to_float(item.get("qty")),
                "price": _to_float(item.get("price")),
                "total": _to_float(item.get("total")),
            }
            # Strict validation: must have at least total, and math must check out
            if normalized["total"] is None and normalized["price"] is None:
                continue
            if (normalized["qty"] is not None and normalized["price"] is not None
                    and normalized["total"] is not None):
                expected = normalized["qty"] * normalized["price"]
                tolerance = max(normalized["total"] * 0.02, 5.0)
                if abs(expected - normalized["total"]) > tolerance:
                    continue  # Math doesn't validate — reject
            if normalized["qty"] is not None and normalized["qty"] > 50:
                continue  # Unrealistic qty — reject
            result["items"].append(normalized)

    return result


def _to_float(val) -> Optional[float]:
    """Safely convert to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace(",", "").strip()
        try:
            return float(val)
        except ValueError:
            return None
    return None
