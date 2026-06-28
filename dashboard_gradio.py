"""FIFA 2026 World Cup Dashboard — Gradio version with BigQuery backend."""

import os
from datetime import date

import gradio as gr
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "proud-sweep-323918"
DATASET = "fifa_2026"

# ── auth ──────────────────────────────────────────────────────────────────────
def get_client():
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_path and os.path.exists(key_path):
        return bigquery.Client(project=PROJECT_ID)
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if sa_json:
        import json
        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    return bigquery.Client(project=PROJECT_ID)


def load_table(table: str) -> pd.DataFrame:
    client = get_client()
    return client.query(f"SELECT * FROM `{PROJECT_ID}.{DATASET}.{table}`").to_dataframe()


# ── prediction helpers ────────────────────────────────────────────────────────
def win_probability(s1: float, s2: float):
    total = s1 + s2
    if total == 0:
        return 0.5, 0.5
    return round(s1 / total, 3), round(s2 / total, 3)


def get_team_stats(standings: pd.DataFrame, team: str):
    row = standings[standings["team"].str.lower() == team.lower()]
    if row.empty:
        row = standings[standings["team"].str.lower().str.contains(team.lower(), na=False)]
    return row.iloc[0] if not row.empty else None


def medal(i):
    return ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."


# ── tab builders ──────────────────────────────────────────────────────────────
def build_todays_games(view_date: date):
    gs = load_table("group_stage_matches")
    ko = load_table("knockout_matches")
    standings = load_table("team_standings")
    bars_df = load_table("nyc_bars")

    gs["match_date"] = pd.to_datetime(gs["match_date"], errors="coerce").dt.date
    ko["match_date"] = pd.to_datetime(ko["match_date"], errors="coerce").dt.date

    today_gs = gs[gs["match_date"] == view_date]
    today_ko = ko[ko["match_date"] == view_date]

    if today_gs.empty and today_ko.empty:
        return f"## No matches scheduled on {view_date}\nPick another date in the sidebar.", pd.DataFrame()

    rows = []

    for _, r in today_gs.iterrows():
        t1, t2 = str(r.get("team1", "")), str(r.get("team2", ""))
        s1 = get_team_stats(standings, t1)
        s2 = get_team_stats(standings, t2)
        sc1 = float(s1["strength_score"]) if s1 is not None else 0.5
        sc2 = float(s2["strength_score"]) if s2 is not None else 0.5
        p1, p2 = win_probability(sc1, sc2)
        fav = t1 if p1 >= p2 else t2
        fav_p = max(p1, p2)
        rows.append({
            "Kickoff (ET)": r.get("kickoff_et", ""),
            "Stage": f"Group {r.get('group_letter','')}",
            "Team 1": t1,
            "Team 2": t2,
            "Result": r.get("result", "TBD"),
            "T1 Win%": f"{p1*100:.1f}%",
            "T2 Win%": f"{p2*100:.1f}%",
            "🤖 Predicted Winner": f"{fav} ({fav_p*100:.1f}%)",
            "Venue": r.get("venue", ""),
            "NYC Bars T1": r.get("nyc_bars_team1", ""),
            "NYC Bars T2": r.get("nyc_bars_team2", ""),
        })

    for _, r in today_ko.iterrows():
        matchup = str(r.get("matchup", ""))
        parts = matchup.split(" vs ", 1)
        t1 = parts[0].strip()
        t2 = parts[1].strip() if len(parts) > 1 else ""
        s1 = get_team_stats(standings, t1)
        s2 = get_team_stats(standings, t2)
        sc1 = float(s1["strength_score"]) if s1 is not None else 0.5
        sc2 = float(s2["strength_score"]) if s2 is not None else 0.5
        p1, p2 = win_probability(sc1, sc2)
        fav = t1 if p1 >= p2 else t2
        fav_p = max(p1, p2)
        b1 = bars_df[bars_df["country"].str.lower() == t1.lower()]
        b2 = bars_df[bars_df["country"].str.lower() == t2.lower()]
        rows.append({
            "Kickoff (ET)": r.get("kickoff_et", ""),
            "Stage": r.get("stage", "Knockout"),
            "Team 1": t1,
            "Team 2": t2,
            "Result": "TBD",
            "T1 Win%": f"{p1*100:.1f}%",
            "T2 Win%": f"{p2*100:.1f}%",
            "🤖 Predicted Winner": f"{fav} ({fav_p*100:.1f}%)",
            "Venue": r.get("venue", ""),
            "NYC Bars T1": b1.iloc[0]["nyc_bars"] if not b1.empty else "—",
            "NYC Bars T2": b2.iloc[0]["nyc_bars"] if not b2.empty else "—",
        })

    df = pd.DataFrame(rows).sort_values("Kickoff (ET)")
    summary = f"## ⚽ {len(df)} match(es) on {view_date.strftime('%A, %B %d, %Y')}\n"
    for _, r in df.iterrows():
        summary += f"\n**{r['Kickoff (ET)']} ET** · {r['Stage']}  \n"
        summary += f"🏳️ **{r['Team 1']}** {r['T1 Win%']} vs **{r['Team 2']}** {r['T2 Win%']}  \n"
        summary += f"🤖 Prediction: **{r['🤖 Predicted Winner']}**  \n"
        if r["Result"] not in ("TBD", ""):
            summary += f"✅ Result: **{r['Result']}**  \n"
        summary += f"📍 {r['Venue']}  \n---\n"

    return summary, df


