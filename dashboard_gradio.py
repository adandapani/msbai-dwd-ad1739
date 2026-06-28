"""FIFA 2026 World Cup Dashboard — Gradio version with BigQuery backend."""

import os
import re
import zoneinfo
from datetime import date, datetime, timezone

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


# ── email capture ─────────────────────────────────────────────────────────────
LEADS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_leads.csv")

def save_email(name: str, email: str) -> str:
    import csv
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return "⚠️ Please enter a valid email address."
    try:
        write_header = not os.path.exists(LEADS_FILE)
        with open(LEADS_FILE, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["email", "name", "submitted_at"])
            w.writerow([email, name, datetime.now(timezone.utc).isoformat()])
        return f"✅ Thanks {name or 'there'}! You're subscribed for FIFA 2026 updates."
    except Exception as e:
        return f"❌ Could not save: {e}"


# ── search ────────────────────────────────────────────────────────────────────
def do_search(query: str, user_email: str = "") -> str:
    query = (query or "").strip()
    if not query or len(query) < 2:
        return "<p style='color:#94a3b8;padding:12px;'>Type at least 2 characters to search.</p>"

    q = query.lower()
    results = []

    try:
        gs = load_table("group_stage_matches")
        ko = load_table("knockout_matches")
        standings = load_table("team_standings")
        bars = load_table("nyc_bars")

        # Search group stage matches
        for _, r in gs.iterrows():
            matchup = str(r.get("matchup", ""))
            venue = str(r.get("venue", ""))
            host = str(r.get("host_city", ""))
            if q in matchup.lower() or q in venue.lower() or q in host.lower():
                result_str = f" — Result: <b>{r['result']}</b>" if str(r.get("result", "")) not in ("", "nan") else ""
                results.append(("⚽ Match", f"{matchup}{result_str}", f"{r.get('match_date','')} · {r.get('kickoff_et','')} ET · {venue}"))

        # Search knockout matches
        for _, r in ko.iterrows():
            matchup = str(r.get("matchup", ""))
            venue = str(r.get("venue", ""))
            host = str(r.get("host_city", ""))
            if q in matchup.lower() or q in venue.lower() or q in host.lower():
                results.append(("🏆 Knockout", matchup, f"{r.get('match_date','')} · {r.get('kickoff_et','')} ET · {r.get('stage','')} · {venue}"))

        # Search standings
        for _, r in standings.iterrows():
            if q in str(r.get("team", "")).lower():
                s = float(r["strength_score"])
                results.append(("📊 Team", str(r["team"]),
                    f"Group {r['group_letter']} · {r['points']} pts · {r['won']}W/{r['drawn']}D/{r['lost']}L · {r['goals_for']} goals · Strength: {s:.3f} · {r['status']}"))

        # Search NYC bars
        for _, r in bars.iterrows():
            country = str(r.get("country", ""))
            spots = str(r.get("nyc_bars", ""))
            if q in country.lower() or q in spots.lower():
                results.append(("🗽 NYC Bar", country, spots))

        # Log search to BigQuery via streaming insert (free tier compatible)
        try:
            client = get_client()
            client.insert_rows_json(f"{PROJECT_ID}.{DATASET}.search_logs", [{
                "query": query,
                "result_count": len(results),
                "searched_at": datetime.now(timezone.utc).isoformat(),
                "user_email": user_email or "",
            }])
        except Exception:
            pass

    except Exception as e:
        return f"<p style='color:red;'>Search error: {e}</p>"

    if not results:
        return f"<div style='padding:16px;color:#64748b;'>No results found for <b>\"{query}\"</b>. Try a team name, country, venue, or city.</div>"

    html = f"<div style='margin-bottom:12px;color:#64748b;font-size:0.9em;'><b>{len(results)}</b> result(s) for <b>\"{query}\"</b></div>"
    for tag, title, detail in results[:20]:
        tag_color = {"⚽ Match": "#dbeafe", "🏆 Knockout": "#fef3c7", "📊 Team": "#dcfce7", "🗽 NYC Bar": "#fce7f3"}.get(tag, "#f1f5f9")
        html += f"""
        <div style="border:1px solid #e2e8f0;border-radius:10px;padding:12px 16px;margin-bottom:8px;background:white;">
          <span style="background:{tag_color};padding:2px 10px;border-radius:12px;font-size:0.78em;font-weight:600;">{tag}</span>
          <div style="font-weight:700;margin:6px 0 2px;color:#1e293b;">{title}</div>
          <div style="font-size:0.83em;color:#64748b;">{detail}</div>
        </div>"""
    if len(results) > 20:
        html += f"<div style='color:#94a3b8;font-size:0.85em;padding:8px;'>... and {len(results)-20} more results. Refine your search.</div>"
    return html


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
ROUND_STYLES = {
    "Round of 32":  {"bg": "#eff6ff", "border": "#3b82f6", "badge": "#1d4ed8", "label": "R32"},
    "Round of 16":  {"bg": "#f0fdf4", "border": "#22c55e", "badge": "#15803d", "label": "R16"},
    "Quarterfinal": {"bg": "#fef9c3", "border": "#eab308", "badge": "#854d0e", "label": "QF"},
    "Semifinal":    {"bg": "#fef3c7", "border": "#f59e0b", "badge": "#92400e", "label": "SF"},
    "Third place":  {"bg": "#f1f5f9", "border": "#94a3b8", "badge": "#475569", "label": "3rd"},
    "Final":        {"bg": "#fff1f2", "border": "#ef4444", "badge": "#991b1b", "label": "🏆 FINAL"},
}

