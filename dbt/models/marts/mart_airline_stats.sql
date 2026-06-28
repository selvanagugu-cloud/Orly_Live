-- models/marts/mart_airline_stats.sql
-- DATA PRODUCT: airline activity summary for the last 24 hours at Orly

{{ config(materialized='table') }}

SELECT
    airline_icao,
    airline_name,
    COUNT(DISTINCT flight_number)           AS total_flights,
    COUNTIF(flight_type = 'departure')      AS departures,
    COUNTIF(flight_type = 'arrival')        AS arrivals,
    COUNTIF(is_delayed = TRUE)              AS delayed_flights,
    ROUND(
        COUNTIF(is_delayed = TRUE) * 100.0
        / NULLIF(COUNT(DISTINCT flight_number), 0),
        1
    )                                       AS delay_rate_pct,
    ROUND(AVG(delay_minutes))               AS avg_delay_minutes,
    MAX(delay_minutes)                      AS max_delay_minutes,
    COUNT(DISTINCT destination_iata)        AS unique_destinations,
    COUNT(DISTINCT aircraft_code)           AS aircraft_types,
    MAX(snapshot_time)                      AS last_seen,
    CURRENT_TIMESTAMP()                     AS computed_at
FROM {{ ref('stg_raw_flights') }}
WHERE
    snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    AND airline_icao IS NOT NULL
GROUP BY 1, 2
ORDER BY total_flights DESC
