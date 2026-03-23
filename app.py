"""
Bill OCR Auditor — Full Application

Tabs:
  1. Processed Output  — structured extraction + audit + vendor intelligence
  2. Verification      — side-by-side image vs JSON, editable fields
  3. Comparison        — all bills in a table, compare across files
  4. Raw OCR           — untranslated OCR output as-is
  5. Export            — CSV / JSON download for all processed bills

Features:
  - Multi-file upload (images + PDFs)
  - Processing queue with progress
  - PaddleOCR (Tamil + English)
  - Mistral AI + regex fallback
  - Vendor intelligence (self-learning)
  - Strict validation + GST cross-check
"""
import streamlit as st
import os
import json
import tempfile
import platform
import logging
import pandas as pd

from config import SUPPORTED_LANGUAGES
from preprocessor import preprocess_image
from paddle_ocr_engine import run_paddle_ocr, avg_confidence as paddle_avg_conf
from layout_engine import group_rows, rows_to_lines
from ocr_utils import (
    normalize_ocr_text, detect_languages, translate_to_english,
    estimate_ocr_noise, estimate_ocr_quality,
)
from parser import parse_bill_layout, parse_bill_lines
from mistral_engine import extract_with_mistral
from audit_engine import run_audit
from vendor_engine import resolve_vendor

log = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bill OCR Auditor", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("Settings")

selected_languages = st.sidebar.multiselect(
    "OCR Languages",
    options=list(SUPPORTED_LANGUAGES.keys()),
    default=["English", "Tamil"],
)

enable_translation = st.sidebar.checkbox("Translate Tamil to English", value=True)

st.sidebar.divider()
st.sidebar.subheader("Mistral AI")
mistral_key = os.getenv("MISTRAL_API_KEY", "")
use_mistral = st.sidebar.checkbox("Use Mistral AI for parsing", value=bool(mistral_key))
if use_mistral and mistral_key:
    st.sidebar.success("Mistral AI enabled")
elif use_mistral:
    st.sidebar.warning("Set MISTRAL_API_KEY in .env")
    use_mistral = False

st.sidebar.divider()
st.sidebar.caption("PaddleOCR + Mistral AI + Vendor Intelligence")

# ── Session state ─────────────────────────────────────────────────────────────
if "all_results" not in st.session_state:
    st.session_state.all_results = []


# ── PDF helper ────────────────────────────────────────────────────────────────

def convert_pdf(pdf_path: str) -> list[str]:
    from pdf2image import convert_from_path
    poppler_path = None
    if platform.system() == "Windows":
        poppler_path = r"C:\Users\mohanraj\poppler\Library\bin"
        if not os.path.isdir(poppler_path):
            st.error(f"Poppler not found at: {poppler_path}")
            return []
    images = convert_from_path(pdf_path, poppler_path=poppler_path)
    paths = []
    for i, img in enumerate(images):
        p = pdf_path.replace(os.path.splitext(pdf_path)[1], f"_page_{i}.png")
        img.save(p)
        paths.append(p)
    return paths


# ── Core pipeline ─────────────────────────────────────────────────────────────

