# FIFA 2026 World Cup NYC Dashboard

## Overview
Streamlit dashboard showing today's games, group standings, NYC bar viewing spots, and ML-based win predictions — backed by BigQuery.

## Cloud Credentials

- **Provider:** GCP
- **Project ID:** `proud-sweep-323918`
- **Service Account:** `fifa-dashboard-sa@proud-sweep-323918.iam.gserviceaccount.com`
- **Roles granted:**
  - `roles/bigquery.dataEditor` — upload/refresh Excel data to BigQuery
  - `roles/bigquery.jobUser` — run queries from the dashboard
  - `roles/bigquery.dataViewer` — read tables
- **Dataset:** `proud-sweep-323918.fifa_2026`
- **Tables:** `group_stage_matches`, `knockout_matches`, `team_standings`, `nyc_bars`

Each team member has their own `.cloud-credentials.<email>.enc` file. The agent decrypts and activates credentials automatically via the SessionStart hook.

## Adding a New Team Member
Run the cloud-bootstrap skill from Claude Code. It will detect you're missing a credentials file and walk through the Add Team Member workflow.

## Escalating Permissions
If a command fails with 403, use the cloud-bootstrap skill → permission escalation workflow.

## Running Locally
```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/credentials.json streamlit run dashboard.py
```

## Deploying to Cloud Run
```bash
bash deploy_cloud_run.sh
```

## Refreshing BigQuery Data
```bash
GOOGLE_APPLICATION_CREDENTIALS=/tmp/credentials.json python3 upload_to_bigquery.py
```
