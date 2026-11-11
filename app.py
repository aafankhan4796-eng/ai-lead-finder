"""Lead Finder: rank companies against an ideal customer profile and draft outreach.

Run locally:  streamlit run app.py
"""

from dataclasses import replace

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from leadfinder.outreach import LINKEDIN_LIMIT, ai_rewrite, drafts
from leadfinder.scoring import CRITERIA, LABELS, PRESETS, Profile, load_companies, rank

NAVY, INK, MUTED, LINE = "#1F4E79", "#1B2430", "#6B7686", "#E3E7ED"
# One hue family for the six criteria, so the chart reads as one measure split in parts.
CRIT_COLORS = {"sector": "#1F4E79", "size": "#2F6FA6", "location": "#5B92C4",
               "momentum": "#8DB3D9", "data": "#B9CFE6", "need": "#D9A441"}
TIER_STYLE = {"A": "#2E7D5B", "B": "#B7862B", "C": "#A3443B"}

st.set_page_config(page_title="Lead Finder", layout="wide")
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"], .stMarkdown, .stText, input, textarea, button {{ font-family: 'Inter', sans-serif; }}
  .block-container {{ padding-top: 3.2rem; max-width: 1180px; }}
  .lf-head {{ border-bottom: 1px solid {LINE}; padding-bottom: 14px; margin-bottom: 18px; }}
  .lf-title {{ font-size: 28px; font-weight: 700; color: {INK}; margin: 0; padding: 0; letter-spacing: -0.3px; }}
  .lf-head p {{ color: {MUTED}; font-size: 14.5px; margin: 4px 0 0; }}
  div[data-testid="stMetric"] {{ border: 1px solid {LINE}; border-radius: 8px; padding: 12px 16px; background: #FFFFFF; }}
  div[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 13px; }}
  div[data-testid="stMetricValue"] {{ font-size: 26px; font-weight: 600; color: {INK}; }}
  h3 {{ font-size: 17px !important; font-weight: 600 !important; color: {INK} !important; margin-top: 8px !important; }}
  section[data-testid="stSidebar"] h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.8px;
          color: {MUTED}; font-weight: 600; }}
  .lf-foot {{ color: {MUTED}; font-size: 12.5px; border-top: 1px solid {LINE}; margin-top: 28px; padding-top: 12px; }}
  .lf-foot a {{ color: {NAVY}; text-decoration: none; }}
  .lf-why {{ background: #F3F5F8; border-left: 3px solid {NAVY}; padding: 10px 14px; border-radius: 4px;
          color: {INK}; font-size: 14px; margin: 6px 0 12px; }}
</style>
<div class="lf-head">
  <div class="lf-title">Lead Finder</div>
  <p>Rank companies against an ideal customer profile, see what drives each score, and draft outreach for the best fits.</p>
