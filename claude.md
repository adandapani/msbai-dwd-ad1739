# msbai-dwd-ad1739
Anusha NYU MSBA repo

## Cloud Credentials

- **Provider:** GCP
- **Project ID:** `project-4dbffca4-5d78-4e9e-b64`
- **Service Account:** `claude-agent@project-4dbffca4-5d78-4e9e-b64.iam.gserviceaccount.com`
- **Roles:**
  - `roles/bigquery.dataEditor` — read/write BigQuery datasets and tables
  - `roles/bigquery.jobUser` — run BigQuery queries

### Authentication (Session Token Mode)

This project uses **session token authentication** because the GCP org policy disables service account key creation.

**At the start of each Claude Code session:**

1. Open [Google Cloud Shell](https://console.cloud.google.com) (click the `>_` icon)
2. Run:
   ```bash
   gcloud config set project project-4dbffca4-5d78-4e9e-b64
   gcloud auth print-access-token
   ```
3. Paste the token into the chat and ask Claude to activate GCP credentials.

Claude will then run:
```bash
gcloud auth activate-service-account \
  --access-token-file=<(echo "$TOKEN")
gcloud config set project project-4dbffca4-5d78-4e9e-b64
```

Tokens expire after ~1 hour. If a BigQuery command fails with a 401/403, generate a new token and re-authenticate.

### Adding a New Team Member

The service account and roles are shared. New team members just need to follow the same session token steps above — no additional setup required.

### Permission Escalation

To add more roles to the service account, a GCP project Owner must grant them via the [IAM console](https://console.cloud.google.com/iam-admin/iam).
