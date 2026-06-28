# Orly Live

Real-time departures and arrivals board for Paris Orly Airport (LFPO).

Built as a personal project to work with GCP streaming infrastructure in a domain
I know well from my day job at Transavia.

**Stack:** FlightRadarAPI · Google Pub/Sub · BigQuery · dbt · Streamlit · Terraform

---

## What it does

- Polls FlightRadar24 every 30 seconds for live departures and arrivals at Orly
- Publishes each flight as a Pub/Sub message
- Consumer reads Pub/Sub, maps fields, and detects status changes (departed, landed,
  delayed, cancelled) via an in-memory state machine
- Data lands in BigQuery (partitioned by hour, clustered by airline)
- dbt builds staging views and two mart tables: live board and airline delay stats
- Streamlit dashboard auto-refreshes every 15 seconds with airline logos, delay info,
  a Europe route map, and a Transavia-only filter

All architectural decisions are documented in [ADR.md](./ADR.md).

---

## Architecture

```
FlightRadar24 (every 30s)
  fr_api.get_airport("LFPO", details=True)
       │
  Python Poller         src/ingestion/poller.py
       │  JSON
  Pub/Sub               orly-flights (1h retention, EU storage policy)
       │  streaming pull
  Python Consumer       src/ingestion/consumer.py
  (field mapping + status change CDC)
       │
  BigQuery
  ├── raw_flights        partitioned HOUR · clustered flight_type, airline_icao
  └── flight_events      partitioned DAY  · status change events
       │
     dbt
  ├── stg_raw_flights    view — clean + delay calculation
  ├── mart_live_board    table — current state per flight
  └── mart_airline_stats table — 24h delay stats
       │
  Streamlit              src/dashboard/app.py
  5 tabs: Departures · Arrivals · Map · Airlines · Events
```

---

## Setup

### 1. Auth

```bash
gcloud auth login
gcloud auth application-default login
export GCP_PROJECT_ID=""
```

### 2. Enable APIs

```bash
gcloud services enable bigquery.googleapis.com pubsub.googleapis.com iam.googleapis.com
```

### 3. Infrastructure

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set your project_id

terraform init
terraform plan -var-file="terraform.tfvars" -out=tfplan.bin
terraform show tfplan.bin        # review before applying
terraform apply tfplan.bin
cd ..
```

### 4. Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install google-cloud-bigquery-storage  # faster BQ queries
```

### 5. Run

Three terminals:

```bash
# Terminal 1 — poller
export GCP_PROJECT_ID=""
python src/ingestion/poller.py

# Terminal 2 — consumer
export GCP_PROJECT_ID=""
python src/ingestion/consumer.py

# Terminal 3 — dashboard
export GCP_PROJECT_ID=""
streamlit run src/dashboard/app.py
```

Open http://localhost:8501. Wait about 1 minute for the first data to appear.

### 6. dbt (optional)

```bash
cp dbt/profiles.example.yml ~/.dbt/profiles.yml
# Edit: set your project ID

cd dbt/
dbt debug
dbt run
dbt test
dbt docs generate && dbt docs serve  # lineage graph at localhost:8080
```

---

## Docs

- [ADR.md](./ADR.md) — architecture decision records
- [docs/terraform_commands.md](./docs/terraform_commands.md) — all Terraform commands with examples
- [docs/medium_article.md](./docs/medium_article.md) — write-up for publication
- [docs/project_narrative.md](./docs/project_narrative.md) — how to present the project
- [docs/interview_revision_guide.md](./docs/interview_revision_guide.md) — revision guide

---

## Clean up

```bash
cd terraform/
terraform destroy -var-file="terraform.tfvars"
```