</div>
""", unsafe_allow_html=True)

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown("## Target profile")
    preset_name = st.selectbox("Preset", list(PRESETS) + ["Custom"], help="Presets fill in the fields below.")
    base = PRESETS.get(preset_name, Profile())
    sectors_all = ["Fintech", "Software", "Logistics", "Healthtech", "Retail & e-commerce", "Energy & climate",
                   "Proptech", "Legaltech", "Edtech", "AgriTech", "Mobility", "Food & beverage", "Non-profit",
                   "Financial services", "Travel", "Media", "Construction", "Professional services"]
    sectors = st.multiselect("Sectors", sectors_all, default=base.sectors, placeholder="Any sector")
    lo, hi = st.slider("Employees", 1, 2000, (base.min_employees, base.max_employees))
    cities = st.multiselect("Cities", ["Amsterdam", "Rotterdam", "Utrecht", "The Hague", "Eindhoven", "Delft",
                                       "Groningen"], default=base.cities, placeholder="Any city")
    no_ai = st.checkbox("Prefer companies without an in-house AI team", value=base.prefer_no_ai_team)
    st.markdown("## Criteria weights")
    weights = {c: st.slider(LABELS[c], 0.0, 2.0, float(base.weights.get(c, 1.0)), 0.25) for c in CRITERIA}
    st.markdown("## Sender")
    sender = st.text_input("Name", "", placeholder="Your name")
    org = st.text_input("Organisation", "", placeholder="Your company or team")
    pitch = st.text_input("Offer", base.pitch)

profile = replace(base, sectors=sectors, min_employees=lo, max_employees=hi, cities=cities,
                  prefer_no_ai_team=no_ai, weights=weights, pitch=pitch)

# ---------------- data ----------------
left, right = st.columns([3, 2])
with left:
    src = st.radio("Data source", ["Sample data (36 fictional companies)", "Upload CSV"], horizontal=True,
                   label_visibility="collapsed")
raw = pd.read_csv("data/sample_companies.csv")
if src == "Upload CSV":
    with right:
        up = st.file_uploader("CSV with company, sector, employees", type="csv", label_visibility="collapsed")
    st.download_button("Download CSV template", raw.head(3).to_csv(index=False), "lead_template.csv")
    if not up:
        st.info("Upload a CSV export (for example from LinkedIn Sales Navigator or Dealroom). Required columns: "
                "company, sector, employees.")
        st.stop()
    raw = pd.read_csv(up)

try:
    companies = load_companies(raw)
except ValueError as e:
    st.error(str(e))
    st.stop()

ranked = rank(companies, profile)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Companies scored", len(ranked))
c2.metric("Tier A", int((ranked["tier"] == "A").sum()))
c3.metric("Tier B", int((ranked["tier"] == "B").sum()))
c4.metric("Median score", f"{ranked['score'].median():.0f}")

tab_rank, tab_list, tab_out, tab_method = st.tabs(["Ranking", "All companies", "Outreach", "Method"])

# ---------------- ranking chart ----------------
with tab_rank:
    st.markdown("### Top 12 companies, score by criterion")
    top = ranked.head(12).iloc[::-1]
    total_w = sum(weights.values()) or 1
    fig = go.Figure()
    for c in CRITERIA:
        fig.add_bar(y=top["company"], x=100 * top[f"s_{c}"] * weights[c] / total_w, name=LABELS[c],
                    orientation="h", marker=dict(color=CRIT_COLORS[c], line=dict(color="#FFFFFF", width=1)),
                    hovertemplate="%{y}<br>" + LABELS[c] + ": %{x:.0f} points<extra></extra>")
    fig.add_scatter(y=top["company"], x=top["score"] + 1.5, mode="text", text=top["score"].astype(str),
                    textposition="middle right", textfont=dict(color=INK, size=12), showlegend=False,
                    hoverinfo="skip")
    fig.update_layout(barmode="stack", height=470, bargap=0.35, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                      font=dict(family="Inter, sans-serif", color=MUTED, size=12),
                      margin=dict(l=0, r=20, t=10, b=0),
                      legend=dict(orientation="h", y=1.08, x=0, traceorder="normal", font=dict(size=12)))
    fig.update_xaxes(range=[0, 105], gridcolor=LINE, zeroline=False, title="Score (0 to 100)")
    fig.update_yaxes(tickfont=dict(color=INK, size=12.5))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption("Each bar shows how many of the company's points come from each criterion, given the current weights.")

# ---------------- table ----------------
with tab_list:
    tiers = st.segmented_control("Tier", ["All", "A", "B", "C"], default="All") or "All"
    view = ranked if tiers == "All" else ranked[ranked["tier"] == tiers]
    table = view[["tier", "score", "company", "sector", "city", "employees", "funding_stage", "has_ai_team",
                  "why"]].rename(columns={"tier": "Tier", "score": "Score", "company": "Company",
                                          "sector": "Sector", "city": "City", "employees": "Employees",
                                          "funding_stage": "Stage", "has_ai_team": "AI team",
                                          "why": "Rationale"})
    st.dataframe(
        table.style.map(lambda t: f"color: {TIER_STYLE.get(t, INK)}; font-weight: 600", subset=["Tier"]),
        hide_index=True, width="stretch", height=min(36 * (len(table) + 1) + 4, 640),
        column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                       "Rationale": st.column_config.TextColumn(width="large")})
    export = ranked[["tier", "score", "company", "sector", "city", "employees", "contact_role", "website",
                     "why"]].copy()
    export["status"], export["next_follow_up"] = "To contact", ""
    st.download_button("Export as tracker (CSV)", export.to_csv(index=False), "ranked_leads.csv")

# ---------------- outreach ----------------
with tab_out:
    by_name = ranked.set_index("company")
    pick = st.selectbox("Company", ranked["company"],
                        format_func=lambda n: f"{n}   ·   Tier {by_name.loc[n, 'tier']}   ·   {by_name.loc[n, 'score']}")
    lead = ranked[ranked["company"] == pick].iloc[0]
    st.markdown(f'<div class="lf-why">{lead["why"]}</div>', unsafe_allow_html=True)
    d = drafts(lead, sender or "[Your name]", org or "[Organisation]", pitch)
    a, b = st.columns([3, 2])
    with a:
        st.text_area("Email", d["email"], height=360)
        try:
            key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            key = None
        if key and st.button("Rewrite with Claude"):
            st.text_area("Rewritten email", ai_rewrite(d["email"], lead, key) or "Rewrite unavailable.", height=300)
    with b:
        st.text_area("LinkedIn connection note", d["linkedin"], height=130)
        st.caption(f"{len(d['linkedin'])} of {LINKEDIN_LIMIT} characters")
        st.text_area("Follow-up after 3 to 4 days", d["follow_up"], height=130)

# ---------------- method ----------------
with tab_method:
    st.markdown("### How the score works")
    st.markdown(
        "Each company gets a score between 0 and 1 on six criteria. The final score is the weighted average, "
        "shown out of 100. Weights are set in the sidebar.")
    st.table(pd.DataFrame({
        "Criterion": [LABELS[c] for c in CRITERIA],
        "Scored as": [
            "1 if the sector is in the target list, otherwise 0",
            "1 inside the employee range, falling to 0 at half the minimum or double the maximum",
            "1 in a target city, 0.3 elsewhere",
            "Half recent funding (full within a month, zero after 24), half open roles (full at 10 or more)",
            "Data maturity on a 1 to 5 scale, rescaled to 0 to 1",
            "1 without an in-house AI team, 0.2 with one (when that preference is on)",
        ],
        "Weight": [f"{weights[c]:.2f}" for c in CRITERIA],
    }).set_index("Criterion"))
    st.markdown("**Tiers:** A from 75, B from 55, C below. A company outside the target sectors is capped at B.")

st.markdown('<div class="lf-foot">Aafan Khan · '
            '<a href="https://github.com/aafankhan4796-eng">GitHub</a> · '
            '<a href="https://www.linkedin.com/in/aafan-khan">LinkedIn</a> · '
            'Sample data is fictional. Contact business addresses only and include an opt-out.</div>',
            unsafe_allow_html=True)
