# Deployment — Land AI Multi-Hazard Intelligence

**Nothing here runs automatically.** The existing production (wildfire v2) keeps running untouched. This project is deployed
as a **separate** pair of resources, tested, and only then promoted.

| | Production today (wildfire v2) | New (multi-hazard v3) — suggested names |
|---|---|---|
| Cloud project / region | `applandai` / `us-east1` | same |
| Cloud Run service | `landai-wildfire-api` | **`landai-multihazard-api`** |
| Frontend | `https://landaiapp.github.io/landai-wildfire/` | **`https://landaiapp.github.io/landai-multihazard/`** (new repo `landai-multihazard`) |

Promotion options after testing (your decision): (a) keep both side by side, (b) point the old frontend at the new API, or
(c) move the old URL to the new repo. The legacy wildfire routes are unchanged, so (b) is backwards compatible.

## 0. Before anything
* Complete [LOCAL_TESTING_ES.md](LOCAL_TESTING_ES.md) (sections 1-9) and tick the pre-production checklist.
* Revoke the Earth Engine key that was exposed earlier (IAM → Service accounts → Keys) and create a new one.
* Create a Billing **budget alert** (Billing → Budgets & alerts). Google Cloud has no hard spending cap.

## 1. Backend → Cloud Run (staging service first)
Reuse the service account, secret and Earth Engine project of the current production. Replace the placeholders.

```powershell
$PROJECT = "applandai"
$REGION  = "us-east1"
$SA      = "<service-account-email-used-in-production>"
$SECRET  = "<secret-name-with-the-NEW-ee-key>"

gcloud config set project $PROJECT

gcloud run deploy landai-multihazard-api `
  --source backend `
  --region $REGION `
  --port 8000 `
  --service-account $SA `
  --allow-unauthenticated `
  --timeout 1200 --memory 2Gi --cpu 1 `
  --min-instances 0 --max-instances 1 `
  --set-secrets "/secrets/ee-key.json=${SECRET}:latest" `
  --set-env-vars "EE_PROJECT=$PROJECT,EE_PRIVATE_KEY_PATH=/secrets/ee-key.json,CORS_ORIGINS=https://landaiapp.github.io,TRUST_FORWARDED_FOR=true,ANALYSIS_REF_SECRET=<long random, NEW>,WORLDPOP_YEAR=2020"
```
* `--min-instances 0` (scale to zero) and `--max-instances 1` keep the cost bounded; rate limits and caches are per instance.
* Raise `--memory` to `4Gi` only if flood exposure on large areas hits out-of-memory (watch Cloud Run logs).
* To pause expensive work without redeploying code: `gcloud run services update landai-multihazard-api --update-env-vars ANALYSIS_ENABLED=false,EXPOSURE_ENABLED=false`.
* Check: `<URL>/health?check_ee=true`, `<URL>/api/v1/hazards`, `<URL>/api/v1/config` (version `3.0.0`, `hazards.flood`).

## 2. Frontend → GitHub Pages
1. Create the repo `landai-multihazard`, push this project, enable *Settings → Pages → Source: GitHub Actions*.
2. Repository variables: `VITE_API_BASE_URL` = the new Cloud Run URL; `VITE_LANDAI_CONTACT_URL` (optional).
3. The existing workflow builds with `VITE_BASE_PATH=/<repo-name>/` and publishes on push to `main`.
4. Add the origin to the backend if it changes: `--update-env-vars "^@^CORS_ORIGINS=https://landaiapp.github.io@..."`.

## 3. Smoke test in the cloud
Open the site → landing shows the two modules (Wildfire, Flood) → Wildfire example (Tolima · San Luis) → Flood with the dates of the reference
script → exposure on a small area. Compare with the local results you recorded.

## 4. Rollback
The old service and site are untouched: rollback is "keep using them". For the new service,
`gcloud run services update-traffic landai-multihazard-api --to-revisions <previous>=100` or delete the service.