def process_single_image(image_path, languages, do_translate, mistral_api_key=None):
    """Full pipeline: preprocess -> PaddleOCR -> parse -> validate -> audit."""
    original_rgb, processed_rgb, pil_image = preprocess_image(image_path)

    # PaddleOCR (try original, fallback to processed if few results)
    ocr_data = run_paddle_ocr(original_rgb, languages)
    if len(ocr_data) < 5:
        ocr_alt = run_paddle_ocr(processed_rgb, languages)
        if len(ocr_alt) > len(ocr_data):
            ocr_data = ocr_alt

    layout_available = len(ocr_data) > 0

    if layout_available:
        rows = group_rows(ocr_data)
        flat_lines = rows_to_lines(rows)
        ocr_confidence = paddle_avg_conf(ocr_data) * 100
    else:
        flat_lines, rows, ocr_confidence = [], [], 0.0

    # Normalize + detect language
    cleaned_lines = normalize_ocr_text(flat_lines)
    languages_detected = detect_languages("\n".join(cleaned_lines))

    original_cleaned = cleaned_lines[:]
    if do_translate and "Tamil" in languages_detected:
        _, translated_lines = translate_to_english(cleaned_lines)
    else:
        translated_lines = cleaned_lines

    # Parse: Mistral primary, regex fallback
    parsing_mode = "regex"
    mistral_result = None
    if mistral_api_key:
        mistral_result = extract_with_mistral("\n".join(cleaned_lines), mistral_api_key)

    if mistral_result:
        structured = mistral_result
        parsing_mode = "mistral"
        regex_result = parse_bill_layout(rows) if (layout_available and rows) else parse_bill_lines(translated_lines)
        for f in ["vendor_name", "invoice_number", "date", "time", "gstin", "phone_number"]:
            if not structured.get(f) and regex_result.get(f):
                structured[f] = regex_result[f]
        if not structured.get("items") and regex_result.get("items"):
            structured["items"] = regex_result["items"]
        for f in ["subtotal", "cgst", "sgst", "total_amount"]:
            if structured.get(f) is None and regex_result.get(f) is not None:
                structured[f] = regex_result[f]
    else:
        if layout_available and rows:
            structured = parse_bill_layout(rows)
            line_result = parse_bill_lines(translated_lines)
            for f in ["vendor_name", "invoice_number", "date", "time", "gstin", "phone_number"]:
                if not structured.get(f) and line_result.get(f):
                    structured[f] = line_result[f]
            if not structured.get("items") and line_result.get("items"):
                structured["items"] = line_result["items"]
            for f in ["subtotal", "cgst", "sgst", "total_amount"]:
                if structured.get(f) is None and line_result.get(f) is not None:
                    structured[f] = line_result[f]
        else:
            structured = parse_bill_lines(translated_lines)

    # Vendor intelligence
    vendor_result = resolve_vendor(
        structured.get("vendor_name"),
        structured.get("phone_number"),
        structured.get("gstin"),
    )
    if vendor_result["match_type"] == "matched" and vendor_result["canonical_name"]:
        structured["vendor_name"] = vendor_result["canonical_name"]

    # Audit
    noise_ratio = estimate_ocr_noise(cleaned_lines)
    quality = max(estimate_ocr_quality(cleaned_lines), ocr_confidence) if ocr_confidence > 0 else estimate_ocr_quality(cleaned_lines)
    audit_result = run_audit(structured, noise_ratio)

    for flag in vendor_result.get("fraud_flags", []):
        target = audit_result["high_risk"] if flag["severity"] == "high" else audit_result["medium_risk"]
        target.append({"rule": "Vendor Fraud Alert" if flag["severity"] == "high" else "Vendor Warning",
                        "detail": flag["detail"]})

    return {
        "raw_ocr_lines": flat_lines,
        "cleaned_ocr_lines": original_cleaned,
        "translated_lines": translated_lines,
        "structured_data": structured,
        "audit_report": {"high_risk": audit_result["high_risk"], "medium_risk": audit_result["medium_risk"], "audit_status": audit_result["audit_status"]},
        "vendor_info": vendor_result,
        "language_detected": languages_detected,
        "confidence_score": audit_result["confidence_score"],
        "ocr_quality": round(quality, 1),
        "parsing_mode": parsing_mode,
    }


def process_uploaded_file(uploaded_file, languages, do_translate, mistral_api_key):
    """Process one uploaded file (image or PDF). Returns list of result dicts."""
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    image_paths = convert_pdf(tmp_path) if suffix == ".pdf" else [tmp_path]
    results = []
    for i, img_path in enumerate(image_paths):
        result = process_single_image(img_path, languages, do_translate, mistral_api_key)
        result["source_file"] = uploaded_file.name
        result["page"] = i + 1
        result["image_path"] = img_path
        results.append(result)
    return results


