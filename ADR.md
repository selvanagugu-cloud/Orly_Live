# ADR — Architecture Decision Records

## Orly Live · Paris Orly Real-Time Flight Board

\---

## ADR-001 — Consumer Python vs Native BigQuery Subscription

**Status:** Accepted  
**Date:** 2026-06-25

### Context

Pub/Sub has a native BigQuery subscription feature: messages are written directly
to a BigQuery table with no code. Zero infrastructure, zero process to manage.

### Options considered

|Option|Pros|Cons|
|-|-|-|
|BigQuery native subscription|Zero code, zero ops|No transformation layer, strict schema match required|
|Python consumer|Full control, transformation, state|Extra process to run|
|Apache Beam on Dataflow|Auto-scaling, exactly-once|Complex, overkill for this volume|

### Decision: Python consumer

Two things ruled out the native subscription entirely.

**Field mapping.** The FlightRadar24 JSON payload is deeply nested:

```json
{
  "flight": {
    "identification": {
      "number": { "default": "TO4610" }
    },
    "airline": {
      "name": "Transavia",
      "code": { "icao": "TVF", "iata": "TO" }
    },
    "airport": {
      "origin": {
        "code": { "iata": "ORY" },
        "info": { "terminal": "3", "gate": "35" }
      },
      "destination": {
        "code": { "iata": "AGP" }
      }
    },
    "time": {
      "scheduled": { "departure": 1750834200 },
      "estimated": { "departure": 1750836600 }
    },
    "status": { "text": "Estimated dep 06:10" }
  }
}
```

Extracting `flight.identification.number.default` into a flat `flight\_number`
column is something I want to do once, in Python, before data hits BigQuery —
not wrestle with `JSON\_EXTRACT` on every query.

**Status change detection (CDC).** The consumer maintains an in-memory state cache:

```python
# In-memory state: {flight\_number: {"status": str, "last\_seen": str}}
state\_cache = {}

def detect\_status\_change(row):
    flight\_number  = row\["flight\_number"]
    current\_status = row\["status"]
    previous       = state\_cache.get(flight\_number)

    if previous and previous\["status"] != current\_status:
        event = {
            "event\_id":      str(uuid.uuid4()),
            "flight\_number": flight\_number,
            "status\_before": previous\["status"],
            "status\_after":  current\_status,
            "event\_type":    classify\_event(current\_status),
            "event\_time":    row\["snapshot\_time"],
        }
        events\_writer.add(event)

    state\_cache\[flight\_number] = {
        "status":    current\_status,
        "last\_seen": row\["snapshot\_time"],
    }
```

This is Change Data Capture — comparing current state against previous state
to detect transitions. A native subscription has no mechanism for inter-message
state. It receives one message, writes one row, and forgets. The Python consumer
keeps the state machine alive between messages.

### Consequences

* Extra running process to manage
* State lost on consumer restart — known limitation, acceptable for this use case
* Production migration path: replace with Dataflow (Apache Beam on GCP),
which auto-scales and supports stateful processing natively

\---

## ADR-002 — Pub/Sub vs Direct BigQuery Write

**Status:** Accepted  
**Date:** 2026-06-25

### Context

The poller fetches data every 30 seconds. The simplest design writes directly
to BigQuery from the poller. Why add Pub/Sub in between?

### Options considered

|Option|Pros|Cons|
|-|-|-|
|Google Pub/Sub|Decoupling, resilience, DLQ, native GCP|Extra component|
|Direct BigQuery write|Simpler, fewer components|Tight coupling, data loss on BQ downtime|
|Kafka|Infinite retention, ordering|Cluster to manage, overkill|

### Decision: Google Pub/Sub

**Decoupling.** The poller does not know who consumes its data. If tomorrow I want
to add a Slack alert when a flight is delayed more than 2 hours, I add a second
consumer — no changes to the poller. With direct writes, the poller is tightly
coupled to every downstream system.

**Resilience.** If BigQuery is briefly unavailable (quota exceeded, maintenance),
messages buffer in Pub/Sub for up to 1 hour. With direct writes, 30 seconds of
data are lost permanently.

The DLQ and retry configuration in Terraform:

```hcl
resource "google\_pubsub\_subscription" "orly\_flights\_sub" {
  name  = "orly-flights-sub"
  topic = google\_pubsub\_topic.orly\_flights.name

  dead\_letter\_policy {
    dead\_letter\_topic     = google\_pubsub\_topic.orly\_flights\_dlq.id
    max\_delivery\_attempts = 3
  }

  retry\_policy {
    minimum\_backoff = "5s"
    maximum\_backoff = "60s"
  }

  # Without this, GCP auto-deletes the subscription after 31 days of inactivity
  expiration\_policy {
    ttl = ""
  }
}
```

After 3 failed delivery attempts, the message goes to `orly-flights-dlq`
rather than disappearing silently. In production, a Cloud Function on the
DLQ topic would alert on-call.

### Consequences

* One extra GCP component to provision and monitor
* 7-day max retention — historical data lives in BigQuery, not Pub/Sub
* Trade-off accepted: no infinite replay (Kafka advantage), but zero ops overhead

\---

## ADR-003 — Streamlit vs Looker Studio

**Status:** Accepted  
**Date:** 2026-06-25

### Context

The dashboard needs to reflect live flight data. Two realistic options:
Looker Studio (native BigQuery connector, zero server) or Streamlit (code,
but full control over refresh rate).

### Options considered

|Option|Pros|Cons|
|-|-|-|
|Streamlit|Genuine real-time refresh, custom UI, airline logos|Needs a running server|
|Looker Studio|Native BQ, shareable, zero server|15 min minimum refresh|
|Grafana|Good time-series|Heavy setup, not GCP native|

### Decision: Streamlit

The dealbreaker for Looker Studio: **hard minimum refresh interval of 15 minutes.**

A flight board with 15-minute-old data is not a live flight board.
It is a history report. For an operations team, a 15-minute delay in seeing
a flight go from "Scheduled" to "Delayed 2 hours" means missed interventions.

Streamlit's `st.rerun()` combined with `@st.cache\_data(ttl=12)` gives
genuine real-time refresh with minimal BigQuery load:

```python
@st.cache\_data(ttl=12)   # cache for 12 seconds
def load\_departures():
    return get\_bq().query(Q\_DEPARTURES).to\_dataframe()

def main():
    df = load\_departures()   # served from cache on most reruns
    st.markdown(render\_flight\_table(df), unsafe\_allow\_html=True)

    time.sleep(15)
    st.rerun()   # full page refresh every 15 seconds
```

The 12-second cache means BigQuery is queried at most once per 15-second cycle,
regardless of how many components render on the page.

### Consequences

* Server process required (acceptable for a personal project)
* In production: deploy on Cloud Run with auto-scaling
* Looker Studio remains the right choice for analytical reporting dashboards
where 15-minute freshness is acceptable

\---


## What I would add for production

1. **Dataflow** — replace Python consumer, auto-scaling, exactly-once semantics
2. **Remote Terraform state** — GCS backend with object locking
3. **Airflow DAG** — orchestrate dbt runs every 15 min, alert on freshness SLA
4. **Cloud Monitoring** — alert on `subscription/oldest\_unacked\_message\_age`
5. **Authorized Views** — expose mart tables without giving access to raw data
6. **Redis (Memorystore)** — persist the CDC state cache across consumer restarts