def schedule_html(ko: pd.DataFrame) -> str:
    ko = ko.copy()
    ko["match_date"] = pd.to_datetime(ko["match_date"], errors="coerce")
    ko = ko.sort_values("match_date")
    et = zoneinfo.ZoneInfo("America/New_York")
    today = datetime.now(et).date()

    html = ""
    current_round = None
    for _, r in ko.iterrows():
        rnd = str(r.get("stage", r.get("round", "")))
        style = next((v for k, v in ROUND_STYLES.items() if k.lower() in rnd.lower()), {"bg": "white", "border": "#e2e8f0", "badge": "#64748b", "label": rnd[:4]})
        if rnd != current_round:
            current_round = rnd
            html += f"""
            <div style="display:flex;align-items:center;gap:10px;margin:20px 0 8px;">
              <span style="background:{style['badge']};color:white;padding:4px 14px;border-radius:20px;font-weight:700;font-size:0.9em;">{rnd}</span>
              <div style="flex:1;height:2px;background:{style['border']};opacity:0.4;"></div>
            </div>"""
        d = r["match_date"]
        is_today = hasattr(d, "date") and d.date() == today
        bg = style["bg"] if not is_today else "#fef2f2"
        border = "#ef4444" if is_today else style["border"]
        today_tag = " 🔴 <b>TODAY</b>" if is_today else ""
        date_str = d.strftime("%a, %b %d") if pd.notna(d) else "TBD"
        html += f"""
        <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;margin:3px 0;background:{bg};border:1px solid {border};border-radius:8px;">
          <span style="background:{style['badge']};color:white;padding:1px 8px;border-radius:8px;font-size:0.72em;font-weight:700;min-width:32px;text-align:center;">{style['label']}</span>
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
def today_et() -> date:
    return datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()


def load_games(view_date):
    if not view_date or str(view_date).strip() in ("", "None"):
        view_date = today_et()
    elif isinstance(view_date, str):
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
# Palette: midnight navy #0b1120 · electric teal #06b6d4 · vivid green #10b981
#          amber gold #f59e0b · soft white #f8fafc · card white #ffffff
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: linear-gradient(160deg,#0b1120 0%,#0f2040 100%); min-height:100vh; }
.gradio-container { max-width: 1160px !important; background: #f8fafc; border-radius: 20px !important; padding: 0 !important; box-shadow: 0 8px 48px rgba(0,0,0,0.35) !important; overflow: hidden; margin: 24px auto !important; }
.tab-nav { background: #0b1120 !important; padding: 0 20px !important; border-bottom: 2px solid #06b6d4 !important; }
.tab-nav button { font-size: 0.88em !important; font-weight: 600 !important; padding: 12px 18px !important; border-radius: 0 !important; color: #94a3b8 !important; border-bottom: 3px solid transparent !important; margin-bottom: -2px !important; }
.tab-nav button.selected { color: #06b6d4 !important; border-bottom: 3px solid #06b6d4 !important; background: transparent !important; }
.tab-nav button:hover { color: #e2e8f0 !important; }
.gradio-tabitem { padding: 20px !important; background: #f8fafc !important; }
button.primary { background: linear-gradient(135deg,#06b6d4,#0891b2) !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; }
button.primary:hover { background: linear-gradient(135deg,#0891b2,#0e7490) !important; }
button.secondary { background: #1e293b !important; color: #e2e8f0 !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; }
input[type=text], input[type=email] { border-radius: 8px !important; border: 1.5px solid #cbd5e1 !important; font-size: 0.9em !important; }
input[type=text]:focus, input[type=email]:focus { border-color: #06b6d4 !important; box-shadow: 0 0 0 3px rgba(6,182,212,0.15) !important; }
footer { display: none !important; }
"""