# ── Title + Upload ────────────────────────────────────────────────────────────

st.title("Bill OCR Auditor")

uploaded_files = st.file_uploader(
    "Upload Bills (Images or PDFs)",
    type=["png", "jpg", "jpeg", "bmp", "tiff", "pdf"],
    accept_multiple_files=True,
)

if uploaded_files and st.button("Process All Bills", type="primary"):
    st.session_state.all_results = []
    progress = st.progress(0)
    total = len(uploaded_files)
    for idx, uf in enumerate(uploaded_files):
        with st.spinner(f"Processing {uf.name} ({idx+1}/{total})..."):
            st.session_state.all_results.extend(
                process_uploaded_file(uf, selected_languages, enable_translation, mistral_key if use_mistral else None)
            )
        progress.progress((idx + 1) / total)
    progress.empty()
    st.success(f"Processed {total} file(s) — {len(st.session_state.all_results)} page(s) total.")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_processed, tab_verify, tab_compare, tab_raw, tab_export = st.tabs(["Processed Output", "Verification", "Comparison", "Raw OCR", "Export"])
all_results = st.session_state.all_results

# ── TAB 1: PROCESSED OUTPUT ──────────────────────────────────────────────────
with tab_processed:
    if not all_results:
        st.info("Upload bills and click **Process All Bills** to see results.")
    else:
        for result in all_results:
            st.divider()
            st.subheader(f"{result['source_file']} — Page {result['page']}")
            col_img, col_info = st.columns([1, 2])
            with col_img:
                if os.path.exists(result.get("image_path", "")):
                    st.image(result["image_path"], use_container_width=True)
            with col_info:
                st.markdown(f"**Languages:** {', '.join(result['language_detected'])}")
                c1, c2, c3 = st.columns(3)
                score = result["confidence_score"]
                with c1:
                    (st.success if score >= 70 else st.warning if score >= 40 else st.error)(f"Confidence: **{score}/100**")
                with c2:
                    st.info(f"OCR Quality: **{result['ocr_quality']}%**")
                with c3:
                    st.info(f"Parser: **{{'mistral': 'Mistral AI', 'regex': 'Regex'}}.get(result.get('parsing_mode', ''), result.get('parsing_mode', ''))**")

            sd = result["structured_data"]
            c1, c2 = st.columns(2)
            with c1:
                for k in ["vendor_name", "invoice_number", "date", "gstin"]:
                    st.markdown(f"**{k.replace('_',' ').title()}:** {sd.get(k) or '`null`'}")
            with c2:
                st.markdown(f"**Phone:** {sd.get('phone_number') or '`null`'}")
                for k in ["subtotal", "total_amount"]:
                    v = sd.get(k)
                    st.markdown(f"**{k.replace('_',' ').title()}:** {f'Rs. {v}' if v is not None else '`null`'}")
                st.markdown(f"**CGST:** {sd.get('cgst') if sd.get('cgst') is not None else '`null`'}  |  **SGST:** {sd.get('sgst') if sd.get('sgst') is not None else '`null`'}")

            items = sd.get("items", [])
            if items:
                st.table([{"Name": it.get("name") or "-", "Qty": it.get("qty", "-"), "Price": it.get("price", "-"), "Total": it.get("total", "-")} for it in items])

            vi = result.get("vendor_info", {})
            if vi.get("match_type") == "matched":
                st.success(f"Vendor: **{vi['canonical_name']}** (Matched, {vi['invoice_count']} invoices)")
            elif vi.get("match_type") == "learned":
                st.info(f"Vendor: **{vi['canonical_name']}** (New — Auto-Learned)")

            audit = result["audit_report"]
            status = audit["audit_status"]
            (st.success if status == "APPROVED" else st.warning if status == "NEEDS REVIEW" else st.error)(f"Audit: **{status}**")
            for iss in audit.get("high_risk", []):
                st.error(f"{iss['rule']} — {iss['detail']}")
            for iss in audit.get("medium_risk", []):
                st.warning(f"{iss['rule']} — {iss['detail']}")

            with st.expander("Full JSON"):
                st.json({"structured_data": sd, "audit_report": audit, "language_detected": result["language_detected"], "confidence_score": score})

