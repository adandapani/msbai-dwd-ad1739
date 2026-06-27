"""FIFA 2026 World Cup Dashboard — Today's Games, Standings & Win Predictions."""

import os
from datetime import date, datetime

import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FIFA 2026 · NYC Dashboard",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT_ID = "proud-sweep-323918"
DATASET = "fifa_2026"

# ── auth ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    """Return a BigQuery client using Streamlit secrets or env credentials."""
    if "gcp_service_account" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/credentials.json")
    return bigquery.Client(project=PROJECT_ID)


@st.cache_data(ttl=3600)
def load_table(table: str) -> pd.DataFrame:
    client = get_client()
    return client.query(f"SELECT * FROM `{PROJECT_ID}.{DATASET}.{table}`").to_dataframe()


# ── helpers ───────────────────────────────────────────────────────────────────
def prediction_label(score: float) -> str:
    if score >= 0.70:
        return "🟢 Strong Favorite"
    if score >= 0.50:
        return "🟡 Slight Favorite"
    return "🔴 Underdog"


def win_probability(t1_score: float, t2_score: float):
    """Convert strength scores to win probabilities (softmax-style)."""
    total = t1_score + t2_score
    if total == 0:
        return 0.5, 0.5
    p1 = t1_score / total
    return round(p1, 3), round(1 - p1, 3)


def get_team_stats(standings: pd.DataFrame, team: str) -> pd.Series | None:
    row = standings[standings["team"].str.lower() == team.lower()]
    if row.empty:
        # fuzzy: check if team name contains the search term
        row = standings[standings["team"].str.lower().str.contains(team.lower(), na=False)]
    return row.iloc[0] if not row.empty else None


# ── sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/en/thumb/e/e3/2026_FIFA_World_Cup.svg/200px-2026_FIFA_World_Cup.svg.png",
    width=120,
)
st.sidebar.title("FIFA 2026 · NYC")
today_override = st.sidebar.date_input("View date", value=date.today())
st.sidebar.markdown("---")
st.sidebar.caption(f"Data refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
st.sidebar.caption("Source: BigQuery · `proud-sweep-323918.fifa_2026`")

# ── load data ─────────────────────────────────────────────────────────────────
try:
    gs = load_table("group_stage_matches")
    ko = load_table("knockout_matches")
    standings = load_table("team_standings")
    bars_df = load_table("nyc_bars")
except Exception as e:
    st.error(f"Could not connect to BigQuery: {e}")
    st.stop()

# Normalise date columns
gs["match_date"] = pd.to_datetime(gs["match_date"], errors="coerce").dt.date
ko["match_date"] = pd.to_datetime(ko["match_date"], errors="coerce").dt.date

view_date = today_override

# ── header ────────────────────────────────────────────────────────────────────
st.title(f"⚽ FIFA 2026 World Cup — {view_date.strftime('%A, %B %d, %Y')}")
st.markdown("**NYC viewing guide · live standings · AI win predictions**")
st.markdown("---")

# ── TODAY'S MATCHES ───────────────────────────────────────────────────────────
today_gs = gs[gs["match_date"] == view_date].copy()
today_ko = ko[ko["match_date"] == view_date].copy()
has_games = not today_gs.empty or not today_ko.empty

if not has_games:
    st.info(f"No matches scheduled on {view_date}. Use the sidebar to pick another date.")
else:
    st.header("🗓️ Today's Matches & Predictions")

    all_today = []

    # --- group stage games ---
    for _, row in today_gs.iterrows():
        t1 = str(row.get("team1", ""))
        t2 = str(row.get("team2", ""))
        s1 = get_team_stats(standings, t1)
        s2 = get_team_stats(standings, t2)

        score1 = s1["strength_score"] if s1 is not None else 0.5
        score2 = s2["strength_score"] if s2 is not None else 0.5
        p1, p2 = win_probability(score1, score2)

        all_today.append({
            "kickoff": row.get("kickoff_et", "TBD"),
            "stage": row.get("stage", "Group Stage"),
            "group": row.get("group_letter", ""),
            "matchup": row.get("matchup", ""),
            "team1": t1,
            "team2": t2,
            "result": row.get("result", ""),
            "venue": row.get("venue", ""),
            "host_city": row.get("host_city", ""),
            "p1": p1, "p2": p2,
            "score1": score1, "score2": score2,
            "nyc_bars_t1": row.get("nyc_bars_team1", ""),
            "nyc_bars_t2": row.get("nyc_bars_team2", ""),
        })

    # --- knockout games ---
    for _, row in today_ko.iterrows():
        parts = str(row.get("matchup", "")).split(" vs ", 1)
        t1 = parts[0].strip() if len(parts) > 1 else row.get("matchup", "TBD")
        t2 = parts[1].strip() if len(parts) > 1 else ""
        s1 = get_team_stats(standings, t1)
        s2 = get_team_stats(standings, t2)
        score1 = s1["strength_score"] if s1 is not None else 0.5
        score2 = s2["strength_score"] if s2 is not None else 0.5
        p1, p2 = win_probability(score1, score2)

        # Look up bars
        b1 = bars_df[bars_df["country"].str.lower() == t1.lower()]
        b2 = bars_df[bars_df["country"].str.lower() == t2.lower()]

        all_today.append({
            "kickoff": row.get("kickoff_et", "TBD"),
            "stage": row.get("stage", "Knockout"),
            "group": row.get("match_number", ""),
            "matchup": row.get("matchup", ""),
            "team1": t1,
            "team2": t2,
            "result": "",
            "venue": row.get("venue", ""),
            "host_city": row.get("host_city", ""),
            "p1": p1, "p2": p2,
            "score1": score1, "score2": score2,
            "nyc_bars_t1": b1.iloc[0]["nyc_bars"] if not b1.empty else "See sidebar",
            "nyc_bars_t2": b2.iloc[0]["nyc_bars"] if not b2.empty else "See sidebar",
        })

    for m in sorted(all_today, key=lambda x: x["kickoff"]):
        with st.container():
            stage_tag = f"{m['stage']}" + (f" · Group {m['group']}" if m['group'] and len(m['group']) == 1 else f" · {m['group']}" if m['group'] else "")
            st.markdown(f"### {m['kickoff']} ET &nbsp;|&nbsp; {stage_tag}")

            col1, col_vs, col2 = st.columns([4, 1, 4])

            with col1:
                st.markdown(f"## 🏳️ {m['team1']}")
                st.metric("Win Probability", f"{m['p1']*100:.1f}%")
                st.caption(prediction_label(m['score1']))
                if m['nyc_bars_t1']:
                    st.markdown(f"🍺 **NYC Bars:** {m['nyc_bars_t1']}")

            with col_vs:
                st.markdown("<h2 style='text-align:center;'>VS</h2>", unsafe_allow_html=True)
                if m['result']:
                    st.markdown(f"<h3 style='text-align:center;color:green'>{m['result']}</h3>", unsafe_allow_html=True)

            with col2:
                st.markdown(f"## 🏳️ {m['team2']}")
                st.metric("Win Probability", f"{m['p2']*100:.1f}%")
                st.caption(prediction_label(m['score2']))
                if m['nyc_bars_t2']:
                    st.markdown(f"🍺 **NYC Bars:** {m['nyc_bars_t2']}")

            # Prediction call-out
            if m['score1'] != m['score2']:
                fav = m['team1'] if m['score1'] > m['score2'] else m['team2']
                fav_p = max(m['p1'], m['p2'])
                st.success(f"🤖 **Prediction:** {fav} wins with **{fav_p*100:.1f}%** probability based on goals scored, wins & tournament form.")
            else:
                st.warning("🤖 **Prediction:** Even matchup — could go either way.")

            st.caption(f"📍 {m['venue']} · {m['host_city']}")
            st.markdown("---")

# ── STANDINGS TABLE ───────────────────────────────────────────────────────────
st.header("📊 Group Standings & Strength Scores")

tab_groups = standings["group_letter"].dropna().unique()
tab_groups = sorted([g for g in tab_groups if len(str(g)) == 1])

tabs = st.tabs([f"Group {g}" for g in tab_groups])
for tab, grp in zip(tabs, tab_groups):
    with tab:
        grp_df = standings[standings["group_letter"] == grp].copy()
        grp_df = grp_df.sort_values("points", ascending=False)

        display = grp_df[[
            "team", "played", "won", "drawn", "lost",
            "goals_for", "goals_against", "goal_diff_num",
            "points", "win_rate", "goals_per_game", "strength_score", "status",
        ]].copy()

        display.columns = [
            "Team", "P", "W", "D", "L", "GF", "GA", "GD",
            "Pts", "Win%", "G/Game", "Strength", "Status",
        ]
        display["Win%"] = (display["Win%"] * 100).round(1).astype(str) + "%"
        display["G/Game"] = display["G/Game"].round(2)
        display["Strength"] = display["Strength"].round(3)

        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
        )

