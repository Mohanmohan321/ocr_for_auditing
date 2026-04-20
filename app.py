"""
Bill OCR Auditor — Professional SaaS Dashboard
Industrial Skeuomorphism UI with role-based access.

Pages:
  1. Dashboard    — KPI cards, trend charts, recent bills
  2. Upload Bills — drag-drop upload, card-based results
  3. Verification — side-by-side image vs editable form
  4. Export       — CSV / JSON / Excel download with preview
"""
import streamlit as st
import os
import json
import tempfile
import platform
import logging
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from styles import get_css
from config import SUPPORTED_LANGUAGES
from preprocessor import preprocess_image
from paddle_ocr_engine import run_paddle_ocr, avg_confidence as paddle_avg_conf
from layout_engine import group_rows, rows_to_lines
from ocr_utils import (
    normalize_ocr_text, detect_languages, translate_to_english,
    estimate_ocr_noise, estimate_ocr_quality, has_non_latin,
)
from parser import parse_bill_layout, parse_bill_lines
from mistral_engine import extract_with_mistral
from audit_engine import run_audit
from vendor_engine import resolve_vendor

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG (must be first Streamlit call)
# ═══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Bill OCR Auditor",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(get_css(), unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════
USERS = {
    "admin":   {"password": "admin123",  "role": "admin",  "name": "Administrator"},
    "vendor":  {"password": "vendor123", "role": "vendor", "name": "Vendor User"},
}


def check_auth() -> bool:
    return st.session_state.get("authenticated", False)


def do_login(username: str, password: str) -> bool:
    user = USERS.get(username)
    if user and user["password"] == password:
        st.session_state.authenticated = True
        st.session_state.username = username
        st.session_state.role = user["role"]
        st.session_state.display_name = user["name"]
        return True
    return False


def do_logout():
    for k in ["authenticated", "username", "role", "display_name"]:
        st.session_state.pop(k, None)
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════
if "all_results" not in st.session_state:
    st.session_state.all_results = []
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"

# ═══════════════════════════════════════════════════════════════════════════════
# PDF HELPER
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# CORE OCR PIPELINE (preserved logic)
# ═══════════════════════════════════════════════════════════════════════════════

def process_single_image(image_path, languages, do_translate, mistral_api_key=None, auto_detect=True):
    original_rgb, processed_rgb, pil_image = preprocess_image(image_path)

    if auto_detect:
        quick_data = run_paddle_ocr(original_rgb, ["English"])
        if quick_data:
            quick_text = " ".join(d["text"] for d in quick_data)
            detected_langs = detect_languages(quick_text)
            ocr_languages = list(set(["English"] + [l for l in detected_langs if l in SUPPORTED_LANGUAGES]))
        else:
            ocr_languages = ["English"]
    else:
        ocr_languages = languages

    ocr_data = run_paddle_ocr(original_rgb, ocr_languages)
    if len(ocr_data) < 5:
        ocr_alt = run_paddle_ocr(processed_rgb, ocr_languages)
        if len(ocr_alt) > len(ocr_data):
            ocr_data = ocr_alt

    layout_available = len(ocr_data) > 0
    if layout_available:
        rows = group_rows(ocr_data)
        flat_lines = rows_to_lines(rows)
        ocr_confidence = paddle_avg_conf(ocr_data) * 100
    else:
        flat_lines, rows, ocr_confidence = [], [], 0.0

    cleaned_lines = normalize_ocr_text(flat_lines)
    languages_detected = detect_languages("\n".join(cleaned_lines))
    original_cleaned = cleaned_lines[:]
    non_english_detected = [l for l in languages_detected if l not in ("English", "Unknown")]
    if do_translate and non_english_detected:
        _, translated_lines = translate_to_english(cleaned_lines)
    else:
        translated_lines = cleaned_lines

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

    vendor_result = resolve_vendor(
        structured.get("vendor_name"),
        structured.get("phone_number"),
        structured.get("gstin"),
    )
    if vendor_result["match_type"] == "matched" and vendor_result["canonical_name"]:
        structured["vendor_name"] = vendor_result["canonical_name"]

    noise_ratio = estimate_ocr_noise(cleaned_lines)
    quality = max(estimate_ocr_quality(cleaned_lines), ocr_confidence) if ocr_confidence > 0 else estimate_ocr_quality(cleaned_lines)
    audit_result = run_audit(structured, noise_ratio)

    for flag in vendor_result.get("fraud_flags", []):
        target = audit_result["high_risk"] if flag["severity"] == "high" else audit_result["medium_risk"]
        target.append({
            "rule": "Vendor Fraud Alert" if flag["severity"] == "high" else "Vendor Warning",
            "detail": flag["detail"],
        })

    return {
        "raw_ocr_lines": flat_lines,
        "cleaned_ocr_lines": original_cleaned,
        "translated_lines": translated_lines,
        "structured_data": structured,
        "audit_report": {
            "high_risk": audit_result["high_risk"],
            "medium_risk": audit_result["medium_risk"],
            "audit_status": audit_result["audit_status"],
        },
        "vendor_info": vendor_result,
        "language_detected": languages_detected,
        "confidence_score": audit_result["confidence_score"],
        "ocr_quality": round(quality, 1),
        "parsing_mode": parsing_mode,
    }