# ── TAB 2: VERIFICATION ──────────────────────────────────────────────────────
with tab_verify:
    if not all_results:
        st.info("Process bills first, then verify here.")
    else:
        labels = [f"{r['source_file']} — Page {r['page']}" for r in all_results]
        selected = st.selectbox("Select bill to verify", labels, key="verify_select")
        idx = labels.index(selected)
        result = all_results[idx]
        left, right = st.columns(2)
        with left:
            st.subheader("Bill Image")
            if os.path.exists(result.get("image_path", "")):
                st.image(result["image_path"], use_container_width=True)
            else:
                st.warning("Image not available.")
        with right:
            st.subheader("Extracted Data")
            sd = result["structured_data"]
            score = result["confidence_score"]
            (st.success if score >= 70 else st.warning if score >= 40 else st.error)(f"Confidence: {score}%")
            st.json(sd)
            st.subheader("Edit / Verify Fields")
            edited = {}
            editable = ["vendor_name", "invoice_number", "date", "time", "gstin", "phone_number", "subtotal", "cgst", "sgst", "total_amount"]
            for key in editable:
                val = sd.get(key)
                edited[key] = st.text_input(key, value=str(val) if val is not None else "", key=f"vedit_{idx}_{key}")
            if st.button("Update Result", key=f"vupdate_{idx}"):
                for key in editable:
                    val = edited[key].strip()
                    if val == "" or val.lower() == "none":
                        sd[key] = None
                    elif key in ("subtotal", "cgst", "sgst", "total_amount"):
                        try: sd[key] = float(val)
                        except ValueError: sd[key] = val
                    else:
                        sd[key] = val
                st.success("Result updated!")
                st.json(sd)

# ── TAB 3: COMPARISON ────────────────────────────────────────────────────────
with tab_compare:
    if not all_results:
        st.info("Process bills first to compare.")
    else:
        st.subheader(f"Comparing {len(all_results)} Bill(s)")
        rows_data = []
        for r in all_results:
            sd = r["structured_data"]
            rows_data.append({"File": r["source_file"], "Page": r["page"], "Vendor": sd.get("vendor_name") or "-", "Invoice": sd.get("invoice_number") or "-", "Date": sd.get("date") or "-", "GSTIN": sd.get("gstin") or "-", "Subtotal": sd.get("subtotal"), "CGST": sd.get("cgst"), "SGST": sd.get("sgst"), "Total": sd.get("total_amount"), "Items": len(sd.get("items", [])), "Confidence": r["confidence_score"], "Audit": r["audit_report"]["audit_status"], "Parser": r.get("parsing_mode", "-")})
        df = pd.DataFrame(rows_data)
        def _cc(val):
            try: v = float(val)
            except: return ""
            return "background-color: #c6efce; color: #006100" if v >= 70 else "background-color: #ffeb9c; color: #9c5700" if v >= 40 else "background-color: #ffc7ce; color: #9c0006"
        def _ca(val):
            return "background-color: #c6efce; color: #006100" if val == "APPROVED" else "background-color: #ffeb9c; color: #9c5700" if val == "NEEDS REVIEW" else "background-color: #ffc7ce; color: #9c0006"
        st.dataframe(df.style.map(_cc, subset=["Confidence"]).map(_ca, subset=["Audit"]), use_container_width=True)
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Total Bills", len(all_results))
        with c2: st.metric("Approved", sum(1 for r in all_results if r["audit_report"]["audit_status"] == "APPROVED"))
        with c3: st.metric("Needs Review", sum(1 for r in all_results if r["audit_report"]["audit_status"] == "NEEDS REVIEW"))
        with c4: st.metric("Rejected", sum(1 for r in all_results if r["audit_report"]["audit_status"] == "REJECTED"))
        totals = [r["structured_data"].get("total_amount") for r in all_results if r["structured_data"].get("total_amount")]
        if totals:
            st.metric("Sum of All Totals", f"Rs. {sum(totals):,.2f}")

