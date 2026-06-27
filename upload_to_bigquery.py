"""Upload FIFA 2026 World Cup data from Excel to BigQuery."""

import os
import re
import pandas as pd
from google.cloud import bigquery

PROJECT_ID = "proud-sweep-323918"
DATASET_ID = "fifa_2026"
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "data", "world_cup_2026.xlsx")


def clean_group_stage(xl: pd.ExcelFile) -> pd.DataFrame:
    df = xl.parse("Group Stage Schedule", header=None)
    # Row 1 (index 1) has headers
    df.columns = df.iloc[1]
    df = df.iloc[2:].reset_index(drop=True)
    df = df.dropna(how="all")
    df.columns = [
        "match_date", "day_of_week", "group_letter", "matchup",
        "kickoff_et", "result", "venue", "host_city",
        "nyc_bars_team1", "nyc_bars_team2",
    ]
    df = df[df["matchup"].notna() & df["matchup"].astype(str).str.contains(" vs. ", na=False)]

    def parse_teams(s):
        parts = str(s).split(" vs. ", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

    df[["team1", "team2"]] = df["matchup"].apply(lambda x: pd.Series(parse_teams(x)))

    def parse_score(r):
        m = re.match(r"^(\d+)-(\d+)$", str(r).strip())
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None

    df[["goals_team1", "goals_team2"]] = df["result"].apply(lambda x: pd.Series(parse_score(x)))
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce", format="%a, %b %d").apply(
        lambda d: d.replace(year=2026) if pd.notna(d) else d
    )
    df["stage"] = "Group Stage"
    return df[[
        "match_date", "day_of_week", "stage", "group_letter", "matchup",
        "team1", "team2", "kickoff_et", "goals_team1", "goals_team2",
        "result", "venue", "host_city", "nyc_bars_team1", "nyc_bars_team2",
    ]]


def clean_knockout(xl: pd.ExcelFile) -> pd.DataFrame:
    df = xl.parse("Knockout Schedule", header=None)
    df.columns = df.iloc[1]
    df = df.iloc[2:].reset_index(drop=True)
    df = df.dropna(how="all")
    df.columns = ["round", "match_date", "match_number", "matchup", "kickoff_et", "venue", "host_city"]
    df = df[df["round"].notna() & ~df["round"].astype(str).str.startswith("Note")]
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce", format="%a, %b %d").apply(
        lambda d: d.replace(year=2026) if pd.notna(d) else d
    )
    df["stage"] = df["round"]
    return df[[
        "match_date", "stage", "match_number", "matchup",
        "kickoff_et", "venue", "host_city",
    ]]


def clean_standings(xl: pd.ExcelFile) -> pd.DataFrame:
    df = xl.parse("Standings (Goals & Wins)", header=None)
    df.columns = df.iloc[2]
    df = df.iloc[3:].reset_index(drop=True)
    df = df.dropna(how="all")
    df.columns = [
        "group_letter", "team", "played", "won", "drawn", "lost",
        "goals_for", "goals_against", "goal_diff", "points", "status",
    ]
    df = df[df["team"].notna()]

    for col in ["played", "won", "drawn", "lost", "goals_for", "goals_against", "points"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Numeric goal_diff (strip + signs)
    df["goal_diff_num"] = df["goal_diff"].astype(str).str.replace("+", "", regex=False)
    df["goal_diff_num"] = pd.to_numeric(df["goal_diff_num"], errors="coerce")

    # Win rate and goals per game for predictions
    df["win_rate"] = df["won"] / df["played"].replace(0, 1)
    df["goals_per_game"] = df["goals_for"] / df["played"].replace(0, 1)
    df["conceded_per_game"] = df["goals_against"] / df["played"].replace(0, 1)

    # Prediction strength score: weighted combo
    df["strength_score"] = (
        df["win_rate"] * 0.45
        + (df["goals_per_game"] / 5.0) * 0.30
        + ((3 - df["conceded_per_game"]) / 3.0).clip(0, 1) * 0.15
        + (df["points"] / (df["played"] * 3).replace(0, 1)) * 0.10
    )
    return df[[
        "group_letter", "team", "played", "won", "drawn", "lost",
        "goals_for", "goals_against", "goal_diff_num", "points",
        "status", "win_rate", "goals_per_game", "conceded_per_game", "strength_score",
    ]]


def clean_nyc_bars(xl: pd.ExcelFile) -> pd.DataFrame:
    df = xl.parse("NYC Bars by Country")
    df.columns = ["country", "nyc_bars"]
    df = df[df["country"].notna()]
    return df


def upload_df(client: bigquery.Client, df: pd.DataFrame, table_name: str, schema: list):
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_TRUNCATE",
    )
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    print(f"  Uploaded {len(df)} rows -> {table_ref}")