def process_uploaded_file(uploaded_file, languages, do_translate, mistral_api_key, auto_detect=True):
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    image_paths = convert_pdf(tmp_path) if suffix == ".pdf" else [tmp_path]
    results = []
    for i, img_path in enumerate(image_paths):
        result = process_single_image(img_path, languages, do_translate, mistral_api_key, auto_detect)
        result["source_file"] = uploaded_file.name
        result["page"] = i + 1
        result["image_path"] = img_path
        results.append(result)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# UI HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt_currency(val) -> str:
    if val is None:
        return "---"
    return f"Rs. {val:,.2f}"


def _fmt_number(val) -> str:
    if val is None:
        return "---"
    if isinstance(val, float):
        return f"{val:,.2f}"
    return f"{val:,}"


def metric_card_html(code: str, value: str, label: str, color: str = "#ff4757") -> str:
    return f"""
    <div class="metric-card" style="--card-accent: {color};">
        <div class="metric-icon" style="background: {color}12; color: {color};">
            {code}
        </div>
        <div>
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
        </div>
    </div>
    """


def status_badge_html(status: str) -> str:
    if status == "APPROVED":
        return '<span class="status-badge status-approved"><span class="led led-green"></span>Approved</span>'
    elif status == "NEEDS REVIEW":
        return '<span class="status-badge status-review"><span class="led led-yellow"></span>Needs Review</span>'
    else:
        return '<span class="status-badge status-rejected"><span class="led led-red"></span>Rejected</span>'