# ── TAB 4: RAW OCR ───────────────────────────────────────────────────────────
with tab_raw:
    if not all_results:
        st.info("Process bills first to see raw OCR output.")
    else:
        st.write("Raw OCR text in the **original language** — no translation, no structuring.")
        for result in all_results:
            st.divider()
            st.subheader(f"{result['source_file']} — Page {result['page']}")
            c1, c2 = st.columns([1, 2])
            with c1:
                if os.path.exists(result.get("image_path", "")):
                    st.image(result["image_path"], use_container_width=True)
            with c2:
                st.json({"file": result["source_file"], "page": result["page"], "language_detected": result["language_detected"], "ocr_lines": result["raw_ocr_lines"]})
            if "Tamil" in result["language_detected"]:
                st.success("Output in **Tamil** (original) — no translation")
            st.text("\n".join(result["raw_ocr_lines"]))
        st.download_button("Download Raw OCR JSON", json.dumps([{"file": r["source_file"], "page": r["page"], "language_detected": r["language_detected"], "ocr_lines": r["raw_ocr_lines"]} for r in all_results], indent=2, ensure_ascii=False), "raw_ocr_output.json", "application/json", key="dl_raw")

# ── TAB 5: EXPORT ────────────────────────────────────────────────────────────
with tab_export:
    if not all_results:
        st.info("Process bills first to export.")
    else:
        st.subheader("Export All Results")
        st.markdown("### Summary CSV")
        csv_rows = [{"file": r["source_file"], "page": r["page"], "vendor_name": r["structured_data"].get("vendor_name"), "invoice_number": r["structured_data"].get("invoice_number"), "date": r["structured_data"].get("date"), "gstin": r["structured_data"].get("gstin"), "subtotal": r["structured_data"].get("subtotal"), "cgst": r["structured_data"].get("cgst"), "sgst": r["structured_data"].get("sgst"), "total_amount": r["structured_data"].get("total_amount"), "item_count": len(r["structured_data"].get("items", [])), "confidence": r["confidence_score"], "audit_status": r["audit_report"]["audit_status"], "parser": r.get("parsing_mode", "")} for r in all_results]
        df_csv = pd.DataFrame(csv_rows)
        st.dataframe(df_csv, use_container_width=True)
        st.download_button("Download CSV (Summary)", df_csv.to_csv(index=False).encode("utf-8"), "bill_results.csv", "text/csv", key="dl_csv")

        st.markdown("### Items CSV")
        item_rows = [{"file": r["source_file"], "page": r["page"], "vendor": r["structured_data"].get("vendor_name") or "", "item_name": it.get("name") or "", "qty": it.get("qty"), "price": it.get("price"), "total": it.get("total")} for r in all_results for it in r["structured_data"].get("items", [])]
        if item_rows:
            df_items = pd.DataFrame(item_rows)
            st.dataframe(df_items, use_container_width=True)
            st.download_button("Download CSV (Items)", df_items.to_csv(index=False).encode("utf-8"), "bill_items.csv", "text/csv", key="dl_items")
        else:
            st.warning("No line items extracted.")

        st.markdown("### Full JSON")
        st.download_button("Download JSON Report", json.dumps([{"file": r["source_file"], "page": r["page"], "structured_data": r["structured_data"], "audit_report": r["audit_report"], "language_detected": r["language_detected"], "confidence_score": r["confidence_score"]} for r in all_results], indent=2, ensure_ascii=False), "bill_audit_report.json", "application/json", key="dl_json")
