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
    sa_b64 = os.environ.get("GCP_SERVICE_ACCOUNT_B64")
    if sa_b64:
        import json, base64
        info = json.loads(base64.b64decode(sa_b64).decode())
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if sa_json:
        import json
        info = json.loads(sa_json)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    return bigquery.Client(project=PROJECT_ID)


def load_table(table: str) -> pd.DataFrame:
    client = get_client()
    return client.query(f"SELECT * FROM `{PROJECT_ID}.{DATASET}.{table}`").to_dataframe()


# ── helpers ───────────────────────────────────────────────────────────────────
def win_probability(s1: float, s2: float):
    total = s1 + s2
    if total == 0:
        return 0.5, 0.5
    return round(s1 / total, 3), round(1 - s1 / total, 3)


def get_team_stats(standings: pd.DataFrame, team: str):
    row = standings[standings["team"].str.lower() == team.lower()]
    if row.empty:
        row = standings[standings["team"].str.lower().str.contains(team.lower(), na=False)]
    return row.iloc[0] if not row.empty else None


def prob_bar(p: float) -> str:
    filled = int(round(p * 20))
    bar = "█" * filled + "░" * (20 - filled)
    return f"`{bar}` {p*100:.1f}%"


def strength_bar(s: float) -> str:
    filled = int(round(s * 10))
    bar = "🟩" * filled + "⬜" * (10 - filled)
    return bar


def medal(i):
    return ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."


# ── match card HTML ───────────────────────────────────────────────────────────
def match_card_html(matches: list) -> str:
    if not matches:
        return "<p style='color:#888;font-size:1.1em;'>No matches found for this date.</p>"

    html = ""
    for m in matches:
        p1, p2 = m["p1"], m["p2"]
        fav = m["team1"] if p1 >= p2 else m["team2"]
        fav_p = max(p1, p2)
        result_badge = ""
        if m.get("result") and m["result"] not in ("TBD", "", "nan"):
            result_badge = f"<span style='background:#22c55e;color:white;padding:2px 10px;border-radius:12px;font-weight:bold;margin-left:8px;'>✅ {m['result']}</span>"

        pct1 = int(p1 * 100)
        pct2 = int(p2 * 100)
        color1 = "#3b82f6" if p1 >= p2 else "#94a3b8"
        color2 = "#3b82f6" if p2 > p1 else "#94a3b8"

        bar_html = f"""
        <div style="display:flex;align-items:center;gap:6px;margin:8px 0;">
          <span style="width:120px;text-align:right;font-weight:600;font-size:0.95em;">{m['team1']}</span>
          <div style="flex:1;background:#e2e8f0;border-radius:8px;height:22px;overflow:hidden;display:flex;">
            <div style="width:{pct1}%;background:{color1};display:flex;align-items:center;justify-content:center;color:white;font-size:0.8em;font-weight:bold;transition:width 0.5s;">
              {''+str(pct1)+'%' if pct1 > 12 else ''}
            </div>
            <div style="width:{pct2}%;background:{color2};display:flex;align-items:center;justify-content:center;color:white;font-size:0.8em;font-weight:bold;">
              {''+str(pct2)+'%' if pct2 > 12 else ''}
            </div>
          </div>
          <span style="width:120px;font-weight:600;font-size:0.95em;">{m['team2']}</span>
        </div>"""

        nyc_html = ""
        if m.get("bars1") and str(m["bars1"]) not in ("", "nan", "—"):
            nyc_html += f"<div style='margin-top:4px;font-size:0.82em;color:#475569;'>🍺 <b>{m['team1']}:</b> {m['bars1']}</div>"
        if m.get("bars2") and str(m["bars2"]) not in ("", "nan", "—"):
            nyc_html += f"<div style='font-size:0.82em;color:#475569;'>🍺 <b>{m['team2']}:</b> {m['bars2']}</div>"

        html += f"""
        <div style="border:1px solid #e2e8f0;border-radius:14px;padding:18px 22px;margin-bottom:18px;background:white;box-shadow:0 1px 4px rgba(0,0,0,0.07);">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
            <span style="background:#f1f5f9;color:#334155;padding:3px 12px;border-radius:20px;font-size:0.85em;font-weight:600;">⏰ {m['kickoff']} ET</span>
            <span style="background:#dbeafe;color:#1d4ed8;padding:3px 12px;border-radius:20px;font-size:0.85em;font-weight:600;">{m['stage']}</span>
            {result_badge}
          </div>
          <div style="font-size:1.25em;font-weight:700;margin-bottom:10px;color:#1e293b;">
            ⚽ {m['team1']} <span style="color:#94a3b8;font-weight:400;">vs</span> {m['team2']}
          </div>
          {bar_html}
          <div style="margin-top:10px;padding:10px 14px;background:#f0fdf4;border-radius:8px;border-left:4px solid #22c55e;">
            🤖 <b>Predicted winner:</b> <span style="color:#15803d;font-weight:700;">{fav}</span>
            <span style="color:#64748b;"> — {fav_p*100:.1f}% win probability based on goals scored, wins & tournament form</span>
          </div>
          <div style="margin-top:8px;font-size:0.85em;color:#64748b;">📍 {m['venue']} · {m['host_city']}</div>
          {nyc_html}
        </div>"""
    return html


