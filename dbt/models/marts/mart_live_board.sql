-- models/marts/mart_live_board.sql
-- DATA PRODUCT: current state of every flight at Orly
-- Queried by the Streamlit dashboard every 15 seconds.

{{ config(
    materialized='table',
    cluster_by=["flight_type", "airline_icao"]
) }}

WITH latest AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY flight_number
            ORDER BY snapshot_time DESC
        ) AS rn
    FROM {{ ref('stg_raw_flights') }}
    WHERE snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
),
final AS (
    SELECT
        flight_number,
        flight_type,
        airline_name,
        airline_icao,
        airline_iata,
        aircraft_code,
        registration,
        origin_iata,
        origin_terminal,
        origin_gate,
        destination_iata,
        dest_terminal,
        dest_gate,
        scheduled_departure,
        scheduled_arrival,
        estimated_departure,
        estimated_arrival,
        real_departure,
        real_arrival,
        is_delayed,
        delay_minutes,
        status,
        snapshot_time,
        CURRENT_TIMESTAMP() AS computed_at
    FROM latest
    WHERE rn = 1
)
SELECT *
FROM final