def build_standings():
    standings = load_table("team_standings")
    standings = standings.sort_values(["group_letter", "points"], ascending=[True, False])
    display = standings[[
        "group_letter", "team", "played", "won", "drawn", "lost",
        "goals_for", "goals_against", "goal_diff_num", "points",
        "win_rate", "goals_per_game", "strength_score", "status",
    ]].copy()
    display.columns = [
        "Group", "Team", "P", "W", "D", "L", "GF", "GA", "GD",
        "Pts", "Win%", "G/Game", "Strength", "Status",
    ]
    display["Win%"] = (display["Win%"] * 100).round(1).astype(str) + "%"
    display["G/Game"] = display["G/Game"].round(2)
    display["Strength"] = display["Strength"].round(3)
    return display


def build_predictions():
    standings = load_table("team_standings")
    qualified = standings[
        standings["status"].str.contains("qualified|Won group|2nd|best-3rd", case=False, na=False)
    ].copy()
    qualified = qualified.sort_values("strength_score", ascending=False).reset_index(drop=True)

    md = "## 🏆 Tournament Favourites\n"
    md += "_Strength Score = 45% win rate + 30% goals/game + 15% defense + 10% points efficiency_\n\n"
    for i, (_, r) in enumerate(qualified.head(10).iterrows()):
        md += f"{medal(i)} **{r['team']}** (Group {r['group_letter']})  \n"
        md += f"   Score: `{r['strength_score']:.3f}` · {r['goals_for']} goals · {r['won']}W/{r['drawn']}D/{r['lost']}L · {r['points']} pts  \n\n"

    display = qualified[[
        "team", "group_letter", "points", "goals_for", "goals_against",
        "win_rate", "goals_per_game", "strength_score", "status",
    ]].head(20).copy()
    display.columns = ["Team", "Grp", "Pts", "GF", "GA", "Win%", "G/Game", "Strength Score", "Status"]
    display["Win%"] = (display["Win%"] * 100).round(1).astype(str) + "%"
    display["G/Game"] = display["G/Game"].round(2)
    display["Strength Score"] = display["Strength Score"].round(3)
    return md, display


def build_nyc_bars():
    bars = load_table("nyc_bars")
    return bars.rename(columns={"country": "Country", "nyc_bars": "NYC Viewing Spots"})


# ── gradio app ────────────────────────────────────────────────────────────────
with gr.Blocks(title="⚽ FIFA 2026 NYC Dashboard") as app:
    gr.Markdown("""
    # ⚽ FIFA 2026 World Cup · NYC Dashboard
    **Today's games · Standings · Win predictions · NYC bars**
    """)

    with gr.Tabs():

        # ── Tab 1: Today's Games ──────────────────────────────────────────────
        with gr.TabItem("🗓️ Today's Games & Predictions"):
            with gr.Row():
                date_input = gr.DateTime(
                    label="View date",
                    value=str(date.today()),
                    include_time=False,
                )
                refresh_btn = gr.Button("🔄 Load Games", variant="primary")

            games_md = gr.Markdown()
            games_table = gr.Dataframe(
                label="Match Details",
                wrap=True,
                interactive=False,
            )

            def on_load_games(d):
                if isinstance(d, str):
                    d = date.fromisoformat(d[:10])
                elif hasattr(d, "date"):
                    d = d.date()
                return build_todays_games(d)

            refresh_btn.click(
                fn=on_load_games,
                inputs=date_input,
                outputs=[games_md, games_table],
            )
            app.load(
                fn=lambda: build_todays_games(date.today()),
                outputs=[games_md, games_table],
            )

        # ── Tab 2: Standings ──────────────────────────────────────────────────
        with gr.TabItem("📊 Group Standings"):
            standings_btn = gr.Button("🔄 Load Standings", variant="primary")
            standings_table = gr.Dataframe(
                label="All Groups — sorted by points",
                wrap=True,
                interactive=False,
            )
            standings_btn.click(fn=build_standings, outputs=standings_table)
            app.load(fn=build_standings, outputs=standings_table)

        # ── Tab 3: Predictions ────────────────────────────────────────────────
        with gr.TabItem("🏆 Tournament Predictions"):
            pred_btn = gr.Button("🔄 Refresh Predictions", variant="primary")
            pred_md = gr.Markdown()
            pred_table = gr.Dataframe(
                label="Top 20 Contenders",
                wrap=True,
                interactive=False,
            )
            pred_btn.click(fn=build_predictions, outputs=[pred_md, pred_table])
            app.load(fn=build_predictions, outputs=[pred_md, pred_table])

        # ── Tab 4: NYC Bars ───────────────────────────────────────────────────
        with gr.TabItem("🗽 NYC Viewing Spots"):
            bars_btn = gr.Button("🔄 Load Bars", variant="primary")
            bars_table = gr.Dataframe(
                label="NYC Supporter Bars by Country",
                wrap=True,
                interactive=False,
            )
            bars_btn.click(fn=build_nyc_bars, outputs=bars_table)
            app.load(fn=build_nyc_bars, outputs=bars_table)

    gr.Markdown("""
    ---
    📡 Data: BigQuery `proud-sweep-323918.fifa_2026` · Refreshes on page load
    """)

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft())