# ── predictions HTML ──────────────────────────────────────────────────────────
def predictions_html(qualified: pd.DataFrame) -> str:
    html = "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;'>"
    colors = ["#fef9c3", "#f1f5f9", "#fef3c7"] + ["#f8fafc"] * 20
    for i, (_, r) in enumerate(qualified.head(16).iterrows()):
        s = float(r["strength_score"])
        bar = int(s * 10)
        bar_html = "🟩" * bar + "⬜" * (10 - bar)
        border = "#eab308" if i == 0 else "#cbd5e1"
        html += f"""
        <div style="border:2px solid {border};border-radius:12px;padding:14px;background:{colors[i]};">
          <div style="font-size:1.1em;font-weight:700;">{medal(i)} {r['team']}</div>
          <div style="font-size:0.8em;color:#64748b;margin:4px 0;">Group {r['group_letter']} · {r['points']} pts · {r['goals_for']} goals scored</div>
          <div style="font-size:1.1em;margin:6px 0;" title="Strength score">{bar_html}</div>
          <div style="display:flex;gap:8px;font-size:0.8em;flex-wrap:wrap;">
            <span style="background:#dcfce7;padding:2px 8px;border-radius:10px;">✅ {r['won']}W</span>
            <span style="background:#fef9c3;padding:2px 8px;border-radius:10px;">🟡 {r['drawn']}D</span>
            <span style="background:#fee2e2;padding:2px 8px;border-radius:10px;">❌ {r['lost']}L</span>
            <span style="background:#dbeafe;padding:2px 8px;border-radius:10px;">⚡ {float(r['goals_per_game']):.1f} g/game</span>
          </div>
          <div style="margin-top:8px;font-size:0.8em;color:#475569;">Strength: <b>{s:.3f}</b></div>
        </div>"""
    html += "</div>"
    return html