# ── OVERALL PREDICTIONS ───────────────────────────────────────────────────────
st.header("🏆 Tournament Favourites — Prediction Rankings")
st.caption("Ranked by Strength Score = 45% win rate + 30% goals per game + 15% defense + 10% points efficiency")

top = standings[standings["status"].str.contains("qualified|Won group|2nd|best-3rd", case=False, na=False)].copy()
top = top.sort_values("strength_score", ascending=False).head(20)

top_display = top[[
    "team", "group_letter", "points", "goals_for", "goals_against",
    "win_rate", "goals_per_game", "strength_score", "status",
]].copy()
top_display.columns = ["Team", "Grp", "Pts", "GF", "GA", "Win%", "G/Game", "Strength Score", "Status"]
top_display["Win%"] = (top_display["Win%"] * 100).round(1).astype(str) + "%"
top_display["G/Game"] = top_display["G/Game"].round(2)
top_display["Strength Score"] = top_display["Strength Score"].round(3)

st.dataframe(top_display, hide_index=True, use_container_width=True)

# Podium
col1, col2, col3 = st.columns(3)
podium = top.head(3)
medals = ["🥇", "🥈", "🥉"]
for col, (_, row), medal in zip([col1, col2, col3], podium.iterrows(), medals):
    with col:
        st.metric(
            f"{medal} {row['team']}",
            f"Score: {row['strength_score']:.3f}",
            f"{row['goals_for']} goals · {row['won']}W/{row['drawn']}D/{row['lost']}L",
        )

# ── NYC VIEWING SPOTS ─────────────────────────────────────────────────────────
st.header("🗽 NYC Viewing Spots — Free Fan Zones")
fan_zones = {
    "Brooklyn Bridge Park": "Brooklyn · Jun 13–Jul 19 · Daily screenings over the skyline",
    "USTA Billie Jean King Tennis Center": "Flushing, Queens · Jun 11–Jun 27 · Largest fan zone",
    "Rockefeller Center Fan Village": "Midtown Manhattan · Jul 6–Jul 19 · NYNJ World Cup 26 & Telemundo",
    "Central Park Great Lawn": "Manhattan · Jul 19 (Final only) · Up to 50,000 via Global Citizen lottery",
    "Times Square": "Midtown · Jul 18–Jul 19 · Final + third-place on FIFA big screens",
}
for venue, info in fan_zones.items():
    st.markdown(f"- **{venue}** — {info}")

st.markdown("---")
st.caption("Dashboard auto-refreshes BigQuery data every hour. Data source: FIFA 2026 official schedule.")
