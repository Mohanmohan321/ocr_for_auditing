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

## Pipeline

```
Image/PDF
    |
    v
Preprocess (OpenCV: upscale, denoise, CLAHE, Otsu threshold)
    |
    v
PaddleOCR (English model + Tamil model, merged by IoU dedup)
    |
    v
Layout Clustering (Y-coordinate row grouping)
    |
    v
Text Normalization (OCR noise fix, language detection)
    |
    v
Parsing (Mistral AI primary -> regex/layout fallback)
    |
    v
Strict Validation (qty*price=total, qty<=50, GST math)
    |
    v
Vendor Intelligence (fuzzy match, auto-learn, fraud detect)
    |
    v
Audit Report (high/medium risk, confidence 0-100)
    |
    v
Output (JSON + CSV + editable verification)
```

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

## License

MIT
