-- models/staging/stg_raw_flights.sql
-- Staging view: cleans and enriches raw flight data from FlightRadar24 airport endpoint

{{ config(materialized='view') }}

SELECT
    flight_number,
    LOWER(TRIM(flight_type))                        AS flight_type,

    -- Airline
    TRIM(airline_name)                              AS airline_name,
    UPPER(TRIM(airline_icao))                       AS airline_icao,
    UPPER(TRIM(airline_iata))                       AS airline_iata,

    -- Aircraft
    UPPER(TRIM(aircraft_code))                      AS aircraft_code,
    UPPER(TRIM(registration))                       AS registration,

    -- Route
    UPPER(TRIM(origin_iata))                        AS origin_iata,
    origin_terminal,
    origin_gate,
    UPPER(TRIM(destination_iata))                   AS destination_iata,
    dest_terminal,
    dest_gate,

    -- Schedules
    CAST(scheduled_departure  AS TIMESTAMP)         AS scheduled_departure,
    CAST(scheduled_arrival    AS TIMESTAMP)         AS scheduled_arrival,
    CAST(real_departure       AS TIMESTAMP)         AS real_departure,
    CAST(real_arrival         AS TIMESTAMP)         AS real_arrival,
    CAST(estimated_departure  AS TIMESTAMP)         AS estimated_departure,
    CAST(estimated_arrival    AS TIMESTAMP)         AS estimated_arrival,

    -- Derived: is the flight delayed?
    CASE
        WHEN LOWER(status) LIKE '%delay%'                   THEN TRUE
        WHEN estimated_departure IS NOT NULL
         AND scheduled_departure IS NOT NULL
         AND TIMESTAMP_DIFF(
               CAST(estimated_departure AS TIMESTAMP),
               CAST(scheduled_departure AS TIMESTAMP),
               MINUTE
             ) > 15                                         THEN TRUE
        ELSE FALSE
    END                                             AS is_delayed,

    -- Derived: delay in minutes (departures)
    CASE
        WHEN estimated_departure IS NOT NULL
         AND scheduled_departure IS NOT NULL
        THEN TIMESTAMP_DIFF(
               CAST(estimated_departure AS TIMESTAMP),
               CAST(scheduled_departure AS TIMESTAMP),
               MINUTE
             )
        ELSE NULL
    END                                             AS delay_minutes,

    -- Status
    TRIM(status)                                    AS status,

    -- Meta
    CAST(snapshot_time AS TIMESTAMP)                AS snapshot_time,
    DATE(snapshot_time)                             AS snapshot_date,
    EXTRACT(HOUR FROM snapshot_time)                AS snapshot_hour

FROM {{ source('paris_orly', 'raw_flights') }}
WHERE
    flight_number IS NOT NULL
    AND snapshot_time IS NOT NULL
