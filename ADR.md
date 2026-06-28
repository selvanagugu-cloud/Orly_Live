# ADR-001 — Real-Time Flight Board: Architecture Decisions

**Status:** Accepted  
**Date:** 2026-06-25  
**Author:** Nagulan  
**Context:** Personal project — live arrivals/departures board for Paris Orly Airport

\---

## Context

I wanted to build a real-time operational dashboard showing live flights at Paris Orly (LFPO),
similar to what I work with daily at Transavia. The goal was to practice GCP streaming
infrastructure and demonstrate a production-grade data pipeline for interviews.

Key constraints:

* Must run in a single evening (≤3h setup)
* Must use GCP stack (BigQuery, Pub/Sub, Terraform) to match Kering's stack
* Free tier only (no paid subscriptions)
* Real data, not mocked

\---

## Decision 1 — Data Source: OpenSky Network API

### Options considered

|Option|Pros|Cons|
|-|-|-|
|**OpenSky Network API**|Free, real-time, no API key needed, LFPO filter|Rate-limited (10 req/min anonymous)|
|AviationStack API|Clean REST API, rich data|Paid above 100 req/month|
|FlightAware API|Very rich, airline logos|Expensive ($$$)|
|Scraping FlightRadar24|Free data|ToS violation, fragile|

### Decision: OpenSky Network API

OpenSky provides a public REST endpoint (`/api/states/all`) with bounding box filtering.
For Orly's coordinates (lat 48.7233, lon 2.3794), a ±0.5° bounding box captures all
approach/departure traffic reliably. No API key needed for polling every 10 seconds.

\---

## Decision 2 — Streaming: Pub/Sub (not Kafka)

### Options considered

|Option|Pros|Cons|
|-|-|-|
|**Google Pub/Sub**|Fully managed, native GCP, zero ops|7-day retention max|
|Apache Kafka|Infinite retention, ordering guarantees|Cluster to manage, overkill for this volume|
|Direct BigQuery streaming|Simple, fewer components|No decoupling, harder to add consumers|

### Decision: Google Pub/Sub

Volume is low (\~30 aircraft in the Orly zone at any time). Pub/Sub gives:

* **Decoupling**: the poller doesn't know about BigQuery or the dashboard
* **Resilience**: if BigQuery is briefly unavailable, messages queue in Pub/Sub
* **GCP native**: integrates directly with BigQuery subscription...

**BUT** — BigQuery native subscription requires schema management and is painful for
JSON payloads that change shape. Instead, I use a **lightweight Python consumer** that
reads from Pub/Sub and writes to BigQuery with explicit schema mapping. This gives full
control over transformations before storage.

\---

## Decision 3 — Storage: BigQuery (not Cloud SQL or Firestore)

### Decision: BigQuery

* **Partitioned** on `snapshot\_time` (hourly) — keeps query costs minimal
* **Clustered** on `icao24` and `origin\_country` — fast filtering per airline
* Enables historical analysis ("how delayed was Air France at 18:00 last Tuesday?")
* dbt transformations on top for clean Data Products

\---

## Decision 4 — Dashboard: Streamlit (not Looker Studio)

### Options considered

|Option|Pros|Cons|
|-|-|-|
|**Streamlit**|Real-time refresh, custom UI, airline logos, free|Needs a running server|
|Looker Studio|Native BigQuery connector, shareable|15min data refresh minimum — useless for real-time|
|Grafana|Great for time-series|Complex setup, not GCP native|

### Decision: Streamlit

Looker Studio has a **minimum 15-minute refresh** — unacceptable for a live flight board.
Streamlit allows `st.rerun()` every 10 seconds, queries BigQuery directly, and renders
airline logos dynamically via `airportsdata` + logo mapping. Perfect for a live demo.

\---

## Decision 5 — Infra: Terraform

All GCP resources provisioned as code:

* BigQuery dataset + 2 tables (raw flights, processed flights)
* Pub/Sub topic + subscription
* Service Account with least-privilege IAM roles

Trade-off accepted: no remote state backend for this personal project (would add GCS bucket
complexity). In production, remote state in GCS with locking would be mandatory.

\---

## Diagram

```
OpenSky API (every 10s)
        │
   \[Python poller]          ← src/ingestion/poller.py
        │
   Pub/Sub topic            ← "orly-flights"
  (orly-flights)
        │
  \[Python consumer]         ← src/ingestion/consumer.py
        │
  BigQuery raw              ← paris\_orly.raw\_flights
  (partitioned + clustered)
        │
      \[dbt]                 ← staging → marts
        │
  BigQuery marts
  ┌─────────────────────┐
  │ mart\_live\_board     │   ← current state per flight
  │ mart\_airline\_stats  │   ← delay stats per airline
  └─────────────────────┘
        │
  \[Streamlit dashboard]     ← Live board with logos, auto-refresh 10s
```

\---

## What I would add in production (Kering-grade)

1. **Remote Terraform state** in GCS with object locking
2. **Dataflow** instead of Python consumer for auto-scaling
3. **Airflow DAG** orchestrating the dbt runs every 15 min
4. **Data quality checks** with dbt tests + Great Expectations
5. **CI/CD** with GitHub Actions: terraform plan on PR, apply on merge
6. **Monitoring** with Cloud Monitoring alerts on Pub/Sub message age

