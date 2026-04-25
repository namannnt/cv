import streamlit as st
import pandas as pd
import os
import sys
import glob

# ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.analytics import AnalyticsEngine
from intelligence.coach import AICoach
from intelligence.gamification import Gamification

st.set_page_config(page_title="Attention Monitor", layout="wide", page_icon="🧠")

st.title("🧠 Attention Monitor Dashboard")

# --- session selector ---
log_dir = "data/logs"
files = sorted(glob.glob(f"{log_dir}/session_*.csv"), reverse=True)

if not files:
    st.warning("No session data found. Run main.py first.")
    st.stop()

selected_file = st.selectbox(
    "Select Session",
    options=files,
    format_func=lambda x: os.path.basename(x)
)

df = pd.read_csv(selected_file)

if df.empty:
    st.warning("Session file is empty.")
    st.stop()

# --- metrics ---
avg_score    = round(df["attention_score"].mean(), 1)
distractions = int((df["state"] == "DISTRACTED").sum())
fatigue_ev   = int((df["fatigue_score"] > 0).sum())
focus_sec    = int((df["state"] == "FOCUSED").sum())
total_sec    = len(df)

focus_pct    = round((focus_sec / total_sec) * 100, 1) if total_sec else 0
distract_pct = round((distractions / total_sec) * 100, 1) if total_sec else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("📊 Avg Score",      f"{avg_score}/100")
col2.metric("✅ Focus Time",     f"{focus_sec // 60}m {focus_sec % 60}s", f"{focus_pct}%")
col3.metric("🔥 Distractions",   distractions,  f"{distract_pct}% of session")
col4.metric("😴 Fatigue Events", fatigue_ev)
col5.metric("⏱ Session Length", f"{total_sec // 60}m {total_sec % 60}s")

st.divider()

# --- attention graph ---
st.subheader("📈 Attention Score Over Time")
chart_df = df[["attention_score", "fatigue_score"]].copy()
chart_df.columns = ["Attention Score", "Fatigue Score"]
st.line_chart(chart_df)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("🧠 State Distribution")
    state_counts = df["state"].value_counts()
    st.bar_chart(state_counts)

with col_b:
    st.subheader("👀 Gaze Distribution")
    gaze_counts = df["gaze"].value_counts()
    st.bar_chart(gaze_counts)

st.divider()

# --- alerts ---
st.subheader("⚠️ Session Alerts")
alerts = []
if avg_score < 50:
    alerts.append("🔴 Low average attention score — consider shorter study sessions.")
if distract_pct > 30:
    alerts.append("🔴 High distraction rate — try removing distractions from environment.")
if fatigue_ev > total_sec * 0.2:
    alerts.append("🟠 Frequent fatigue detected — take regular breaks.")
if focus_pct > 70:
    alerts.append("🟢 Great focus maintained throughout the session!")

if alerts:
    for a in alerts:
        st.write(a)
else:
    st.write("✅ Session looks good!")

st.divider()

# --- analytics engine (used for quality, decay, coach) ---
analytics = AnalyticsEngine(selected_file)
summary   = analytics.get_summary()

# --- session quality + focus decay ---
quality = analytics.session_quality()
decay   = analytics.focus_decay()

col_q1, col_q2 = st.columns(2)
col_q1.metric("🎯 Session Quality Score", f"{quality}/100")
col_q2.write("")
col_q2.write(decay)

st.subheader("🔥 Distraction Timeline")
distraction_data = analytics.distraction_series()
st.line_chart(distraction_data)

st.divider()
st.subheader("🧠 AI Coach Feedback")
coach    = AICoach()
feedback = coach.generate_feedback(summary)
for f in feedback:
    st.write(f)

st.divider()

# --- gamification ---
try:
    focus_min = int(summary["focus_time"].split("m")[0])
except:
    focus_min = 0

game = Gamification()
game.update(summary["avg_score"], focus_minutes=focus_min)
stats  = game.get_stats()
badges = game.get_badges()

st.subheader("🎯 Your Progress")
col_g1, col_g2, col_g3, col_g4 = st.columns(4)
col_g1.metric("🔥 Streak",          f"{stats['streak']} days")
col_g2.metric("📊 Total Sessions",  stats["total_sessions"])
col_g3.metric("🏆 High Score",      f"{stats['high_score']}/100")
col_g4.metric("⏱ Total Focus",     f"{stats.get('total_focus_minutes', 0)} min")

st.subheader("🏅 Achievements")
if badges:
    cols = st.columns(len(badges))
    for i, b in enumerate(badges):
        cols[i].success(b)
else:
    st.info("No badges yet — keep going! 💪")

st.divider()

# --- raw data ---
with st.expander("📄 View Raw Data"):
    st.dataframe(df, use_container_width=True)