def render_bill_card(result: dict, idx: int):
    """Render a single bill result as a styled card."""
    sd = result["structured_data"]
    audit = result["audit_report"]
    status = audit["audit_status"]
    score = result["confidence_score"]

    vendor = sd.get("vendor_name") or "Unknown Vendor"
    invoice = sd.get("invoice_number") or "---"
    date_str = sd.get("date") or "---"
    gstin = sd.get("gstin") or "---"
    phone = sd.get("phone_number") or "---"
    total = sd.get("total_amount")
    subtotal = sd.get("subtotal")
    cgst = sd.get("cgst")
    sgst = sd.get("sgst")
    items = sd.get("items", [])
    parser = {"mistral": "Mistral AI", "regex": "Regex"}.get(result.get("parsing_mode", ""), "---")
    langs = ", ".join(result.get("language_detected", []))

    # Build items table rows
    items_html = ""
    if items:
        item_rows = ""
        for it in items:
            name = it.get("name") or "---"
            qty = it.get("qty", "---")
            price = it.get("price", "---")
            tot = it.get("total", "---")
            item_rows += f"""
            <tr>
                <td>{name}</td>
                <td class="mono">{qty}</td>
                <td class="mono">{price}</td>
                <td class="mono">{tot}</td>
            </tr>"""
        items_html = f"""
        <table class="items-table">
            <thead><tr>
                <th>Item</th><th>Qty</th><th>Price</th><th>Total</th>
            </tr></thead>
            <tbody>{item_rows}</tbody>
        </table>"""

    # Tax breakdown
    tax_html = f"""
    <div style="margin-top: 16px;">
        <div class="tax-row"><span class="tax-label">Subtotal</span><span class="tax-value">{_fmt_currency(subtotal)}</span></div>
        <div class="tax-row"><span class="tax-label">CGST</span><span class="tax-value">{_fmt_currency(cgst)}</span></div>
        <div class="tax-row"><span class="tax-label">SGST</span><span class="tax-value">{_fmt_currency(sgst)}</span></div>
        <div class="tax-row" style="border-top: 2px solid rgba(0,0,0,0.08); padding-top: 10px;">
            <span class="tax-label" style="font-size: 0.8rem; color: var(--text-primary);">Total</span>
            <span class="tax-value" style="font-size: 1.1rem; color: var(--accent);">{_fmt_currency(total)}</span>
        </div>
    </div>"""

    card_html = f"""
    <div class="bill-card">
        <div class="bill-card-header">
            <div>
                <div class="bill-card-title">{vendor}</div>
                <div class="bill-card-meta">{result['source_file']} &middot; Page {result['page']} &middot; {parser} &middot; {langs}</div>
            </div>
            <div>{status_badge_html(status)}</div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px 32px;">
            <div class="field-row"><span class="field-label">Invoice</span><span class="field-value">{invoice}</span></div>
            <div class="field-row"><span class="field-label">Date</span><span class="field-value">{date_str}</span></div>
            <div class="field-row"><span class="field-label">GSTIN</span><span class="field-value" style="font-size: 0.75rem;">{gstin}</span></div>
            <div class="field-row"><span class="field-label">Phone</span><span class="field-value">{phone}</span></div>
            <div class="field-row"><span class="field-label">Confidence</span><span class="field-value">{score}/100</span></div>
            <div class="field-row"><span class="field-label">OCR Quality</span><span class="field-value">{result['ocr_quality']}%</span></div>
        </div>
        {items_html}
        {tax_html}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    # Audit issues
    for iss in audit.get("high_risk", []):
        st.error(f"**{iss['rule']}** --- {iss['detail']}")
    for iss in audit.get("medium_risk", []):
        st.warning(f"**{iss['rule']}** --- {iss['detail']}")


def plotly_theme():
    """Shared plotly layout for industrial theme."""
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#2d3436", size=12),
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(gridcolor="rgba(186,190,204,0.3)", zerolinecolor="rgba(186,190,204,0.3)"),
        yaxis=dict(gridcolor="rgba(186,190,204,0.3)", zerolinecolor="rgba(186,190,204,0.3)"),
        hoverlabel=dict(bgcolor="#2d3436", font_color="white", font_size=12),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def login_page():
    col1, col2, col3 = st.columns([1.2, 1, 1.2])
    with col2:
        st.markdown("""
        <div class="login-brand">
            <div class="login-logo">BOA</div>
            <h2 class="login-title">Bill OCR Auditor</h2>
            <p class="login-subtitle">Industrial-Grade Invoice Intelligence</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
            if submitted:
                if do_login(username.strip(), password):
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("""
        <div class="login-footer">
            <span class="led led-green" style="margin-right: 6px;"></span> System Operational
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    with st.sidebar:
        # Brand
        st.markdown("""
        <div class="sidebar-brand">
            <div class="brand-icon">BOA</div>
            <div>
                <div class="brand-name">Bill OCR Auditor</div>
                <div class="brand-tagline">Invoice Intelligence</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # User info
        name = st.session_state.get("display_name", "User")
        role = st.session_state.get("role", "vendor")
        st.markdown(f"""
        <div class="user-info">
            <div class="user-avatar">{name[0].upper()}</div>
            <div>
                <div class="user-name">{name}</div>
                <div class="user-role">{role}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Navigation
        pages_list = ["Dashboard", "Upload Bills", "Verification", "Export"]
        current = st.session_state.get("page", "Dashboard")
        idx = pages_list.index(current) if current in pages_list else 0
        page = st.radio("NAV", pages_list, index=idx, label_visibility="collapsed")
        st.session_state.page = page

        st.divider()

        # OCR Settings
        st.markdown("### OCR Settings")

        auto_detect_lang = st.checkbox("Auto-detect languages", value=True)
        if auto_detect_lang:
            selected_languages = list(SUPPORTED_LANGUAGES.keys())
        else:
            selected_languages = st.multiselect(
                "OCR Languages",
                options=list(SUPPORTED_LANGUAGES.keys()),
                default=["English"],
            )

        enable_translation = st.checkbox("Auto-translate to English", value=True)

        st.divider()

        mistral_key = os.getenv("MISTRAL_API_KEY", "")
        use_mistral = st.checkbox("Use Mistral AI", value=bool(mistral_key))
        if use_mistral and mistral_key:
            st.markdown('<div style="display:flex;align-items:center;gap:6px;margin-top:4px;"><span class="led led-green"></span><span style="font-family:JetBrains Mono,monospace;font-size:0.6rem;color:var(--success);text-transform:uppercase;letter-spacing:0.08em;font-weight:600;">Mistral Connected</span></div>', unsafe_allow_html=True)
        elif use_mistral:
            st.warning("Set MISTRAL_API_KEY in .env")
            use_mistral = False

        st.divider()

        # Logout
        st.markdown('<div class="logout-btn">', unsafe_allow_html=True)
        if st.button("Logout", use_container_width=True, key="btn_logout"):
            do_logout()
        st.markdown('</div>', unsafe_allow_html=True)

    return {
        "auto_detect": auto_detect_lang,
        "languages": selected_languages,
        "translate": enable_translation,
        "use_mistral": use_mistral,
        "mistral_key": mistral_key if use_mistral else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def dashboard_page():
    st.markdown("""
    <div class="page-header">
        <h1 class="page-title">Dashboard</h1>
        <p class="page-description">Overview of your bill processing and GST analytics</p>
    </div>
    """, unsafe_allow_html=True)

    results = st.session_state.all_results

    # Compute metrics
    total_bills = len(results)
    total_cgst = sum(r["structured_data"].get("cgst") or 0 for r in results)
    total_sgst = sum(r["structured_data"].get("sgst") or 0 for r in results)
    total_gst = total_cgst + total_sgst
    total_amount = sum(r["structured_data"].get("total_amount") or 0 for r in results)
    approved = sum(1 for r in results if r["audit_report"]["audit_status"] == "APPROVED")
    rejected = sum(1 for r in results if r["audit_report"]["audit_status"] == "REJECTED")
    review = sum(1 for r in results if r["audit_report"]["audit_status"] == "NEEDS REVIEW")
    itc_claimed = sum(
        (r["structured_data"].get("cgst") or 0) + (r["structured_data"].get("sgst") or 0)
        for r in results if r["audit_report"]["audit_status"] == "APPROVED"
    )

    # KPI Cards Row 1
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(metric_card_html("GST", _fmt_currency(total_gst), "Total GST Paid", "#ff4757"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card_html("ITC", _fmt_currency(itc_claimed), "Total ITC Claimed", "#22c55e"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card_html("AMT", _fmt_currency(total_amount), "Total Bill Amount", "#3b82f6"), unsafe_allow_html=True)

    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

    # KPI Cards Row 2
    c4, c5, c6 = st.columns(3)
    with c4:
        st.markdown(metric_card_html("BIL", str(total_bills), "Total Bills", "#8b5cf6"), unsafe_allow_html=True)
    with c5:
        st.markdown(metric_card_html("REV", str(review), "Needs Review", "#f59e0b"), unsafe_allow_html=True)
    with c6:
        st.markdown(metric_card_html("REJ", str(rejected), "Failed / Rejected", "#ef4444"), unsafe_allow_html=True)

    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

    # Tax Breakdown Cards
    c7, c8, c9 = st.columns(3)
    with c7:
        st.markdown(metric_card_html("CG", _fmt_currency(total_cgst), "Total CGST", "#06b6d4"), unsafe_allow_html=True)
    with c8:
        st.markdown(metric_card_html("SG", _fmt_currency(total_sgst), "Total SGST", "#14b8a6"), unsafe_allow_html=True)
    with c9:
        st.markdown(metric_card_html("OK", str(approved), "Approved Bills", "#22c55e"), unsafe_allow_html=True)

    st.markdown("<div style='height: 32px'></div>", unsafe_allow_html=True)

    # Charts row
    if results:
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown('<p class="chart-title">Bill Amounts Overview</p>', unsafe_allow_html=True)
            amounts = []
            labels = []
            for r in results:
                sd = r["structured_data"]
                vendor = sd.get("vendor_name") or r["source_file"]
                labels.append(vendor[:20])
                amounts.append(sd.get("total_amount") or 0)
            fig = go.Figure(data=[
                go.Bar(
                    x=labels, y=amounts,
                    marker_color="#ff4757",
                    marker_line_width=0,
                    hovertemplate="<b>%{x}</b><br>Rs. %{y:,.2f}<extra></extra>",
                )
            ])
            fig.update_layout(**plotly_theme(), height=300, bargap=0.3)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        with chart_col2:
            st.markdown('<p class="chart-title">Tax Breakdown</p>', unsafe_allow_html=True)
            tax_labels = ["CGST", "SGST"]
            tax_values = [total_cgst, total_sgst]
            colors = ["#06b6d4", "#14b8a6"]
            if all(v == 0 for v in tax_values):
                tax_values = [1, 1]  # placeholder
            fig2 = go.Figure(data=[
                go.Pie(
                    labels=tax_labels, values=tax_values,
                    marker=dict(colors=colors, line=dict(color="#e0e5ec", width=3)),
                    hole=0.55,
                    textinfo="label+percent",
                    textfont=dict(family="JetBrains Mono", size=12),
                    hovertemplate="<b>%{label}</b><br>Rs. %{value:,.2f}<extra></extra>",
                )
            ])
            fig2.update_layout(**plotly_theme(), height=300, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

        # Recent Bills Table
        st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)
        st.markdown('<p class="chart-title">Recent Bills</p>', unsafe_allow_html=True)
        table_rows = []
        for r in results:
            sd = r["structured_data"]
            table_rows.append({
                "File": r["source_file"],
                "Vendor": sd.get("vendor_name") or "---",
                "Invoice": sd.get("invoice_number") or "---",
                "Date": sd.get("date") or "---",
                "Total": _fmt_currency(sd.get("total_amount")),
                "GST": _fmt_currency((sd.get("cgst") or 0) + (sd.get("sgst") or 0)),
                "Status": r["audit_report"]["audit_status"],
                "Confidence": f"{r['confidence_score']}/100",
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#babecc" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
            </div>
            <div class="empty-state-title">No Bills Processed Yet</div>
            <div class="empty-state-text">Upload and process bills from the Upload Bills page to see your dashboard analytics here.</div>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# UPLOAD PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def upload_page(settings: dict):
    st.markdown("""
    <div class="page-header">
        <h1 class="page-title">Upload Bills</h1>
        <p class="page-description">Upload bill images or PDFs for OCR extraction and auditing</p>
    </div>
    """, unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Drop files here or click to browse",
        type=["png", "jpg", "jpeg", "bmp", "tiff", "pdf"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    if uploaded_files:
        # File preview
        st.markdown(f'<div class="section-subtitle">Selected: {len(uploaded_files)} file(s)</div>', unsafe_allow_html=True)

        preview_cols = st.columns(min(len(uploaded_files), 5))
        for i, uf in enumerate(uploaded_files[:5]):
            with preview_cols[i]:
                if uf.type and uf.type.startswith("image"):
                    st.image(uf, caption=uf.name[:20], use_container_width=True)
                else:
                    st.markdown(f"""
                    <div class="neu-recessed" style="text-align:center; padding: 24px 8px;">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#4a5568" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto 8px;display:block;">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                        <div style="font-size:0.7rem;color:var(--text-muted);font-family:JetBrains Mono,monospace;">{uf.name[:18]}</div>
                    </div>
                    """, unsafe_allow_html=True)

        st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

        if st.button("Process All Bills", type="primary", use_container_width=False, key="btn_process"):
            st.session_state.all_results = []
            progress = st.progress(0)
            total = len(uploaded_files)
            for idx, uf in enumerate(uploaded_files):
                with st.spinner(f"Processing {uf.name} ({idx+1}/{total})..."):
                    st.session_state.all_results.extend(
                        process_uploaded_file(
                            uf,
                            settings["languages"],
                            settings["translate"],
                            settings["mistral_key"],
                            settings["auto_detect"],
                        )
                    )
                progress.progress((idx + 1) / total)
            progress.empty()
            st.success(f"Processed {total} file(s) --- {len(st.session_state.all_results)} page(s) extracted.")

    # Display results
    results = st.session_state.all_results
    if results:
        st.markdown("<div style='height: 24px'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="section-header">
            <div class="section-led"></div>
            <h2>Extraction Results ({len(results)} bills)</h2>
        </div>
        """, unsafe_allow_html=True)

        for i, result in enumerate(results):
            col_img, col_data = st.columns([1, 2.5])
            with col_img:
                if os.path.exists(result.get("image_path", "")):
                    st.image(result["image_path"], use_container_width=True)
            with col_data:
                render_bill_card(result, i)

            st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
    elif not uploaded_files:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#babecc" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
            </div>
            <div class="empty-state-title">Upload Bills to Get Started</div>
            <div class="empty-state-text">Drag and drop bill images or PDFs above. Supports PNG, JPG, TIFF, BMP, and PDF formats.</div>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def verification_page():
    st.markdown("""
    <div class="page-header">
        <h1 class="page-title">Verification</h1>
        <p class="page-description">Review extracted data side-by-side with the original bill image</p>
    </div>
    """, unsafe_allow_html=True)

    results = st.session_state.all_results
    if not results:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#babecc" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 11l3 3L22 4"/>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
            </div>
            <div class="empty-state-title">No Bills to Verify</div>
            <div class="empty-state-text">Process bills from the Upload page first, then return here to verify and correct the extracted data.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    labels = [f"{r['source_file']} --- Page {r['page']}" for r in results]
    selected = st.selectbox("Select bill to verify", labels, key="verify_select")
    idx = labels.index(selected)
    result = results[idx]
    sd = result["structured_data"]
    score = result["confidence_score"]

    st.markdown("<div style='height: 16px'></div>", unsafe_allow_html=True)

    # Status + confidence bar
    status = result["audit_report"]["audit_status"]
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap: 16px; margin-bottom: 20px;">
        {status_badge_html(status)}
        <span style="font-family: JetBrains Mono, monospace; font-size: 0.8rem; font-weight: 600; color: var(--text-muted);">
            Confidence: {score}/100
        </span>
    </div>
    """, unsafe_allow_html=True)

    col_img, col_form = st.columns([1, 1.2])

    with col_img:
        st.markdown('<p class="chart-title">Original Bill</p>', unsafe_allow_html=True)
        if os.path.exists(result.get("image_path", "")):
            st.image(result["image_path"], use_container_width=True)
        else:
            st.warning("Image not available.")

    with col_form:
        st.markdown('<div class="chart-title" style="margin-bottom:16px;">Extracted Data</div>', unsafe_allow_html=True)

        with st.form(f"verify_form_{idx}"):
            editable_fields = {
                "vendor_name": "Vendor Name",
                "invoice_number": "Invoice Number",
                "date": "Date",
                "gstin": "GSTIN",
                "phone_number": "Phone Number",
            }
            edited = {}
            for key, label in editable_fields.items():
                val = sd.get(key)
                edited[key] = st.text_input(
                    label,
                    value=str(val) if val is not None else "",
                    key=f"vf_{idx}_{key}",
                )

            st.markdown("---")

            amount_fields = {
                "subtotal": "Subtotal",
                "cgst": "CGST",
                "sgst": "SGST",
                "total_amount": "Total Amount",
            }
            ac1, ac2 = st.columns(2)
            for i, (key, label) in enumerate(amount_fields.items()):
                val = sd.get(key)
                col = ac1 if i % 2 == 0 else ac2
                with col:
                    edited[key] = st.text_input(
                        label,
                        value=str(val) if val is not None else "",
                        key=f"vf_{idx}_{key}",
                    )

            st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

            bc1, bc2 = st.columns(2)
            with bc1:
                save_btn = st.form_submit_button("Save Changes", use_container_width=True, type="primary")
            with bc2:
                approve_btn = st.form_submit_button("Approve Bill", use_container_width=True)

            if save_btn or approve_btn:
                for key in editable_fields:
                    val = edited[key].strip()
                    sd[key] = val if val and val.lower() not in ("none", "") else None
                for key in amount_fields:
                    val = edited[key].strip()
                    if val and val.lower() not in ("none", ""):
                        try:
                            sd[key] = float(val)
                        except ValueError:
                            sd[key] = val
                    else:
                        sd[key] = None
                if approve_btn:
                    result["audit_report"]["audit_status"] = "APPROVED"
                    st.success("Bill approved and saved.")
                else:
                    st.success("Changes saved successfully.")

        # Items display (read-only)
        items = sd.get("items", [])
        if items:
            st.markdown('<div class="chart-title" style="margin-top:16px;">Line Items</div>', unsafe_allow_html=True)
            items_df = pd.DataFrame([
                {
                    "Item": it.get("name") or "---",
                    "Qty": it.get("qty", "---"),
                    "Price": it.get("price", "---"),
                    "Total": it.get("total", "---"),
                }
                for it in items
            ])
            st.dataframe(items_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT PAGE
# ═══════════════════════════════════════════════════════════════════════════════

def export_page():
    st.markdown("""
    <div class="page-header">
        <h1 class="page-title">Export</h1>
        <p class="page-description">Download processed bill data in multiple formats</p>
    </div>
    """, unsafe_allow_html=True)

    results = st.session_state.all_results
    if not results:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#babecc" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
            </div>
            <div class="empty-state-title">Nothing to Export</div>
            <div class="empty-state-text">Process some bills first, then come back here to download the results.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Summary table
    st.markdown('<p class="chart-title">Summary Preview</p>', unsafe_allow_html=True)
    summary_rows = []
    for r in results:
        sd = r["structured_data"]
        summary_rows.append({
            "File": r["source_file"],
            "Page": r["page"],
            "Vendor": sd.get("vendor_name") or "---",
            "Invoice": sd.get("invoice_number") or "---",
            "Date": sd.get("date") or "---",
            "GSTIN": sd.get("gstin") or "---",
            "Subtotal": sd.get("subtotal"),
            "CGST": sd.get("cgst"),
            "SGST": sd.get("sgst"),
            "Total": sd.get("total_amount"),
            "Items": len(sd.get("items", [])),
            "Confidence": r["confidence_score"],
            "Status": r["audit_report"]["audit_status"],
        })
    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

    st.markdown("<div style='height: 24px'></div>", unsafe_allow_html=True)

    # Download buttons
    st.markdown("""
    <div class="section-header">
        <div class="section-led"></div>
        <h2>Download Files</h2>
    </div>
    """, unsafe_allow_html=True)

    # Prepare download data
    csv_data = df_summary.to_csv(index=False).encode("utf-8")
    json_data = json.dumps([
        {
            "file": r["source_file"],
            "page": r["page"],
            "structured_data": r["structured_data"],
            "audit_report": r["audit_report"],
            "language_detected": r["language_detected"],
            "confidence_score": r["confidence_score"],
        }
        for r in results
    ], indent=2, ensure_ascii=False).encode("utf-8")

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="Summary", index=False)
        item_rows = [
            {
                "File": r["source_file"],
                "Page": r["page"],
                "Vendor": r["structured_data"].get("vendor_name") or "",
                "Item": it.get("name") or "",
                "Qty": it.get("qty"),
                "Price": it.get("price"),
                "Total": it.get("total"),
            }
            for r in results
            for it in r["structured_data"].get("items", [])
        ]
        if item_rows:
            pd.DataFrame(item_rows).to_excel(writer, sheet_name="Items", index=False)
    excel_buffer.seek(0)
    excel_data = excel_buffer.getvalue()

    dc1, dc2, dc3 = st.columns(3)

    with dc1:
        st.markdown("""<div class="neu-flat" style="text-align:center; padding: 24px 20px;">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin: 0 auto 10px; display: block;">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            <div style="font-weight:700; margin-bottom: 2px;">CSV Report</div>
            <div style="font-size:0.7rem; margin-bottom: 4px;">Summary + line items</div>
        </div>""", unsafe_allow_html=True)
        st.download_button("Download CSV", csv_data, "bill_results.csv", "text/csv", key="dl_csv", use_container_width=True)

    with dc2:
        st.markdown("""<div class="neu-flat" style="text-align:center; padding: 24px 20px;">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin: 0 auto 10px; display: block;">
                <polyline points="16 18 22 12 16 6"/>
                <polyline points="8 6 2 12 8 18"/>
            </svg>
            <div style="font-weight:700; margin-bottom: 2px;">JSON Report</div>
            <div style="font-size:0.7rem; margin-bottom: 4px;">Full structured data</div>
        </div>""", unsafe_allow_html=True)
        st.download_button("Download JSON", json_data, "bill_audit_report.json", "application/json", key="dl_json", use_container_width=True)

    with dc3:
        st.markdown("""<div class="neu-flat" style="text-align:center; padding: 24px 20px;">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin: 0 auto 10px; display: block;">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <line x1="3" y1="9" x2="21" y2="9"/>
                <line x1="3" y1="15" x2="21" y2="15"/>
                <line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
            <div style="font-weight:700; margin-bottom: 2px;">Excel Workbook</div>
            <div style="font-size:0.7rem; margin-bottom: 4px;">Summary + items sheets</div>
        </div>""", unsafe_allow_html=True)
        st.download_button("Download Excel", excel_data, "bill_report.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_xlsx", use_container_width=True)

    # Items table
    st.markdown("<div style='height: 24px'></div>", unsafe_allow_html=True)
    item_rows_preview = [
        {
            "File": r["source_file"],
            "Vendor": r["structured_data"].get("vendor_name") or "",
            "Item": it.get("name") or "---",
            "Qty": it.get("qty", "---"),
            "Price": it.get("price", "---"),
            "Total": it.get("total", "---"),
        }
        for r in results
        for it in r["structured_data"].get("items", [])
    ]
    if item_rows_preview:
        st.markdown('<p class="chart-title">Line Items Preview</p>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(item_rows_preview), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTING
# ═══════════════════════════════════════════════════════════════════════════════

if not check_auth():
    login_page()
else:
    settings = render_sidebar()
    page = st.session_state.get("page", "Dashboard")

    if page == "Dashboard":
        dashboard_page()
    elif page == "Upload Bills":
        upload_page(settings)
    elif page == "Verification":
        verification_page()
    elif page == "Export":
        export_page()
