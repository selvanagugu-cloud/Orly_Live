"""
Orly Live — Flight Poller
Fetches real departures and arrivals from Paris Orly (LFPO)
via FlightRadar24API airport endpoint, then publishes each
flight as a Pub/Sub message.

Source: FlightRadarAPI (JeanExtreme002)
  pip install FlightRadarAPI

Usage:
    export GCP_PROJECT_ID=
    python src/ingestion/poller.py
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

from FlightRadarAPI import FlightRadar24API
from google.cloud import pubsub_v1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("orly.poller")

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID    = os.environ["GCP_PROJECT_ID"]
TOPIC_ID      = "orly-flights"
POLL_INTERVAL = 30      # secondes — l'API airport ne change pas plus vite
AIRPORT_ICAO  = "LFPO"  # Paris Orly


# ── Extraction depuis la structure airport.departures/arrivals ────────────────

def extract_flight(item, flight_type, snapshot_time):
    """
    Extrait les champs utiles depuis un item de departures ou arrivals.
    flight_type : "departure" ou "arrival"
    Retourne un dict propre ou None si données insuffisantes.
    """
    try:
        flight = item["flight"]

        # Identification
        number = (
            flight.get("identification", {})
                  .get("number", {})
                  .get("default")
        )
        if not number:
            return None

        # Compagnie
        airline_name = (
            flight.get("airline", {})
                  .get("name")
        )
        airline_icao = (
            flight.get("airline", {})
                  .get("code", {})
                  .get("icao")
        )
        airline_iata = (
            flight.get("airline", {})
                  .get("code", {})
                  .get("iata")
        )

        # Aéroport d'origine
        origin = flight.get("airport", {}).get("origin", {})
        origin_iata     = origin.get("code", {}).get("iata")
        origin_terminal = origin.get("info", {}).get("terminal")
        origin_gate     = origin.get("info", {}).get("gate")

        # Aéroport de destination
        dest = flight.get("airport", {}).get("destination", {})
        dest_iata     = dest.get("code", {}).get("iata")
        dest_terminal = dest.get("info", {}).get("terminal")
        dest_gate     = dest.get("info", {}).get("gate")

        # Avion
        aircraft      = flight.get("aircraft", {})
        aircraft_code = aircraft.get("model", {}).get("code")
        registration  = aircraft.get("registration")

        # Statut
        status = flight.get("status", {}).get("text")

        # Horaires
        time_data   = flight.get("time", {})
        scheduled   = time_data.get("scheduled", {})
        real        = time_data.get("real", {})
        estimated   = time_data.get("estimated", {})

        sched_dep = scheduled.get("departure")
        sched_arr = scheduled.get("arrival")
        real_dep  = real.get("departure")
        real_arr  = real.get("arrival")
        est_dep   = estimated.get("departure")
        est_arr   = estimated.get("arrival")

        return {
            "flight_number":        number,
            "flight_type":          flight_type,   # "departure" ou "arrival"
            "airline_name":         airline_name,
            "airline_icao":         airline_icao,
            "airline_iata":         airline_iata,
            "aircraft_code":        aircraft_code,
            "registration":         registration,
            # Route
            "origin_iata":          origin_iata,
            "origin_terminal":      str(origin_terminal) if origin_terminal else None,
            "origin_gate":          str(origin_gate)     if origin_gate     else None,
            "destination_iata":     dest_iata,
            "dest_terminal":        str(dest_terminal)   if dest_terminal   else None,
            "dest_gate":            str(dest_gate)       if dest_gate       else None,
            # Horaires (timestamps Unix -> ISO)
            "scheduled_departure":  datetime.fromtimestamp(sched_dep, tz=timezone.utc).isoformat() if sched_dep else None,
            "scheduled_arrival":    datetime.fromtimestamp(sched_arr, tz=timezone.utc).isoformat() if sched_arr else None,
            "real_departure":       datetime.fromtimestamp(real_dep,  tz=timezone.utc).isoformat() if real_dep  else None,
            "real_arrival":         datetime.fromtimestamp(real_arr,  tz=timezone.utc).isoformat() if real_arr  else None,
            "estimated_departure":  datetime.fromtimestamp(est_dep,   tz=timezone.utc).isoformat() if est_dep   else None,
            "estimated_arrival":    datetime.fromtimestamp(est_arr,   tz=timezone.utc).isoformat() if est_arr   else None,
            # Statut
            "status":               status,
            # Meta
            "snapshot_time":        snapshot_time,
        }

    except Exception as exc:
        logger.debug("Skipping flight item: %s", exc)
        return None


# ── Pub/Sub publish ───────────────────────────────────────────────────────────

def publish_batch(publisher, topic_path, flights):
    """Publie une liste de dicts de vols sur Pub/Sub."""
    futures = []
    for f in flights:
        data   = json.dumps(f, default=str).encode("utf-8")
        future = publisher.publish(
            topic_path,
            data,
            flight_type=f.get("flight_type", "unknown"),
            airline_icao=f.get("airline_icao") or "unknown",
        )
        futures.append(future)

    published = 0
    for future in futures:
        try:
            future.result(timeout=10)
            published += 1
        except Exception as exc:
            logger.warning("Publish failed: %s", exc)

    return published


# ── Affichage console (comme ton script de test) ──────────────────────────────

def print_board(departures, arrivals):
    """Affiche le tableau de bord dans le terminal."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 110)
    print(f"PARIS ORLY (ORY) - {now}")
    print("=" * 110)

    if departures:
        print("\n>>> DEPARTS")
        print(f"{'VOL':<10} {'COMPAGNIE':<22} {'DEST':<6} {'TER':<5} {'GATE':<6} {'STATUT'}")
        print("-" * 80)
        for f in departures[:20]:
            print(
                f"{(f['flight_number'] or ''):<10}"
                f"{(f['airline_name'] or '')[:21]:<22}"
                f"{(f['destination_iata'] or ''):<6}"
                f"{(f['origin_terminal'] or ''):<5}"
                f"{(f['origin_gate'] or ''):<6}"
                f"{f['status'] or ''}"
            )

    if arrivals:
        print("\n>>> ARRIVEES")
        print(f"{'VOL':<10} {'COMPAGNIE':<22} {'ORIG':<6} {'TER':<5} {'GATE':<6} {'STATUT'}")
        print("-" * 80)
        for f in arrivals[:20]:
            print(
                f"{(f['flight_number'] or ''):<10}"
                f"{(f['airline_name'] or '')[:21]:<22}"
                f"{(f['origin_iata'] or ''):<6}"
                f"{(f['dest_terminal'] or ''):<5}"
                f"{(f['dest_gate'] or ''):<6}"
                f"{f['status'] or ''}"
            )

    print()


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    fr_api     = FlightRadar24API()
    publisher  = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    logger.info("Orly Live Poller starting")
    logger.info("Project: %s | Topic: %s", PROJECT_ID, TOPIC_ID)
    logger.info("Airport: %s | Polling every %ds", AIRPORT_ICAO, POLL_INTERVAL)

    poll_count = 0

    while True:
        cycle_start   = time.monotonic()
        snapshot_time = datetime.now(timezone.utc).isoformat()
        poll_count   += 1

        try:
            # Appel principal — c'est cet endpoint qui fonctionne vraiment
            airport = fr_api.get_airport(AIRPORT_ICAO, details=True)

            raw_departures = airport.departures.get("data", [])
            raw_arrivals   = airport.arrivals.get("data",   [])

            # Extraire les vols
            departures = [
                f for f in (
                    extract_flight(item, "departure", snapshot_time)
                    for item in raw_departures
                )
                if f is not None
            ]
            arrivals = [
                f for f in (
                    extract_flight(item, "arrival", snapshot_time)
                    for item in raw_arrivals
                )
                if f is not None
            ]

            all_flights = departures + arrivals

            # Affichage console
            os.system("clear")
            print_board(departures, arrivals)

            # Publication Pub/Sub
            if all_flights:
                published = publish_batch(publisher, topic_path, all_flights)
                logger.info(
                    "[Poll #%d] %d dep + %d arr = %d flights -> %d published to Pub/Sub",
                    poll_count,
                    len(departures),
                    len(arrivals),
                    len(all_flights),
                    published,
                )
            else:
                logger.info("[Poll #%d] No flights returned", poll_count)

        except Exception as exc:
            logger.error("[Poll #%d] Error: %s", poll_count, exc)

        # Attendre le reste de l'intervalle
        elapsed    = time.monotonic() - cycle_start
        sleep_time = max(0.0, POLL_INTERVAL - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Poller stopped.")
