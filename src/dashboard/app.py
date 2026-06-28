import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from processing.airline_mapper import get_airline

st.set_page_config(
    page_title="Orly Live",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0d1117; }
  [data-testid="stHeader"]           { background: transparent; }
  [data-testid="stSidebar"]          { background: #0d1117; border-right: 1px solid #21262d; }
  .block-container { padding-top: 1.5rem; }

  .kpi { background: #161b22; border: 1px solid #21262d; border-radius: 8px;
         padding: 18px 16px; text-align: center; }
  .kpi-val { font-size: 36px; font-weight: 700; color: #e6edf3; line-height: 1; }
  .kpi-lbl { font-size: 11px; color: #8b949e; text-transform: uppercase;
              letter-spacing: 1.2px; margin-top: 6px; }

  .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
               background: #3fb950; margin-right: 6px;
               animation: blink 1.4s ease-in-out infinite; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

  .tvf-highlight { background: #0d2137 !important; border-left: 3px solid #006DB7; }

  table { border-collapse: collapse; width: 100%; }
  th { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px;
       padding: 8px 12px; border-bottom: 1px solid #21262d; text-align: left; }
  td { font-size: 13px; color: #c9d1d9; padding: 9px 12px;
       border-bottom: 1px solid #161b22; vertical-align: middle; }
  tr:hover td { background: #161b22; }

  .badge { display:inline-block; font-size:11px; font-weight:600; padding:2px 8px; border-radius:20px; }
  .badge-ok     { background:#0d3a1c; color:#3fb950; }
  .badge-delay  { background:#3a2a00; color:#d29922; }
  .badge-cancel { background:#3a1c0d; color:#f78166; }
  .badge-sched  { background:#1c1c2e; color:#8b949e; }

  img.logo { height: 20px; vertical-align: middle; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_bq():
    from google.cloud import bigquery
    pid = os.environ.get("GCP_PROJECT_ID")
    if not pid:
        st.error("Set GCP_PROJECT_ID environment variable.")
        st.stop()
    return bigquery.Client(project=pid)


PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
DS_DBT     = "paris_orly_dbt"
DS_RAW     = "paris_orly"


def build_departures_query(tvf_only=False):
    where = "flight_type = 'departure' AND snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)"
    if tvf_only:
        where += " AND airline_icao = 'TVF'"
    return """
    SELECT flight_number, airline_name, airline_icao, aircraft_code,
           destination_iata, origin_terminal AS terminal, origin_gate AS gate,
           scheduled_departure, estimated_departure, real_departure,
           delay_minutes, is_delayed, status, snapshot_time
    FROM `{p}.{ds}.mart_live_board`
    WHERE {w}
    ORDER BY COALESCE(estimated_departure, scheduled_departure)
    LIMIT 60
    """.format(p=PROJECT_ID, ds=DS_DBT, w=where)


def build_arrivals_query(tvf_only=False):
    where = "flight_type = 'arrival' AND snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)"
    if tvf_only:
        where += " AND airline_icao = 'TVF'"
    return """
    SELECT flight_number, airline_name, airline_icao, aircraft_code,
           origin_iata, dest_terminal AS terminal, dest_gate AS gate,
           scheduled_arrival, estimated_arrival, real_arrival,
           delay_minutes, is_delayed, status, snapshot_time
    FROM `{p}.{ds}.mart_live_board`
    WHERE {w}
    ORDER BY COALESCE(estimated_arrival, scheduled_arrival)
    LIMIT 60
    """.format(p=PROJECT_ID, ds=DS_DBT, w=where)


Q_STATS_TPL = """
SELECT
    COUNT(DISTINCT flight_number)          AS total_flights,
    COUNTIF(flight_type = 'departure')     AS departures,
    COUNTIF(flight_type = 'arrival')       AS arrivals,
    COUNTIF(is_delayed = TRUE)             AS delayed,
    COUNT(DISTINCT airline_icao)           AS airlines,
    COUNT(DISTINCT destination_iata)       AS destinations
FROM `{p}.{ds}.mart_live_board`
WHERE snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR){extra}
"""

Q_EVENTS = """
SELECT event_type, flight_number, airline_name,
       origin_iata, destination_iata, status_before, status_after, event_time
FROM `{p}.{ds}.flight_events`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 HOUR)
ORDER BY event_time DESC LIMIT 30
""".format(p=PROJECT_ID, ds=DS_RAW)

Q_AIRLINE_STATS = """
SELECT airline_icao, airline_name, total_flights, departures, arrivals,
       delayed_flights, delay_rate_pct, avg_delay_minutes, unique_destinations
FROM `{p}.{ds}.mart_airline_stats`
ORDER BY total_flights DESC LIMIT 12
""".format(p=PROJECT_ID, ds=DS_DBT)

Q_MAP_FLIGHTS = """
SELECT DISTINCT
    flight_number, airline_name, airline_icao,
    origin_iata, destination_iata, status
FROM `{p}.{ds}.mart_live_board`
WHERE snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
""".format(p=PROJECT_ID, ds=DS_DBT)


@st.cache_data(ttl=12)
def load_departures(tvf_only=False):
    try:
        return get_bq().query(build_departures_query(tvf_only)).to_dataframe()
    except Exception as e:
        st.warning("BigQuery: {}".format(e))
        return pd.DataFrame()


@st.cache_data(ttl=12)
def load_arrivals(tvf_only=False):
    try:
        return get_bq().query(build_arrivals_query(tvf_only)).to_dataframe()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=12)
def load_stats(tvf_only=False):
    extra = " AND airline_icao = 'TVF'" if tvf_only else ""
    q = Q_STATS_TPL.format(p=PROJECT_ID, ds=DS_DBT, extra=extra)
    try:
        rows = list(get_bq().query(q).result())
        r = rows[0] if rows else None
        if r:
            return {k: int(getattr(r, k) or 0) for k in
                    ["total_flights","departures","arrivals","delayed","airlines","destinations"]}
    except Exception:
        pass
    return {k: 0 for k in ["total_flights","departures","arrivals","delayed","airlines","destinations"]}


@st.cache_data(ttl=20)
def load_events():
    try:
        return get_bq().query(Q_EVENTS).to_dataframe()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def load_airline_stats():
    try:
        return get_bq().query(Q_AIRLINE_STATS).to_dataframe()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def load_map_flights():
    try:
        return get_bq().query(Q_MAP_FLIGHTS).to_dataframe()
    except Exception:
        return pd.DataFrame()


def safe_val(val, default="—"):
    try:
        if pd.isna(val):
            return default
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s if s and s != "None" else default


def fmt_time(val):
    try:
        if pd.isna(val):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(val).strftime("%H:%M")
    except Exception:
        return "—"


def status_badge(status, is_delayed):
    s = (status or "").lower()
    if "cancel" in s:
        css = "badge-cancel"
    elif is_delayed or "delay" in s:
        css = "badge-delay"
    elif "land" in s or "arriv" in s or "departed" in s:
        css = "badge-ok"
    else:
        css = "badge-sched"
    return '<span class="badge {}">{}</span>'.format(css, safe_val(status, "Scheduled")[:30])


def logo_img(airline_icao):
    info = get_airline(safe_val(airline_icao, None))
    url  = info.get("logo")
    if url:
        return '<img class="logo" src="{}" onerror="this.style.display=\'none\'">'.format(url)
    return "✈️ "


def render_flight_table(df, columns, headers, highlight_tvf=False):
    if df.empty:
        return "<p style='color:#8b949e;padding:16px'>No data — make sure the poller is running.</p>"

    rows = ""
    for _, r in df.iterrows():
        is_delayed = False
        try:
            is_delayed = bool(r.get("is_delayed")) if not pd.isna(r.get("is_delayed")) else False
        except (TypeError, ValueError):
            pass

        is_tvf = safe_val(r.get("airline_icao"), "") == "TVF"
        row_cls = ' class="tvf-highlight"' if (highlight_tvf and is_tvf) else ""

        cells = ""
        for col in columns:
            if col == "_logo_airline":
                icao = safe_val(r.get("airline_icao"), None)
                name = safe_val(r.get("airline_name"))
                cells += "<td>{}{}</td>".format(logo_img(icao), name)
            elif col == "_status":
                cells += "<td>{}</td>".format(status_badge(r.get("status"), is_delayed))
            elif col == "_delay":
                try:
                    dm = int(r["delay_minutes"]) if not pd.isna(r.get("delay_minutes")) else None
                except (TypeError, ValueError):
                    dm = None
                cells += "<td>{}</td>".format("+{}min".format(dm) if dm and dm > 0 else "—")
            elif col in ("scheduled_departure","scheduled_arrival",
                         "estimated_departure","estimated_arrival",
                         "real_departure","real_arrival"):
                cells += "<td>{}</td>".format(fmt_time(r.get(col)))
            else:
                cells += "<td>{}</td>".format(safe_val(r.get(col)))

        rows += "<tr{}>{}</tr>".format(row_cls, cells)

    ths = "".join("<th>{}</th>".format(h) for h in headers)
    return "<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>".format(ths, rows)


AIRPORT_COORDS = {
    "ORY": (48.7233, 2.3794), "CDG": (49.0097, 2.5479), "LHR": (51.4700, -0.4543),
    "AMS": (52.3086, 4.7639), "MAD": (40.4936, -3.5668), "BCN": (41.2971, 2.0785),
    "FCO": (41.8003, 12.2389), "LIS": (38.7756, -9.1354), "DUB": (53.4213, -6.2700),
    "VLC": (39.4893, -0.4816), "ALC": (38.2822, -0.5582), "PMI": (39.5517, 2.7388),
    "AGP": (36.6749, -4.4991), "ACE": (28.9455, -13.6052), "FUE": (28.4527, -13.8638),
    "TUN": (36.8510, 10.2272), "ALG": (36.6910, 3.2154), "CMN": (33.3675, -7.5898),
    "RAK": (31.6069, -8.0363), "ATH": (37.9364, 23.9445), "ZTH": (37.7509, 20.8843),
    "HER": (35.3397, 25.1803), "HRG": (27.1783, 33.7994), "MPL": (43.5762, 3.9630),
    "MRS": (43.4365, 5.2214), "TLS": (43.6293, 1.3678), "NCE": (43.6584, 7.2159),
    "BIQ": (43.4683, -1.5233), "TLN": (43.0997, 6.1463), "LDE": (43.1787, -0.0059),
    "PTP": (16.2653, -61.5317), "FDF": (14.5910, -61.0032), "RUN": (-20.8871, 55.5103),
    "ABJ": (5.2613, -3.9262), "EWR": (40.6895, -74.1745), "LDE": (43.1787, -0.0059),
    "IST": (41.2753, 28.7519), "DXB": (25.2532, 55.3657), "BVA": (49.4544, 2.1128),
    "MAH": (39.8626, 4.2186), "OPO": (41.2481, -8.6814), "DBV": (42.5614, 18.2682),
    "MXP": (45.6306, 8.7281), "NAP": (40.8860, 14.2908), "CAG": (39.2515, 9.0543),
    "AJA": (41.9234, 8.8029), "BIA": (42.5527, 9.4839),
}


def render_europe_map(df_map, tvf_only=False):
    if df_map.empty:
        st.info("No flight route data yet.")
        return

    if tvf_only:
        df_map = df_map[df_map["airline_icao"] == "TVF"]

    routes = []
    for _, r in df_map.iterrows():
        orig = safe_val(r.get("origin_iata"), None)
        dest = safe_val(r.get("destination_iata"), None)
        if not orig or not dest:
            continue
        orig_coords = AIRPORT_COORDS.get(orig)
        dest_coords = AIRPORT_COORDS.get(dest)
        if not orig_coords or not dest_coords:
            continue
        routes.append({
            "flight": safe_val(r.get("flight_number")),
            "airline": safe_val(r.get("airline_name")),
            "is_tvf": safe_val(r.get("airline_icao")) == "TVF",
            "orig": orig, "orig_lat": orig_coords[0], "orig_lon": orig_coords[1],
            "dest": dest, "dest_lat": dest_coords[0], "dest_lon": dest_coords[1],
        })

    if not routes:
        st.info("No routes with known coordinates. Routes expand as data accumulates.")
        return

    points = []
    for route in routes:
        color = [0, 109, 183, 200] if route["is_tvf"] else [180, 180, 180, 80]
        mid_lat = (route["orig_lat"] + route["dest_lat"]) / 2
        mid_lon = (route["orig_lon"] + route["dest_lon"]) / 2
        points.append({
            "lat": route["orig_lat"], "lon": route["orig_lon"],
            "label": "{} ({})".format(route["orig"], route["flight"]),
            "color": color,
        })
        points.append({
            "lat": route["dest_lat"], "lon": route["dest_lon"],
            "label": "{} -> {}".format(route["orig"], route["dest"]),
            "color": color,
        })
        points.append({
            "lat": mid_lat, "lon": mid_lon,
            "label": "{} {} -> {}".format(route["flight"], route["orig"], route["dest"]),
            "color": color,
        })

    df_points = pd.DataFrame(points)

    st.map(
        df_points,
        latitude="lat",
        longitude="lon",
        color="color",
        size=50,
        zoom=3,
    )

    tvf_count = sum(1 for r in routes if r["is_tvf"])
    other_count = len(routes) - tvf_count
    st.caption(
        "🔵 {} Transavia routes   ⚪ {} other routes   "
        "Coverage limited to airports in the coordinates database.".format(tvf_count, other_count)
    )


def main():
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    with st.sidebar:
        st.markdown("### ✈️ Orly Live")
        st.markdown("---")
        tvf_only = st.toggle("🔵 Transavia only", value=False,
                             help="Filter all views to show only Transavia (TVF) flights")
        if tvf_only:
            st.markdown(
                '<div style="background:#0d2137;border:1px solid #006DB7;border-radius:6px;'
                'padding:10px;font-size:12px;color:#58a6ff">'
                '<b>Transavia filter active</b><br>Showing TVF flights only across all tabs.'
                '</div>',
                unsafe_allow_html=True,
            )
        st.markdown("---")
        st.markdown(
            '<div style="font-size:11px;color:#8b949e">'
            'Source: FlightRadar24<br>'
            'Refresh: every 15s<br>'
            'Airport: Paris Orly (LFPO)'
            '</div>',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            '<h1 style="color:#e6edf3;margin:0">✈️ Orly Live</h1>'
            '<p style="color:#8b949e;margin-top:4px">'
            '<span class="live-dot"></span>'
            'Paris Orly (LFPO) · {} · FlightRadar24 + GCP BigQuery'
            '</p>'.format(now),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div style="text-align:right;padding-top:20px">'
            '<span style="font-size:11px;color:#8b949e;font-family:monospace">'
            'auto-refresh 15s'
            '</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#21262d;margin:8px 0 20px'>", unsafe_allow_html=True)

    stats = load_stats(tvf_only)
    cols  = st.columns(6)
    kpis  = [
        (stats["total_flights"], "Total Flights"),
        (stats["departures"],    "🛫 Departures"),
        (stats["arrivals"],      "🛬 Arrivals"),
        (stats["delayed"],       "⏰ Delayed"),
        (stats["airlines"],      "🏢 Airlines"),
        (stats["destinations"],  "🌍 Destinations"),
    ]
    for col, (val, lbl) in zip(cols, kpis):
        with col:
            st.markdown(
                '<div class="kpi"><div class="kpi-val">{}</div>'
                '<div class="kpi-lbl">{}</div></div>'.format(val, lbl),
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    tab_dep, tab_arr, tab_map, tab_airlines, tab_events = st.tabs(
        ["🛫 Departures", "🛬 Arrivals", "🗺 Map", "🏢 Airlines", "⚡ Events"]
    )

    with tab_dep:
        df = load_departures(tvf_only)
        st.markdown(render_flight_table(
            df,
            columns=["flight_number", "_logo_airline", "aircraft_code",
                     "destination_iata", "terminal", "gate",
                     "scheduled_departure", "estimated_departure", "_delay", "_status"],
            headers=["Flight", "Airline", "Aircraft", "To", "Term.", "Gate",
                     "Sched.", "Estim.", "Delay", "Status"],
            highlight_tvf=not tvf_only,
        ), unsafe_allow_html=True)

    with tab_arr:
        df = load_arrivals(tvf_only)
        st.markdown(render_flight_table(
            df,
            columns=["flight_number", "_logo_airline", "aircraft_code",
                     "origin_iata", "terminal", "gate",
                     "scheduled_arrival", "estimated_arrival", "_delay", "_status"],
            headers=["Flight", "Airline", "Aircraft", "From", "Term.", "Gate",
                     "Sched.", "Estim.", "Delay", "Status"],
            highlight_tvf=not tvf_only,
        ), unsafe_allow_html=True)

    with tab_map:
        if tvf_only:
            st.markdown(
                '<p style="color:#58a6ff;font-size:13px">🔵 Showing Transavia routes only</p>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<p style="color:#8b949e;font-size:13px">'
                '🔵 Transavia routes highlighted · ⚪ other airlines</p>',
                unsafe_allow_html=True,
            )
        df_map = load_map_flights()
        render_europe_map(df_map, tvf_only=tvf_only)

    with tab_airlines:
        df_al = load_airline_stats()
        if df_al.empty:
            st.info("Accumulating data — check back in a few minutes.")
        else:
            if tvf_only:
                df_al = df_al[df_al["airline_icao"] == "TVF"]
            for _, row in df_al.iterrows():
                icao = safe_val(row.get("airline_icao"), None)
                info = get_airline(icao)
                c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                with c1:
                    logo = info.get("logo")
                    if logo:
                        st.image(logo, width=70)
                    else:
                        st.write("✈️")
                with c2:
                    name = safe_val(row.get("airline_name"), info["name"])
                    st.markdown("**{}**  \n`{}` · {}".format(name, icao or "—", info["country"]))
                with c3:
                    st.metric("Flights", int(row.get("total_flights") or 0))
                    st.metric("Delayed", "{}%".format(safe_val(row.get("delay_rate_pct"), "0")))
                with c4:
                    st.metric("Avg delay", "{} min".format(int(row.get("avg_delay_minutes") or 0)))
                    st.metric("Destinations", int(row.get("unique_destinations") or 0))
                st.markdown("<hr style='border-color:#21262d;margin:6px 0'>", unsafe_allow_html=True)

    with tab_events:
        df_ev = load_events()
        if df_ev.empty:
            st.info("No status change events yet.")
        else:
            if tvf_only:
                df_ev = df_ev[df_ev["airline_name"].str.contains("Transavia", na=False)]
            df_ev["event_time"] = pd.to_datetime(df_ev["event_time"]).dt.strftime("%H:%M:%S")
            df_ev["event_type"] = df_ev["event_type"].map({
                "departed": "🛫 Departed", "landed": "🛬 Landed",
                "delayed": "⏰ Delayed", "cancelled": "❌ Cancelled",
                "status_change": "🔄 Status change",
            }).fillna(df_ev["event_type"])
            st.dataframe(
                df_ev[["event_time","flight_number","airline_name","origin_iata",
                        "destination_iata","event_type","status_before","status_after"]],
                use_container_width=True, hide_index=True,
            )

    time.sleep(15)
    st.rerun()


if __name__ == "__main__":
    main()
