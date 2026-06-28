"""
Orly Live — Pub/Sub Consumer
Reads flight messages from Pub/Sub and writes to BigQuery.

The poller sends airport-level data (departures + arrivals) from
FlightRadar24's airport endpoint. Each message contains:
  flight_number, flight_type (departure/arrival), airline info,
  route (origin_iata, destination_iata), terminal, gate,
  scheduled/real/estimated times, status, snapshot_time.

This consumer maps those fields to BigQuery, detects status changes
between polls (e.g. Scheduled -> Estimated -> Landed), and writes
change events to flight_events table.

Usage:
    export GCP_PROJECT_ID=
    python src/ingestion/consumer.py
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from google.cloud import bigquery, pubsub_v1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("orly.consumer")

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID      = os.environ["GCP_PROJECT_ID"]
SUBSCRIPTION_ID = "orly-flights-sub"
DATASET_ID      = "paris_orly"
RAW_TABLE       = "{}.{}.raw_flights".format(PROJECT_ID, DATASET_ID)
EVENTS_TABLE    = "{}.{}.flight_events".format(PROJECT_ID, DATASET_ID)

BATCH_SIZE      = 25

# ── In-memory state cache ─────────────────────────────────────────────────────
# Tracks previous status per flight_number to detect status changes
# {flight_number: {"status": str, "last_seen": str}}
state_cache = {}


# ── Row coercion ──────────────────────────────────────────────────────────────

def safe_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def coerce_row(payload, message_id):
    """
    Maps the Pub/Sub payload (from new poller) to a BigQuery-ready dict.
    All fields match the Terraform schema in main.tf.
    """
    return {
        # Identity
        "flight_number":       safe_str(payload.get("flight_number")),
        "flight_type":         safe_str(payload.get("flight_type")),   # departure / arrival
        # Airline
        "airline_name":        safe_str(payload.get("airline_name")),
        "airline_icao":        safe_str(payload.get("airline_icao")),
        "airline_iata":        safe_str(payload.get("airline_iata")),
        # Aircraft
        "aircraft_code":       safe_str(payload.get("aircraft_code")),
        "registration":        safe_str(payload.get("registration")),
        # Route
        "origin_iata":         safe_str(payload.get("origin_iata")),
        "origin_terminal":     safe_str(payload.get("origin_terminal")),
        "origin_gate":         safe_str(payload.get("origin_gate")),
        "destination_iata":    safe_str(payload.get("destination_iata")),
        "dest_terminal":       safe_str(payload.get("dest_terminal")),
        "dest_gate":           safe_str(payload.get("dest_gate")),
        # Schedules (already ISO strings from poller)
        "scheduled_departure": payload.get("scheduled_departure"),
        "scheduled_arrival":   payload.get("scheduled_arrival"),
        "real_departure":      payload.get("real_departure"),
        "real_arrival":        payload.get("real_arrival"),
        "estimated_departure": payload.get("estimated_departure"),
        "estimated_arrival":   payload.get("estimated_arrival"),
        # Status
        "status":              safe_str(payload.get("status")),
        # Meta
        "snapshot_time":       payload.get("snapshot_time") or datetime.now(timezone.utc).isoformat(),
        "pub_sub_message_id":  message_id,
    }


# ── Status change detection ───────────────────────────────────────────────────

def detect_status_change(row):
    """
    Detects when a flight status changes between two polls.
    Examples: Scheduled -> Estimated, Estimated -> Landed, etc.
    Returns an event dict if a change is detected, else None.
    """
    flight_number = row["flight_number"]
    if not flight_number:
        return None

    current_status = row["status"]
    previous       = state_cache.get(flight_number)

    event = None

    if previous is not None and previous["status"] != current_status:
        prev_status = previous["status"] or ""
        curr_status = current_status or ""

        # Determine event type from status text
        if "land" in curr_status.lower() or "arrived" in curr_status.lower():
            event_type = "landed"
        elif "departed" in curr_status.lower() or "airborne" in curr_status.lower():
            event_type = "departed"
        elif "delay" in curr_status.lower():
            event_type = "delayed"
        elif "cancel" in curr_status.lower():
            event_type = "cancelled"
        else:
            event_type = "status_change"

        event = {
            "event_id":        str(uuid.uuid4()),
            "flight_number":   flight_number,
            "flight_type":     row.get("flight_type"),
            "airline_icao":    row.get("airline_icao"),
            "airline_name":    row.get("airline_name"),
            "aircraft_code":   row.get("aircraft_code"),
            "origin_iata":     row.get("origin_iata"),
            "destination_iata": row.get("destination_iata"),
            "event_type":      event_type,
            "status_before":   prev_status,
            "status_after":    curr_status,
            "event_time":      row["snapshot_time"],
        }

        logger.info(
            "STATUS CHANGE  %s: [%s] -> [%s] (%s)",
            flight_number, prev_status, curr_status, event_type
        )

    # Update cache
    state_cache[flight_number] = {
        "status":    current_status,
        "last_seen": row["snapshot_time"],
    }

    return event


# ── Batch writer ──────────────────────────────────────────────────────────────

class BatchWriter(object):
    """Buffers rows and flushes to BigQuery in batches."""

    def __init__(self, client, table_id, batch_size=BATCH_SIZE):
        self._client     = client
        self._table_id   = table_id
        self._batch_size = batch_size
        self._buffer     = []
        self.total       = 0

    def add(self, row):
        self._buffer.append(row)
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self):
        if not self._buffer:
            return
        errors = self._client.insert_rows_json(self._table_id, self._buffer)
        if errors:
            logger.error("BigQuery insert errors (%s): %s", self._table_id, errors[:2])
        else:
            self.total += len(self._buffer)
        self._buffer = []


# ── Main consumer loop ────────────────────────────────────────────────────────

def run():
    bq         = bigquery.Client(project=PROJECT_ID)
    sub_path   = "projects/{}/subscriptions/{}".format(PROJECT_ID, SUBSCRIPTION_ID)
    subscriber = pubsub_v1.SubscriberClient()

    raw_writer    = BatchWriter(bq, RAW_TABLE)
    events_writer = BatchWriter(bq, EVENTS_TABLE)
    processed     = 0

    def handle_message(message):
        nonlocal processed

        try:
            payload = json.loads(message.data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("Bad message payload: %s", exc)
            message.nack()
            return

        row   = coerce_row(payload, message.message_id)
        event = detect_status_change(row)

        raw_writer.add(row)
        if event:
            events_writer.add(event)

        message.ack()
        processed += 1

        if processed % 100 == 0:
            logger.info(
                "Processed %d messages | raw=%d | events=%d | flights_tracked=%d",
                processed, raw_writer.total, events_writer.total, len(state_cache),
            )

    logger.info("Orly Live Consumer starting")
    logger.info("Project: %s | Subscription: %s", PROJECT_ID, SUBSCRIPTION_ID)
    logger.info("Writing raw    -> %s", RAW_TABLE)
    logger.info("Writing events -> %s", EVENTS_TABLE)

    future = subscriber.subscribe(sub_path, callback=handle_message)
    logger.info("Listening... Ctrl+C to stop.")

    with subscriber:
        try:
            future.result()
        except KeyboardInterrupt:
            future.cancel()
            raw_writer.flush()
            events_writer.flush()
            logger.info(
                "Consumer stopped. raw=%d events=%d flights_tracked=%d",
                raw_writer.total, events_writer.total, len(state_cache),
            )


if __name__ == "__main__":
    run()