# ── schedule HTML ─────────────────────────────────────────────────────────────
def schedule_html(ko: pd.DataFrame) -> str:
    ko = ko.copy()
    ko["match_date"] = pd.to_datetime(ko["match_date"], errors="coerce")
    ko = ko.sort_values("match_date")
    today = date.today()

    html = ""
    current_round = None
    for _, r in ko.iterrows():
        rnd = str(r.get("stage", r.get("round", "")))
        if rnd != current_round:
            current_round = rnd
            html += f"<h3 style='margin:18px 0 8px;color:#1e293b;border-bottom:2px solid #3b82f6;padding-bottom:4px;'>{rnd}</h3>"
        d = r["match_date"]
        is_today = hasattr(d, "date") and d.date() == today
        bg = "#eff6ff" if is_today else "white"
        border = "#3b82f6" if is_today else "#e2e8f0"
        today_tag = " 🔴 TODAY" if is_today else ""
        date_str = d.strftime("%a, %b %d") if pd.notna(d) else "TBD"
        html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;margin:4px 0;background:{bg};border:1px solid {border};border-radius:8px;">
          <span style="min-width:110px;font-size:0.85em;color:#64748b;">{date_str}{today_tag}</span>
          <span style="font-weight:600;flex:1;">{r.get('matchup','TBD')}</span>
          <span style="font-size:0.82em;color:#64748b;">{r.get('kickoff_et','')}</span>
          <span style="font-size:0.78em;color:#94a3b8;min-width:120px;text-align:right;">{r.get('host_city','')}</span>
        </div>"""
    return html


# ── bars HTML ─────────────────────────────────────────────────────────────────
def bars_html(bars: pd.DataFrame) -> str:
    html = "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;'>"
    for _, r in bars.iterrows():
        country = str(r.get("country", r.get("Country", "")))
        spots = str(r.get("nyc_bars", r.get("NYC Viewing Spots", "")))
        is_generic = "multi-nation" in spots.lower() or "Football Factory" in spots
        bg = "#f8fafc" if is_generic else "white"
        border = "#e2e8f0" if is_generic else "#3b82f6"
        html += f"""
        <div style="border:1px solid {border};border-radius:10px;padding:12px;background:{bg};">
          <div style="font-weight:700;margin-bottom:4px;">🏳️ {country}</div>
          <div style="font-size:0.82em;color:#475569;">🍺 {spots}</div>
        </div>"""
    html += "</div>"
    return html


# ── data loaders ──────────────────────────────────────────────────────────────
def load_games(view_date):
    if isinstance(view_date, str):
        view_date = date.fromisoformat(str(view_date)[:10])
    elif hasattr(view_date, "date"):
        view_date = view_date.date()

    gs = load_table("group_stage_matches")
    ko = load_table("knockout_matches")
    standings = load_table("team_standings")
    bars_df = load_table("nyc_bars")

    gs["match_date"] = pd.to_datetime(gs["match_date"], errors="coerce").dt.date
    ko["match_date"] = pd.to_datetime(ko["match_date"], errors="coerce").dt.date

    today_gs = gs[gs["match_date"] == view_date]
    today_ko = ko[ko["match_date"] == view_date]

    matches = []
    for _, r in today_gs.iterrows():
        t1, t2 = str(r.get("team1", "")), str(r.get("team2", ""))
        s1 = get_team_stats(standings, t1)
        s2 = get_team_stats(standings, t2)
        sc1 = float(s1["strength_score"]) if s1 is not None else 0.5
        sc2 = float(s2["strength_score"]) if s2 is not None else 0.5
        p1, p2 = win_probability(sc1, sc2)
        matches.append({
            "kickoff": r.get("kickoff_et", ""), "stage": f"Group {r.get('group_letter','')}",
            "team1": t1, "team2": t2, "p1": p1, "p2": p2,
            "result": str(r.get("result", "TBD")),
            "venue": r.get("venue", ""), "host_city": r.get("host_city", ""),
            "bars1": r.get("nyc_bars_team1", ""), "bars2": r.get("nyc_bars_team2", ""),
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
        b1 = bars_df[bars_df["country"].str.lower() == t1.lower()]
        b2 = bars_df[bars_df["country"].str.lower() == t2.lower()]
        matches.append({
            "kickoff": r.get("kickoff_et", ""), "stage": r.get("stage", "Knockout"),
            "team1": t1, "team2": t2, "p1": p1, "p2": p2, "result": "TBD",
            "venue": r.get("venue", ""), "host_city": r.get("host_city", ""),
            "bars1": b1.iloc[0]["nyc_bars"] if not b1.empty else "—",
            "bars2": b2.iloc[0]["nyc_bars"] if not b2.empty else "—",
        })

    header = f"<h2 style='color:#1e293b;margin-bottom:4px;'>⚽ {len(matches)} match(es) on {view_date.strftime('%A, %B %d, %Y')}</h2>"
    if not matches:
        header += "<p style='color:#64748b;'>No games scheduled. Try another date.</p>"
    return header + match_card_html(sorted(matches, key=lambda x: x["kickoff"]))


def load_standings():
    standings = load_table("team_standings")
    standings = standings.sort_values(["group_letter", "points"], ascending=[True, False])
    html = ""
    for grp in sorted(standings["group_letter"].dropna().unique()):
        grp_df = standings[standings["group_letter"] == grp]
        html += f"<h3 style='margin:16px 0 6px;color:#1d4ed8;'>Group {grp}</h3>"
        html += "<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:0.88em;'>"
        html += "<tr style='background:#f1f5f9;'><th style='padding:8px;text-align:left;'>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th><th>Strength</th><th>Status</th></tr>"
        for i, (_, r) in enumerate(grp_df.iterrows()):
            bg = "#f0fdf4" if i == 0 else "#eff6ff" if i == 1 else "white"
            s = float(r["strength_score"])
            bar = "🟩" * int(s * 8) + "⬜" * (8 - int(s * 8))
            status_color = "#15803d" if "qualified" in str(r["status"]).lower() or "Won" in str(r["status"]) else "#b45309" if "3rd" in str(r["status"]) else "#dc2626"
            html += f"<tr style='background:{bg};border-bottom:1px solid #e2e8f0;'>"
            html += f"<td style='padding:8px;font-weight:600;'>{r['team']}</td>"
            for col in ["played", "won", "drawn", "lost", "goals_for", "goals_against", "goal_diff_num", "points"]:
                html += f"<td style='padding:8px;text-align:center;'>{r[col]}</td>"
            html += f"<td style='padding:8px;text-align:center;' title='{s:.3f}'>{bar}</td>"
            html += f"<td style='padding:8px;font-size:0.8em;color:{status_color};'>{r['status']}</td>"
            html += "</tr>"
        html += "</table></div>"
    return html


def load_predictions():
    standings = load_table("team_standings")
    qualified = standings[
        standings["status"].str.contains("qualified|Won group|2nd|best-3rd", case=False, na=False)
    ].sort_values("strength_score", ascending=False).reset_index(drop=True)
    header = """<div style='margin-bottom:16px;'>
    <h2 style='color:#1e293b;margin-bottom:4px;'>🏆 Tournament Favourites</h2>
    <p style='color:#64748b;font-size:0.88em;'>Strength Score = 45% win rate + 30% goals/game + 15% defense + 10% points efficiency</p>
    </div>"""
    return header + predictions_html(qualified)


def load_schedule():
    ko = load_table("knockout_matches")
    header = "<h2 style='color:#1e293b;margin-bottom:4px;'>📅 Full Knockout Schedule</h2>"
    return header + schedule_html(ko)


def load_bars():
    bars = load_table("nyc_bars")
    header = "<h2 style='color:#1e293b;margin-bottom:12px;'>🗽 NYC Supporter Bars by Country</h2>"
    return header + bars_html(bars)


# ── gradio app ────────────────────────────────────────────────────────────────
CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.gradio-container { max-width: 1100px !important; }
"""

