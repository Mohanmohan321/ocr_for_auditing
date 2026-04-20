# OCR Bill Auditor

AI-powered bill/invoice extraction and auditing system with multilingual support (Tamil + English).

## Features

- **PaddleOCR** dual-language OCR (English + Tamil) with bounding box layout awareness
- **Mistral AI** for intelligent parsing (with regex fallback for offline use)
- **Strict validation** — items must pass `qty * price = total` math check
- **GST cross-validation** — verifies `subtotal + CGST + SGST = total`
- **Vendor intelligence** — self-learning vendor database with fuzzy matching, Tamil transliteration, and fraud detection
- **Multi-file upload** — process batches of images and PDFs with progress tracking
- **5-tab UI** — Processed Output, Verification, Comparison, Raw OCR, Export (CSV + JSON)

## Project Structure

```
ocr/
  app.py                 # Streamlit UI (main application)
  config.py              # Language maps, constants
  preprocessor.py        # Image preprocessing (OpenCV)
  paddle_ocr_engine.py   # PaddleOCR dual-language engine
  layout_engine.py       # Y-coordinate row clustering + keyword dicts
  ocr_utils.py           # Text normalization, language detection, translation
  parser.py              # Layout-aware hybrid parser (strict validation)
  mistral_engine.py      # Mistral AI extraction layer
  audit_engine.py        # Risk rules, GSTIN validation, confidence scoring
  vendor_engine.py       # Self-learning vendor matching + fraud detection
  requirements.txt       # Python dependencies
  .env                   # API keys (not committed)
```

## Setup

```bash
# Clone
git clone https://github.com/Mohanmohan321/ocr_for_auditing.git
cd ocr_for_auditing

# Install dependencies
pip install -r requirements.txt

# Set API keys (optional — works offline without Mistral)
echo "MISTRAL_API_KEY=your_key_here" > .env

# For PDF support on Windows, install Poppler:
# Download from https://github.com/oschwartz10612/poppler-windows/releases
# Extract to C:\Users\<you>\poppler\Library\bin

# Run
streamlit run app.py
```

## Project Flow

### High-Level Pipeline

```
Image/PDF Upload (Streamlit UI)
        |
        v
  +------------------+
  |  PDF Conversion   |  pdf2image + Poppler -> per-page PNG images
  +------------------+
        |
        v
  +------------------+
  |  Preprocessing    |  OpenCV: upscale small images, denoise,
  |  (preprocessor.py)|  CLAHE contrast enhancement, Otsu threshold
  +------------------+  Returns: original_rgb + processed_rgb + PIL image
        |
        v
  +------------------+
  |  PaddleOCR        |  Dual/multi-language OCR engine
  | (paddle_ocr_      |  1. Quick English-only scan for language detection
  |  engine.py)       |  2. Full OCR with detected language models
  +------------------+  3. IoU-based dedup merges overlapping bboxes
        |                Returns: [{text, x, y, w, h, conf}, ...]
        v
  +------------------+
  |  Layout Engine    |  Y-coordinate row clustering:
  | (layout_engine.py)|  - Groups text fragments into rows by Y-proximity
  +------------------+  - Sorts cells left-to-right within each row
        |                - Bilingual keyword dicts (8 languages)
        v
  +------------------+
  |  Text Normalize   |  1. Unicode NFC normalization (Tamil combining chars)
  |  (ocr_utils.py)   |  2. Word-level OCR noise fix (6T600T -> GSTIN)
  +------------------+  3. Char-level fix in numbers (O->0, l->1)
        |                4. Language detection (Unicode script ranges)
        v                5. Auto-translate non-English -> English
  +------------------+
  |  Parsing          |  PRIMARY: Mistral AI (sends raw OCR text, gets JSON)
  |  (parser.py +     |  FALLBACK: Layout-aware regex parser
  |   mistral_        |    - Row-based item extraction (qty*price=total)
  |   engine.py)      |    - Smart total detection with GST cross-validation
  +------------------+    - Hybrid filter: remove items > bill total
        |                MERGE: Mistral + regex results fill each other's gaps
        v
  +------------------+
  |  Vendor Engine    |  1. Load vendor_db.json
  | (vendor_engine.py)|  2. Multi-signal scoring: GSTIN(5) + Phone(3) + Name(2)
  +------------------+  3. Tamil transliteration for cross-language matching
        |                4. Auto-learn new vendors (with learning gate)
        v                5. Fraud detection (same name + different GSTIN)
  +------------------+
  |  Audit Engine     |  HIGH RISK: missing vendor/invoice/GSTIN/items/total,
  | (audit_engine.py) |            GST math mismatch, vendor fraud
  +------------------+  MEDIUM RISK: OCR noise, missing HSN, no date,
        |                            unreadable names, missing GST breakup
        v                CONFIDENCE: starts at 100, deducts per missing field
  +------------------+   STATUS: APPROVED | NEEDS REVIEW | REJECTED
  |  Streamlit UI     |
  |  (app.py)         |  5-Tab Output:
  +------------------+    Tab 1: Processed Output (structured data + audit)
                          Tab 2: Verification (side-by-side image vs JSON, editable)
                          Tab 3: Comparison (all bills in color-coded table)
                          Tab 4: Raw OCR (original language, no translation)
                          Tab 5: Export (CSV summary + CSV items + full JSON)
```