with gr.Blocks(title="⚽ FIFA 2026 NYC Dashboard", css=CSS) as app:
    current_email = gr.State("")

    # ── Header ────────────────────────────────────────────────────────────────
    gr.HTML("""
    <div style="background:linear-gradient(135deg,#0b1120 0%,#0f2040 55%,#064e3b 100%);padding:32px 36px 28px;position:relative;overflow:hidden;">
      <!-- decorative blobs -->
      <div style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;background:radial-gradient(circle,rgba(6,182,212,0.18) 0%,transparent 70%);pointer-events:none;"></div>
      <div style="position:absolute;bottom:-30px;left:10%;width:160px;height:160px;background:radial-gradient(circle,rgba(16,185,129,0.14) 0%,transparent 70%);pointer-events:none;"></div>
      <!-- content -->
      <div style="position:relative;z-index:1;">
        <div style="display:flex;align-items:flex-start;gap:16px;">
          <div style="background:rgba(6,182,212,0.15);border:1.5px solid rgba(6,182,212,0.4);border-radius:14px;padding:10px 14px;font-size:2em;line-height:1;">⚽</div>
          <div>
            <div style="font-size:0.7em;font-weight:600;color:#06b6d4;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px;">AD1739 · Live Dashboard</div>
            <h1 style="margin:0;font-size:1.95em;font-weight:800;color:#f8fafc;letter-spacing:-0.5px;line-height:1.15;">FIFA 2026 World Cup<br><span style="color:#06b6d4;">New York City</span></h1>
            <p style="margin:10px 0 0;color:#94a3b8;font-size:0.88em;letter-spacing:0.2px;">Live scores &nbsp;·&nbsp; Group standings &nbsp;·&nbsp; AI win predictions &nbsp;·&nbsp; NYC viewing spots</p>
          </div>
        </div>
      </div>
    </div>
    """)

    # ── Nav guide (clickable cards → jump to tab) ─────────────────────────────
    gr.HTML("""
    <div style="background:#0b1120;padding:16px 20px 20px;">
      <div style="font-size:0.7em;font-weight:600;color:#475569;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px;">Quick Navigation</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;">
        <div onclick="document.querySelectorAll('.tab-nav button')[0].click()"
             style="background:#0f2040;border:1px solid #1e3a5f;border-radius:10px;padding:10px 14px;flex:1;min-width:130px;cursor:pointer;transition:all 0.15s;color:white;"
             onmouseover="this.style.borderColor='#06b6d4';this.style.background='#0c2a50';" onmouseout="this.style.borderColor='#1e3a5f';this.style.background='#0f2040';">
          <div style="font-size:0.82em;font-weight:700;color:#06b6d4;">🗓️ Today's Games</div>
          <div style="font-size:0.7em;color:#64748b;margin-top:2px;">Kickoffs & predictions</div>
        </div>
        <div onclick="document.querySelectorAll('.tab-nav button')[1].click()"
             style="background:#0f2040;border:1px solid #1e3a5f;border-radius:10px;padding:10px 14px;flex:1;min-width:130px;cursor:pointer;transition:all 0.15s;color:white;"
             onmouseover="this.style.borderColor='#10b981';this.style.background='#0c2a50';" onmouseout="this.style.borderColor='#1e3a5f';this.style.background='#0f2040';">
          <div style="font-size:0.82em;font-weight:700;color:#10b981;">📊 Group Standings</div>
          <div style="font-size:0.7em;color:#64748b;margin-top:2px;">Points table · All groups</div>
        </div>
        <div onclick="document.querySelectorAll('.tab-nav button')[2].click()"
             style="background:#0f2040;border:1px solid #1e3a5f;border-radius:10px;padding:10px 14px;flex:1;min-width:130px;cursor:pointer;transition:all 0.15s;color:white;"
             onmouseover="this.style.borderColor='#f59e0b';this.style.background='#0c2a50';" onmouseout="this.style.borderColor='#1e3a5f';this.style.background='#0f2040';">
          <div style="font-size:0.82em;font-weight:700;color:#f59e0b;">🏆 Predictions</div>
          <div style="font-size:0.7em;color:#64748b;margin-top:2px;">AI-ranked favourites</div>
        </div>
        <div onclick="document.querySelectorAll('.tab-nav button')[3].click()"
             style="background:#0f2040;border:1px solid #1e3a5f;border-radius:10px;padding:10px 14px;flex:1;min-width:130px;cursor:pointer;transition:all 0.15s;color:white;"
             onmouseover="this.style.borderColor='#a78bfa';this.style.background='#0c2a50';" onmouseout="this.style.borderColor='#1e3a5f';this.style.background='#0f2040';">
          <div style="font-size:0.82em;font-weight:700;color:#a78bfa;">📅 Full Schedule</div>
          <div style="font-size:0.7em;color:#64748b;margin-top:2px;">R32 → R16 → QF → Final</div>
        </div>
        <div onclick="document.querySelectorAll('.tab-nav button')[4].click()"
             style="background:#0f2040;border:1px solid #1e3a5f;border-radius:10px;padding:10px 14px;flex:1;min-width:130px;cursor:pointer;transition:all 0.15s;color:white;"
             onmouseover="this.style.borderColor='#f43f5e';this.style.background='#0c2a50';" onmouseout="this.style.borderColor='#1e3a5f';this.style.background='#0f2040';">
          <div style="font-size:0.82em;font-weight:700;color:#f43f5e;">🗽 NYC Bars</div>
          <div style="font-size:0.7em;color:#64748b;margin-top:2px;">Where to watch in NYC</div>
        </div>
      </div>
    </div>
    """)

    # ── Search bar ────────────────────────────────────────────────────────────
    gr.HTML("<div style='padding:16px 20px 6px;'><div style='font-weight:600;color:#334155;font-size:0.88em;'>🔍 Search teams, matches, venues or NYC bars</div></div>")
    with gr.Row(elem_id="search-row"):
        search_box = gr.Textbox(
            placeholder="e.g. France, MetLife Stadium, South Africa, Astoria...",
            label="", scale=5, container=False,
        )
        search_btn = gr.Button("Search", variant="secondary", scale=0)
    search_results = gr.HTML()
    search_btn.click(fn=do_search, inputs=[search_box, current_email], outputs=search_results)
    search_box.submit(fn=do_search, inputs=[search_box, current_email], outputs=search_results)

    gr.HTML("<div style='height:1px;background:#e2e8f0;margin:8px 0;'></div>")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    with gr.Tabs():

        with gr.TabItem("🗓️ Today's Games"):
            with gr.Row():
                date_input = gr.DateTime(
                    label="Select date (ET)",
                    value=str(today_et()),
                    include_time=False,
                )
                load_btn = gr.Button("🔄 Load Games", variant="primary", scale=0)
            gr.HTML("<p style='color:#64748b;font-size:0.82em;margin:0 0 10px;'>All times Eastern (ET). Browse past or future dates with the picker.</p>")
            games_html = gr.HTML()
            load_btn.click(fn=load_games, inputs=date_input, outputs=games_html)
            app.load(fn=lambda: load_games(today_et()), outputs=games_html)

        with gr.TabItem("📊 Group Standings"):
            gr.HTML("<p style='color:#64748b;font-size:0.82em;margin:0 0 10px;'>🟩 1st place &nbsp;·&nbsp; 🟦 2nd place &nbsp;·&nbsp; White = eliminated. Strength score drives knockout predictions.</p>")
            standings_btn = gr.Button("🔄 Refresh Standings", variant="primary", scale=0)
            standings_html = gr.HTML()
            standings_btn.click(fn=load_standings, outputs=standings_html)
            app.load(fn=load_standings, outputs=standings_html)

        with gr.TabItem("🏆 Predictions"):
            gr.HTML("<p style='color:#64748b;font-size:0.82em;margin:0 0 10px;'>Strength Score = 45% win rate + 30% goals/game + 15% defense + 10% points efficiency.</p>")
            pred_btn = gr.Button("🔄 Refresh Predictions", variant="primary", scale=0)
            pred_html = gr.HTML()
            pred_btn.click(fn=load_predictions, outputs=pred_html)
            app.load(fn=load_predictions, outputs=pred_html)

        with gr.TabItem("📅 Full Schedule"):
            gr.HTML("""<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;font-size:0.78em;align-items:center;'>
              <span style='color:#64748b;font-weight:600;margin-right:4px;'>Legend:</span>
              <span style='background:#1d4ed8;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>R32</span>
              <span style='background:#15803d;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>R16</span>
              <span style='background:#92400e;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>QF</span>
              <span style='background:#7c2d12;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>SF</span>
              <span style='background:#475569;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>3rd</span>
              <span style='background:#991b1b;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>🏆 Final</span>
              <span style='background:#ef4444;color:white;padding:3px 10px;border-radius:20px;font-weight:600;'>🔴 Today</span>
            </div>""")
            sched_btn = gr.Button("🔄 Refresh Schedule", variant="primary", scale=0)
            sched_html = gr.HTML()
            sched_btn.click(fn=load_schedule, outputs=sched_html)
            app.load(fn=load_schedule, outputs=sched_html)

        with gr.TabItem("🗽 NYC Bars"):
            gr.HTML("<p style='color:#64748b;font-size:0.82em;margin:0 0 10px;'>🔵 Blue border = dedicated supporter bar &nbsp;·&nbsp; Grey = multi-nation soccer bar. Always confirm with the venue.</p>")
            bars_btn = gr.Button("🔄 Refresh", variant="primary", scale=0)
            bars_html_out = gr.HTML()
            bars_btn.click(fn=load_bars, outputs=bars_html_out)
            app.load(fn=load_bars, outputs=bars_html_out)

    # ── Subscribe (bottom) ────────────────────────────────────────────────────
    gr.HTML("""
    <div style="margin:8px 20px 0;padding:20px 24px;background:linear-gradient(135deg,#0b1120,#0f2040);border-radius:14px;">
      <div style="color:#f8fafc;font-weight:700;font-size:1em;margin-bottom:4px;">📬 Get daily match alerts & predictions</div>
      <div style="color:#64748b;font-size:0.8em;margin-bottom:12px;">Stay updated on today's games, results, and tournament picks.</div>
    </div>
    """)
    with gr.Row():
        email_name = gr.Textbox(placeholder="Your name (optional)", label="", scale=1, container=False)
        email_input = gr.Textbox(placeholder="Your email address", label="", scale=2, container=False)
        email_btn = gr.Button("Subscribe →", variant="primary", scale=0)
    email_status = gr.HTML()

    def on_subscribe(name, email):
        msg = save_email(name, email)
        saved = email if "✅" in msg else ""
        bg = "#f0fdf4" if "✅" in msg else "#fff7ed"
        color = "#15803d" if "✅" in msg else "#b45309"
        return f"<div style='padding:8px 12px;border-radius:8px;background:{bg};color:{color};font-weight:500;margin-top:4px;'>{msg}</div>", saved

    email_btn.click(fn=on_subscribe, inputs=[email_name, email_input], outputs=[email_status, current_email])

    # ── Footer / Disclaimer ───────────────────────────────────────────────────
    gr.HTML("""
    <div style="margin:20px 20px 20px;padding:18px 22px;background:#f1f5f9;border-radius:12px;border:1px solid #e2e8f0;font-size:0.76em;color:#64748b;line-height:1.7;">
      <div style="font-weight:700;color:#475569;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.8px;font-size:0.85em;">Disclaimer</div>
      <p style="margin:0 0 5px;">This is an independent fan dashboard for informational and entertainment purposes only.
      Data is sourced from publicly available FIFA 2026 records and may not reflect real-time updates.
      Win predictions are algorithmic estimates — not professional sports analysis or betting advice.</p>
      <p style="margin:0;">NYC bar listings are community-sourced; always verify with the venue directly.</p>
      <div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
        <span style="font-weight:700;color:#0b1120;font-size:0.95em;">© 2026 AD1739</span>
        <span style="color:#94a3b8;">FIFA World Cup 2026 · Data updated June 2026</span>
      </div>
    </div>
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=True,
        share=False,
    )