with gr.Blocks(title="⚽ FIFA 2026 NYC Dashboard", css=CSS) as app:
    gr.HTML("""
    <div style="background:linear-gradient(135deg,#1d4ed8,#059669);padding:24px 28px;border-radius:14px;margin-bottom:16px;color:white;">
      <h1 style="margin:0;font-size:1.8em;">⚽ FIFA 2026 World Cup · NYC Dashboard</h1>
      <p style="margin:6px 0 0;opacity:0.85;">Live scores · Group standings · AI win predictions · NYC viewing spots</p>
    </div>
    """)

    with gr.Tabs():

        # ── Tab 1: Today's Games ──────────────────────────────────────────────
        with gr.TabItem("🗓️ Today's Games"):
            with gr.Row():
                date_input = gr.DateTime(
                    label="Select date",
                    value=str(date.today()),
                    include_time=False,
                )
                load_btn = gr.Button("🔄 Load Games", variant="primary", scale=0)
            games_html = gr.HTML()
            load_btn.click(fn=load_games, inputs=date_input, outputs=games_html)
            app.load(fn=lambda: load_games(date.today()), outputs=games_html)

        # ── Tab 2: Standings ──────────────────────────────────────────────────
        with gr.TabItem("📊 Group Standings"):
            standings_btn = gr.Button("🔄 Refresh", variant="primary", scale=0)
            standings_html = gr.HTML()
            standings_btn.click(fn=load_standings, outputs=standings_html)
            app.load(fn=load_standings, outputs=standings_html)

        # ── Tab 3: Predictions ────────────────────────────────────────────────
        with gr.TabItem("🏆 Predictions"):
            pred_btn = gr.Button("🔄 Refresh", variant="primary", scale=0)
            pred_html = gr.HTML()
            pred_btn.click(fn=load_predictions, outputs=pred_html)
            app.load(fn=load_predictions, outputs=pred_html)

        # ── Tab 4: Full Schedule ──────────────────────────────────────────────
        with gr.TabItem("📅 Full Schedule"):
            sched_btn = gr.Button("🔄 Refresh", variant="primary", scale=0)
            sched_html = gr.HTML()
            sched_btn.click(fn=load_schedule, outputs=sched_html)
            app.load(fn=load_schedule, outputs=sched_html)

        # ── Tab 5: NYC Bars ───────────────────────────────────────────────────
        with gr.TabItem("🗽 NYC Bars"):
            bars_btn = gr.Button("🔄 Refresh", variant="primary", scale=0)
            bars_html_out = gr.HTML()
            bars_btn.click(fn=load_bars, outputs=bars_html_out)
            app.load(fn=load_bars, outputs=bars_html_out)

    gr.HTML("<div style='text-align:center;color:#94a3b8;font-size:0.8em;margin-top:12px;'>📡 Live data from BigQuery · proud-sweep-323918.fifa_2026 · Refreshes on page load</div>")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=True,
        share=False,
    )
