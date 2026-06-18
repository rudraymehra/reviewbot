"""Streamlit dashboard: review history, quality trends, severity-filtered findings.

Run with:  streamlit run dashboard/app.py
"""

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Make src/copilot importable when run via `streamlit run`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from copilot.config import get_settings  # noqa: E402
from copilot.models import SEVERITY_EMOJI  # noqa: E402

st.set_page_config(page_title="Code Review Copilot", page_icon="🔍", layout="wide")
st.title("🔍 Code Review Copilot — Dashboard")

DB_PATH = get_settings().copilot_db_path


@st.cache_data(ttl=10)
def load_reviews() -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query("SELECT * FROM reviews ORDER BY created_at DESC", conn)
    finally:
        conn.close()


df = load_reviews()
if df.empty:
    st.info("No reviews yet — run `copilot review <PR URL>` first.")
    st.stop()

# ---- top-line metrics ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("Reviews", len(df))
c2.metric("Avg quality score", f"{df.quality_score.mean():.0f}/100")
c3.metric("Total findings", int(df.finding_count.sum()))
total_in = int(df.input_tokens.sum())
total_cached = int(df.cached_tokens.sum()) if "cached_tokens" in df else 0
total_out = int(df.output_tokens.sum())
# claude-opus-4-8 pricing: $5 / $25 per MTok; cached input reads bill at ~0.1x ($0.50/MTok).
# input_tokens is the UNCACHED remainder, so cached reads must be added separately.
cost = total_in / 1e6 * 5 + total_cached / 1e6 * 0.5 + total_out / 1e6 * 25
c4.metric("Est. API cost", f"${cost:.2f}")

# ---- charts ----
left, right = st.columns(2)
with left:
    st.subheader("Quality score over time")
    trend = df[["created_at", "quality_score"]].copy()
    trend["created_at"] = pd.to_datetime(trend["created_at"])
    st.line_chart(trend.set_index("created_at").sort_index())

with right:
    st.subheader("Findings by severity (all reviews)")
    sev_counts: dict[str, int] = {}
    for raw in df.result_json:
        for f in json.loads(raw)["findings"]:
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
    if sev_counts:
        st.bar_chart(pd.Series(sev_counts).sort_values(ascending=False))
    else:
        st.caption("No findings recorded yet.")

# ---- review browser with severity filter ----
st.subheader("Review browser")
df["label"] = df.apply(lambda r: f"#{r['id']} · {r['repo']}#{r['pr_number']} — {r['pr_title']}", axis=1)
choice = st.selectbox("Pick a review", df.label)
row = df[df.label == choice].iloc[0]
result = json.loads(row.result_json)

st.markdown(
    f"**Score {row.quality_score}/100** · recommendation **{row.recommendation}** · "
    f"model `{row.model}` · tokens in/out: {row.input_tokens:,}/{row.output_tokens:,} "
    f"(cached: {row.cached_tokens:,})"
)
st.markdown(f"> {result['summary']['overall_assessment']}")
if result["summary"]["highest_risk_changes"]:
    st.markdown("**Highest-risk changes:**")
    for r in result["summary"]["highest_risk_changes"]:
        st.markdown(f"- {r}")

severities = sorted({f["severity"] for f in result["findings"]})
selected = st.multiselect("Filter by severity", severities, default=severities)

for f in result["findings"]:
    if f["severity"] not in selected:
        continue
    emoji = SEVERITY_EMOJI.get(f["severity"], "⚪")
    with st.expander(f"{emoji} [{f['severity'].upper()}] {f['file']}:{f['line']} — {f['title']}"):
        st.markdown(f"**Issue:** {f['issue']}")
        st.markdown(f"**Why it matters:** {f['why_it_matters']}")
        if f["suggested_fix"].strip():
            st.code(f["suggested_fix"], language="python")
        st.caption(f"confidence: {f['confidence']}")
