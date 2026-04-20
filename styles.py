"""
Industrial Skeuomorphism CSS Theme for Streamlit.

Design tokens: #e0e5ec chassis, #ff4757 accent, Inter + JetBrains Mono fonts,
neumorphic dual-shadow system, mechanical interaction physics.
"""


def get_css() -> str:
    return """<style>
/* ═══════════════════════════════════════════════════════════════════════
   FONTS
   ═══════════════════════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ═══════════════════════════════════════════════════════════════════════
   CSS VARIABLES
   ═══════════════════════════════════════════════════════════════════════ */
:root {
    --bg-chassis: #e0e5ec;
    --bg-panel: #f0f2f5;
    --bg-recessed: #d1d9e6;
    --text-primary: #2d3436;
    --text-muted: #1a1a2e;
    --accent: #ff4757;
    --accent-hover: #ff6b81;
    --accent-dark: #e84155;
    --success: #22c55e;
    --warning: #f59e0b;
    --error: #ef4444;
    --info: #3b82f6;
    --shadow-dark: #babecc;
    --shadow-light: #ffffff;
    --shadow-deep: #a3b1c6;

    --shadow-card: 8px 8px 16px var(--shadow-dark), -8px -8px 16px var(--shadow-light);
    --shadow-card-sm: 5px 5px 10px var(--shadow-dark), -5px -5px 10px var(--shadow-light);
    --shadow-floating: 12px 12px 24px var(--shadow-dark), -12px -12px 24px var(--shadow-light);
    --shadow-pressed: inset 6px 6px 12px var(--shadow-dark), inset -6px -6px 12px var(--shadow-light);
    --shadow-recessed: inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light);
    --shadow-recessed-sm: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 16px;
    --radius-xl: 24px;
    --radius-full: 9999px;
    --ease-mechanical: cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

/* ═══════════════════════════════════════════════════════════════════════
   GLOBAL / APP BACKGROUND
   ═══════════════════════════════════════════════════════════════════════ */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: var(--bg-chassis) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--text-primary) !important;
}

/* Subtle noise texture overlay */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    opacity: 0.025;
    mix-blend-mode: overlay;
    pointer-events: none;
    z-index: 0;
}

/* Hide default Streamlit chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] {
    background: rgba(224, 229, 236, 0.85) !important;
    backdrop-filter: blur(12px);
}

/* ═══════════════════════════════════════════════════════════════════════
   SIDEBAR
   ═══════════════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: var(--bg-chassis) !important;
    border-right: none !important;
    box-shadow: 4px 0 16px rgba(0,0,0,0.06) !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1rem !important;
}

/* Sidebar brand */
.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 4px 16px;
}
.brand-icon {
    width: 44px; height: 44px;
    border-radius: 12px;
    background: var(--accent);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    box-shadow: 3px 3px 6px rgba(166,50,60,0.3), -2px -2px 4px rgba(255,100,110,0.2);
    flex-shrink: 0;
}
.brand-name {
    font-weight: 800;
    font-size: 1rem;
    color: var(--text-primary);
    line-height: 1.2;
}
.brand-tagline {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.55rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    margin-top: 2px;
}

/* User info block */
.user-info {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: var(--bg-chassis);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-recessed-sm);
}
.user-avatar {
    width: 36px; height: 36px;
    border-radius: var(--radius-full);
    background: var(--bg-recessed);
    color: var(--text-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    box-shadow: var(--shadow-card-sm);
    flex-shrink: 0;
}
.user-name {
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--text-primary);
}
.user-role {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent);
    margin-top: 1px;
}

/* Sidebar radio as nav */
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] {
    gap: 4px !important;
}
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label {
    padding: 10px 14px !important;
    border-radius: var(--radius-md) !important;
    transition: all 0.2s ease !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    color: var(--text-primary) !important;
    cursor: pointer !important;
    margin: 0 !important;
    background: transparent !important;
    border: none !important;
}
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label:hover {
    color: var(--text-primary) !important;
    background: rgba(0,0,0,0.05) !important;
}
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label:has(input:checked) {
    background: var(--bg-chassis) !important;
    box-shadow: var(--shadow-recessed-sm) !important;
    color: var(--text-primary) !important;
    font-weight: 700 !important;
}
/* Hide radio circles */
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label > div:first-child {
    display: none !important;
}
[data-testid="stSidebar"] .stRadio > label {
    display: none !important;
}

/* Sidebar divider */
[data-testid="stSidebar"] hr {
    border: none !important;
    height: 2px !important;
    background: var(--bg-chassis) !important;
    box-shadow: 1px 1px 2px var(--shadow-dark), -1px -1px 2px var(--shadow-light) !important;
    margin: 16px 0 !important;
}

/* Sidebar subheader */
[data-testid="stSidebar"] .stMarkdown h3 {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.65rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: var(--text-muted) !important;
    font-weight: 700 !important;
    margin-bottom: 8px !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════════════════════ */

/* Primary buttons */
.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button {
    background: var(--accent) !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: 4px 4px 10px rgba(166,50,60,0.35), -3px -3px 8px rgba(255,130,140,0.2) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    font-weight: 700 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    padding: 12px 28px !important;
    min-height: 48px !important;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"]:hover,
div[data-testid="stFormSubmitButton"] > button:hover {
    background: var(--accent-hover) !important;
    transform: translateY(-1px) !important;
    box-shadow: 6px 6px 14px rgba(166,50,60,0.4), -4px -4px 10px rgba(255,130,140,0.25) !important;
}
.stButton > button[kind="primary"]:active,
div[data-testid="stFormSubmitButton"] > button:active {
    transform: translateY(2px) !important;
    box-shadow: inset 4px 4px 8px rgba(166,50,60,0.4), inset -4px -4px 8px rgba(255,130,140,0.15) !important;
}

/* Secondary / default buttons */
.stButton > button {
    background: var(--bg-chassis) !important;
    color: var(--text-primary) !important;
    border: none !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-card-sm) !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    padding: 10px 24px !important;
    min-height: 44px !important;
    transition: all 0.15s ease !important;
    letter-spacing: 0.02em !important;
}
.stButton > button:hover {
    color: var(--accent) !important;
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-card) !important;
}
.stButton > button:active {
    transform: translateY(2px) !important;
    box-shadow: var(--shadow-pressed) !important;
}

/* Logout button override */
.logout-btn .stButton > button {
    background: transparent !important;
    box-shadow: none !important;
    color: var(--text-muted) !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    min-height: 36px !important;
    padding: 6px 12px !important;
}
.logout-btn .stButton > button:hover {
    color: var(--accent) !important;
    box-shadow: none !important;
    transform: none !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   TEXT INPUTS & SELECTS
   ═══════════════════════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input,
.stTimeInput > div > div > input {
    background: var(--bg-chassis) !important;
    border: none !important;
    box-shadow: var(--shadow-recessed) !important;
    border-radius: var(--radius-md) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem !important;
    color: var(--text-primary) !important;
    padding: 14px 18px !important;
    min-height: 48px !important;
    transition: box-shadow 0.2s ease !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    box-shadow: var(--shadow-recessed), 0 0 0 2px var(--accent) !important;
    outline: none !important;
}
.stTextInput label, .stNumberInput label, .stSelectbox label,
.stDateInput label, .stTimeInput label, .stFileUploader label {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: var(--text-muted) !important;
}

/* Selectbox */
.stSelectbox > div > div {
    background: var(--bg-chassis) !important;
    border: none !important;
    box-shadow: var(--shadow-recessed) !important;
    border-radius: var(--radius-md) !important;
}
.stSelectbox [data-baseweb="select"] > div {
    background: transparent !important;
    border: none !important;
}

/* Checkbox */
[data-testid="stSidebar"] .stCheckbox label span {
    font-size: 0.82rem !important;
    color: var(--text-muted) !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   FILE UPLOADER
   ═══════════════════════════════════════════════════════════════════════ */
[data-testid="stFileUploader"] {
    background: var(--bg-chassis) !important;
    border-radius: var(--radius-xl) !important;
    box-shadow: var(--shadow-recessed) !important;
    padding: 24px !important;
}
[data-testid="stFileUploader"] section {
    border: 2px dashed var(--shadow-dark) !important;
    border-radius: var(--radius-lg) !important;
    padding: 32px !important;
    background: transparent !important;
    transition: border-color 0.3s ease !important;
}
[data-testid="stFileUploader"] section:hover {
    border-color: var(--accent) !important;
}
[data-testid="stFileUploader"] section > div > span {
    font-family: 'Inter', sans-serif !important;
    color: var(--text-muted) !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════════════════════════════════ */
.stProgress > div > div > div {
    background: var(--accent) !important;
    border-radius: var(--radius-full) !important;
}
.stProgress > div > div {
    background: var(--bg-recessed) !important;
    box-shadow: var(--shadow-recessed-sm) !important;
    border-radius: var(--radius-full) !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   DATAFRAME / TABLE
   ═══════════════════════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-card-sm) !important;
    overflow: hidden !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   ALERTS (SUCCESS / WARNING / ERROR / INFO)
   ═══════════════════════════════════════════════════════════════════════ */
.stAlert {
    border-radius: var(--radius-md) !important;
    border: none !important;
    box-shadow: var(--shadow-card-sm) !important;
    font-family: 'Inter', sans-serif !important;
}
div[data-testid="stNotification"] {
    border-radius: var(--radius-md) !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   EXPANDER
   ═══════════════════════════════════════════════════════════════════════ */
.streamlit-expanderHeader {
    background: var(--bg-chassis) !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-card-sm) !important;
    font-weight: 600 !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS — METRIC CARDS
   ═══════════════════════════════════════════════════════════════════════ */
.metric-card {
    background: var(--bg-chassis);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card-sm);
    padding: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: all 0.3s var(--ease-mechanical);
    cursor: default;
    min-height: 88px;
    position: relative;
    overflow: hidden;
}
.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-card);
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    border-radius: 4px 0 0 4px;
}
.metric-icon {
    width: 48px; height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9rem;
    font-weight: 700;
}
.metric-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
    letter-spacing: -0.02em;
}
.metric-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-top: 3px;
}

/* ═══════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS — NEU CARDS
   ═══════════════════════════════════════════════════════════════════════ */
.neu-card {
    background:
        radial-gradient(circle at 14px 14px, rgba(0,0,0,0.08) 1.5px, transparent 2.5px),
        radial-gradient(circle at calc(100% - 14px) 14px, rgba(0,0,0,0.08) 1.5px, transparent 2.5px),
        radial-gradient(circle at 14px calc(100% - 14px), rgba(0,0,0,0.08) 1.5px, transparent 2.5px),
        radial-gradient(circle at calc(100% - 14px) calc(100% - 14px), rgba(0,0,0,0.08) 1.5px, transparent 2.5px),
        var(--bg-chassis);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card);
    padding: 28px;
    position: relative;
    transition: all 0.3s var(--ease-mechanical);
}
.neu-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-floating);
}
/* Vent slots */
.neu-card .vents {
    position: absolute;
    top: 16px; right: 20px;
    display: flex;
    gap: 3px;
}
.neu-card .vents span {
    display: block;
    width: 2px; height: 20px;
    border-radius: var(--radius-full);
    background: var(--bg-recessed);
    box-shadow: inset 1px 1px 2px rgba(0,0,0,0.08);
}

/* Flat card (no screws) */
.neu-flat {
    background: var(--bg-chassis);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card-sm);
    padding: 24px;
    transition: all 0.3s ease;
}

/* Recessed panel */
.neu-recessed {
    background: var(--bg-chassis);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-recessed);
    padding: 16px;
}

/* ═══════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS — STATUS BADGES
   ═══════════════════════════════════════════════════════════════════════ */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: var(--radius-full);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.status-approved {
    background: rgba(34,197,94,0.12);
    color: #16a34a;
    box-shadow: 0 0 8px rgba(34,197,94,0.15);
}
.status-review {
    background: rgba(245,158,11,0.12);
    color: #d97706;
    box-shadow: 0 0 8px rgba(245,158,11,0.15);
}
.status-rejected {
    background: rgba(239,68,68,0.12);
    color: #dc2626;
    box-shadow: 0 0 8px rgba(239,68,68,0.15);
}

/* LED dots inside badges */
.led {
    width: 7px; height: 7px;
    border-radius: var(--radius-full);
    display: inline-block;
    flex-shrink: 0;
}
.led-green {
    background: var(--success);
    box-shadow: 0 0 6px rgba(34,197,94,0.7);
    animation: led-pulse 2s ease-in-out infinite;
}
.led-red {
    background: var(--accent);
    box-shadow: 0 0 6px rgba(255,71,87,0.7);
    animation: led-pulse 2s ease-in-out infinite;
}
.led-yellow {
    background: var(--warning);
    box-shadow: 0 0 6px rgba(245,158,11,0.7);
    animation: led-pulse 2s ease-in-out infinite;
}

@keyframes led-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ═══════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS — BILL RESULT CARD
   ═══════════════════════════════════════════════════════════════════════ */
.bill-card {
    background: var(--bg-chassis);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card);
    padding: 24px;
    margin-bottom: 20px;
    position: relative;
    border-left: 4px solid var(--accent);
}
.bill-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--bg-recessed);
}
.bill-card-title {
    font-weight: 700;
    font-size: 1rem;
    color: var(--text-primary);
}
.bill-card-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--text-muted);
    letter-spacing: 0.05em;
}

/* Field row in bill card */
.field-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 8px 0;
    border-bottom: 1px solid rgba(0,0,0,0.04);
}
.field-row:last-child { border-bottom: none; }
.field-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
}
.field-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
}
.field-value.highlight {
    color: var(--accent);
    font-weight: 700;
    font-size: 1rem;
}

/* Items table inside bill card */
.items-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin-top: 12px;
    font-size: 0.82rem;
}
.items-table thead th {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    padding: 10px 12px;
    text-align: left;
    background: var(--bg-chassis);
    box-shadow: var(--shadow-recessed-sm);
    border-radius: var(--radius-sm);
}
.items-table thead th:first-child { border-radius: var(--radius-sm) 0 0 var(--radius-sm); }
.items-table thead th:last-child { border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.items-table tbody td {
    padding: 10px 12px;
    color: var(--text-primary);
    border-bottom: 1px solid rgba(0,0,0,0.04);
    font-family: 'Inter', sans-serif;
}
.items-table tbody td.mono {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
}

/* ═══════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS — SECTION HEADERS
   ═══════════════════════════════════════════════════════════════════════ */
.section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
}
.section-header h2 {
    font-weight: 800;
    font-size: 1.5rem;
    color: var(--text-primary);
    margin: 0;
    letter-spacing: -0.02em;
}
.section-header .section-led {
    width: 10px; height: 10px;
    border-radius: var(--radius-full);
    background: var(--accent);
    box-shadow: 0 0 10px rgba(255,71,87,0.5);
    animation: led-pulse 2s ease-in-out infinite;
    flex-shrink: 0;
}
.section-subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    margin-top: -16px;
    margin-bottom: 24px;
}

/* ═══════════════════════════════════════════════════════════════════════
   LOGIN PAGE
   ═══════════════════════════════════════════════════════════════════════ */
.login-brand {
    text-align: center;
    margin-bottom: 8px;
    padding-top: 60px;
}
.login-logo {
    width: 72px; height: 72px;
    border-radius: 20px;
    background: var(--accent);
    color: white;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 1.2rem;
    letter-spacing: 0.05em;
    box-shadow: 8px 8px 16px rgba(166,50,60,0.3), -6px -6px 12px rgba(255,130,140,0.2);
    margin-bottom: 20px;
}
.login-title {
    font-weight: 800;
    font-size: 1.8rem;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    margin: 0 0 4px;
}
.login-subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-muted);
}
.login-card {
    background: var(--bg-chassis);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-card);
    padding: 36px 32px;
    margin-top: 24px;
}
.login-footer {
    text-align: center;
    margin-top: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    color: var(--text-muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* ═══════════════════════════════════════════════════════════════════════
   DOWNLOAD / EXPORT BUTTONS
   ═══════════════════════════════════════════════════════════════════════ */
.stDownloadButton > button {
    background: var(--bg-chassis) !important;
    color: var(--text-primary) !important;
    border: 2px solid var(--bg-recessed) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-card-sm) !important;
    font-weight: 700 !important;
    padding: 14px 28px !important;
    min-height: 52px !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.03em !important;
    transition: all 0.2s ease !important;
}
.stDownloadButton > button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-card) !important;
}
.stDownloadButton > button:active {
    transform: translateY(2px) !important;
    box-shadow: var(--shadow-pressed) !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   FORM STYLING
   ═══════════════════════════════════════════════════════════════════════ */
[data-testid="stForm"] {
    background: var(--bg-chassis) !important;
    border: none !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-card) !important;
    padding: 28px !important;
}

/* ═══════════════════════════════════════════════════════════════════════
   PLOTLY CHART CONTAINER
   ═══════════════════════════════════════════════════════════════════════ */
.chart-container {
    background: var(--bg-chassis);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-card-sm);
    padding: 20px;
    margin-bottom: 16px;
}
.chart-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 12px;
}

/* ═══════════════════════════════════════════════════════════════════════
   PAGE TITLE
   ═══════════════════════════════════════════════════════════════════════ */
.page-header {
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 2px solid var(--bg-chassis);
    box-shadow: 0 2px 0 var(--shadow-light);
}
.page-title {
    font-weight: 800;
    font-size: 1.8rem;
    color: var(--text-primary);
    letter-spacing: -0.03em;
    margin: 0;
    line-height: 1.2;
}
.page-description {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 6px;
    line-height: 1.5;
}

/* ═══════════════════════════════════════════════════════════════════════
   VERIFICATION FORM FIELDS
   ═══════════════════════════════════════════════════════════════════════ */
.verify-field-group {
    background: var(--bg-chassis);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-recessed-sm);
    padding: 12px 16px;
    margin-bottom: 12px;
}
.verify-field-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    margin-bottom: 4px;
}

/* ═══════════════════════════════════════════════════════════════════════
   EMPTY STATE
   ═══════════════════════════════════════════════════════════════════════ */
.empty-state {
    text-align: center;
    padding: 64px 32px;
    color: var(--text-muted);
}
.empty-state-icon {
    width: 72px; height: 72px;
    margin: 0 auto 20px;
    border-radius: var(--radius-full);
    background: var(--bg-chassis);
    box-shadow: var(--shadow-card-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.8rem;
    color: var(--shadow-dark);
}
.empty-state-title {
    font-weight: 700;
    font-size: 1.1rem;
    color: var(--text-primary);
    margin-bottom: 8px;
}
.empty-state-text {
    font-size: 0.85rem;
    color: var(--text-muted);
    max-width: 400px;
    margin: 0 auto;
    line-height: 1.6;
}

/* ═══════════════════════════════════════════════════════════════════════
   TAX BREAKDOWN MINI TABLE
   ═══════════════════════════════════════════════════════════════════════ */
.tax-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid rgba(0,0,0,0.04);
}
.tax-row:last-child { border-bottom: none; }
.tax-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.tax-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--text-primary);
}

/* ═══════════════════════════════════════════════════════════════════════
   RESPONSIVE
   ═══════════════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    .metric-card { min-height: 76px; padding: 16px; }
    .metric-value { font-size: 1.1rem; }
    .neu-card { padding: 20px; }
    .bill-card { padding: 18px; }
    .page-title { font-size: 1.4rem; }
    .login-brand { padding-top: 30px; }
    .login-title { font-size: 1.5rem; }
}

/* ═══════════════════════════════════════════════════════════════════════
   SCROLLBAR
   ═══════════════════════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track {
    background: var(--bg-chassis);
    box-shadow: var(--shadow-recessed-sm);
}
::-webkit-scrollbar-thumb {
    background: var(--shadow-dark);
    border-radius: var(--radius-full);
}
::-webkit-scrollbar-thumb:hover { background: var(--shadow-deep); }

/* ═══════════════════════════════════════════════════════════════════════
   GLOBAL TEXT DARK COLOR OVERRIDE
   Force ALL text to be dark and readable on the light chassis background.
   ═══════════════════════════════════════════════════════════════════════ */

/* All Streamlit text, labels, spans, paragraphs */
.stApp, .stApp p, .stApp span, .stApp label, .stApp div,
.stApp li, .stApp td, .stApp th, .stApp h1, .stApp h2,
.stApp h3, .stApp h4, .stApp h5, .stApp h6,
[data-testid="stSidebar"], [data-testid="stSidebar"] p,
[data-testid="stSidebar"] span, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] div {
    color: #1a1a2e !important;
}

/* Checkbox labels in sidebar */
[data-testid="stSidebar"] .stCheckbox label,
[data-testid="stSidebar"] .stCheckbox label span,
[data-testid="stSidebar"] .stCheckbox p {
    color: #1a1a2e !important;
    font-weight: 500 !important;
}

/* Sidebar radio nav items */
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stRadio span,
[data-testid="stSidebar"] .stRadio p {
    color: #1a1a2e !important;
}

/* Selectbox & multiselect text */
.stSelectbox span, .stMultiSelect span,
.stSelectbox div, .stMultiSelect div {
    color: #1a1a2e !important;
}

/* Input labels */
.stTextInput label, .stNumberInput label,
.stSelectbox label, .stMultiSelect label,
.stDateInput label, .stTimeInput label,
.stFileUploader label, .stCheckbox label {
    color: #1a1a2e !important;
}

/* Caption / small text */
.stApp small, .stApp .stCaption, .stApp caption {
    color: #2d3436 !important;
}

/* Metric values and labels */
[data-testid="stMetric"] label, [data-testid="stMetric"] div {
    color: #1a1a2e !important;
}

/* Alert text stays readable (don't override alert-specific colors) */
.stAlert p, .stAlert span { color: inherit !important; }

/* Keep white text on accent-colored elements */
.brand-icon, .login-logo,
.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button,
.status-badge { color: inherit !important; }
.brand-icon *, .login-logo * { color: white !important; }
.stButton > button[kind="primary"] *,
div[data-testid="stFormSubmitButton"] > button * { color: white !important; }

/* Keep status badge colors */
.status-approved { color: #16a34a !important; }
.status-review { color: #d97706 !important; }
.status-rejected { color: #dc2626 !important; }

/* User role accent color */
.user-role { color: var(--accent) !important; }

/* Metric card icon keeps its own color */
.metric-icon { color: inherit !important; }

/* File uploader browse button text */
[data-testid="stFileUploader"] button { color: #1a1a2e !important; }

/* Sidebar subheader */
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #2d3436 !important;
}

</style>"""