def main():
    os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/credentials.json")
    client = bigquery.Client(project=PROJECT_ID)

    xl = pd.ExcelFile(EXCEL_PATH)

    print("Uploading group_stage_matches...")
    gs = clean_group_stage(xl)
    upload_df(client, gs, "group_stage_matches", [
        bigquery.SchemaField("match_date", "DATE"),
        bigquery.SchemaField("day_of_week", "STRING"),
        bigquery.SchemaField("stage", "STRING"),
        bigquery.SchemaField("group_letter", "STRING"),
        bigquery.SchemaField("matchup", "STRING"),
        bigquery.SchemaField("team1", "STRING"),
        bigquery.SchemaField("team2", "STRING"),
        bigquery.SchemaField("kickoff_et", "STRING"),
        bigquery.SchemaField("goals_team1", "INTEGER"),
        bigquery.SchemaField("goals_team2", "INTEGER"),
        bigquery.SchemaField("result", "STRING"),
        bigquery.SchemaField("venue", "STRING"),
        bigquery.SchemaField("host_city", "STRING"),
        bigquery.SchemaField("nyc_bars_team1", "STRING"),
        bigquery.SchemaField("nyc_bars_team2", "STRING"),
    ])

    print("Uploading knockout_matches...")
    ko = clean_knockout(xl)
    upload_df(client, ko, "knockout_matches", [
        bigquery.SchemaField("match_date", "DATE"),
        bigquery.SchemaField("stage", "STRING"),
        bigquery.SchemaField("match_number", "STRING"),
        bigquery.SchemaField("matchup", "STRING"),
        bigquery.SchemaField("kickoff_et", "STRING"),
        bigquery.SchemaField("venue", "STRING"),
        bigquery.SchemaField("host_city", "STRING"),
    ])

    print("Uploading team_standings...")
    st = clean_standings(xl)
    upload_df(client, st, "team_standings", [
        bigquery.SchemaField("group_letter", "STRING"),
        bigquery.SchemaField("team", "STRING"),
        bigquery.SchemaField("played", "INTEGER"),
        bigquery.SchemaField("won", "INTEGER"),
        bigquery.SchemaField("drawn", "INTEGER"),
        bigquery.SchemaField("lost", "INTEGER"),
        bigquery.SchemaField("goals_for", "INTEGER"),
        bigquery.SchemaField("goals_against", "INTEGER"),
        bigquery.SchemaField("goal_diff_num", "INTEGER"),
        bigquery.SchemaField("points", "INTEGER"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("win_rate", "FLOAT"),
        bigquery.SchemaField("goals_per_game", "FLOAT"),
        bigquery.SchemaField("conceded_per_game", "FLOAT"),
        bigquery.SchemaField("strength_score", "FLOAT"),
    ])

    print("Uploading nyc_bars...")
    bars = clean_nyc_bars(xl)
    upload_df(client, bars, "nyc_bars", [
        bigquery.SchemaField("country", "STRING"),
        bigquery.SchemaField("nyc_bars", "STRING"),
    ])

    print("\nAll tables uploaded successfully.")


if __name__ == "__main__":
    main()