### Detailed Module Flow

```
app.py  process_single_image()
  |
  |-- preprocessor.preprocess_image(path)
  |     -> cv2.imread -> upscale if <1000px -> grayscale -> denoise
  |     -> CLAHE -> Otsu threshold -> return (original, processed, PIL)
  |
  |-- paddle_ocr_engine.run_paddle_ocr(original, ["English"])     # quick scan
  |     -> detect_languages(quick_text)                           # auto-detect
  |     -> run_paddle_ocr(original, detected_languages)           # full scan
  |     -> if <5 results: retry with processed image
  |     -> _merge_multilingual() removes IoU>0.5 duplicates
  |
  |-- layout_engine.group_rows(ocr_data)
  |     -> auto-threshold from median text height
  |     -> cluster fragments by Y-proximity into rows
  |     -> rows_to_lines() for flat text
  |
  |-- ocr_utils.normalize_ocr_text(flat_lines)
  |     -> NFC normalize -> fix word noise -> fix char noise in numbers
  |-- ocr_utils.detect_languages(text)
  |     -> check Unicode ranges for 12 Indic scripts + English
  |-- ocr_utils.translate_to_english(lines)           # if non-English detected
  |     -> deep-translator GoogleTranslator(source='auto', target='en')
  |
  |-- mistral_engine.extract_with_mistral(text, key)  # if API key set
  |     -> POST to Mistral API with structured prompt
  |     -> parse JSON response -> normalize -> validate items
  |-- parser.parse_bill_layout(rows)                  # regex/layout fallback
  |     -> detect_vendor() from top 5 rows (scored by script + keywords + position)
  |     -> extract_items_from_rows() with math validation (qty*price=total)
  |     -> find_totals() with GST cross-validation
  |     -> filter_items() removes items > bill total
  |-- MERGE: fill missing fields from regex into Mistral result (or vice versa)
  |
  |-- vendor_engine.resolve_vendor(name, phone, gstin)
  |     -> load_db() -> find_vendor() multi-signal scoring
  |     -> if matched: update_vendor() + detect_fraud()
  |     -> if new: learn_vendor() with validation gate
  |     -> save_db()
  |
  |-- audit_engine.run_audit(structured, noise_ratio)
  |     -> validate_gstin() format check
  |     -> validate_gst_math() subtotal + GST = total
  |     -> confidence scoring (100 - deductions)
  |     -> append vendor fraud flags
  |
  `-- return full result dict -> Streamlit renders in 5 tabs
```

### Validation Rules

| Rule | Type | Logic |
|------|------|-------|
| Item math check | Strict | `qty * price = total` (within 2% or Rs.5) |
| Qty sanity | Strict | `qty <= 50` (reject unrealistic quantities) |
| GST split check | High Risk | `CGST == SGST` (intra-state requirement) |
| GST total check | High Risk | `subtotal + CGST + SGST = total` (within Rs.1.50) |
| GSTIN format | High Risk | 15 chars: `2-digit state + PAN + entity + Z + check` |
| Hybrid filter | Strict | Remove items where `item.total > bill.total` |

### Confidence Scoring

| Missing Field | Deduction |
|---------------|-----------|
| Vendor name | -15 |
| Invoice number | -15 |
| GSTIN | -20 |
| Line items | -20 |
| Total amount | -15 |
| OCR noise >5% | -10 |

## Output Format

```json
{
  "structured_data": {
    "vendor_name": "Sri Murugan Store",
    "invoice_number": "INV-4521",
    "date": "15/03/2025",
    "gstin": "33AABCS1234Z1Z5",
    "phone_number": "9876543210",
    "items": [
      {"name": "Chicken Biriyani", "qty": 2, "price": 250.0, "total": 500.0}
    ],
    "subtotal": 755.0,
    "cgst": 18.88,
    "sgst": 18.88,
    "total_amount": 792.76
  },
  "audit_report": {
    "high_risk": [],
    "medium_risk": [],
    "audit_status": "APPROVED"
  },
  "language_detected": ["Tamil", "English"],
  "confidence_score": 85
}
```

## UI Tabs

| Tab | Purpose |
|-----|---------|
| Processed Output | Structured extraction + audit + vendor info per bill |
| Verification | Side-by-side image vs JSON with editable fields |
| Comparison | All bills in one color-coded table with summary stats |
| Raw OCR | Untranslated OCR output in original language (Tamil/English) |
| Export | Download CSV (summary + items) and full JSON report |

## Supported Languages

English, Tamil, Hindi, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Odia, Urdu, Assamese, Nepali


