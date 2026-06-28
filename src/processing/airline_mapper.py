"""
Orly Live — Airline Mapper
Maps ICAO airline codes to display names and logo URLs.
Compatible with Python 3.8+.
"""

AIRLINES = {
    "TVF": {"name": "Transavia France",   "country": "France",         "iata": "TO", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Transavia_logo.svg/3840px-Transavia_logo.svg.png"},
    "AFR": {"name": "Air France",         "country": "France",         "iata": "AF", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Air_France_Logo.svg/3840px-Air_France_Logo.svg.png"},
    "TRA": {"name": "Transavia",          "country": "Netherlands",    "iata": "HV", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Transavia_logo.svg/3840px-Transavia_logo.svg.png"},
    "DHL": {"name": "Air Algerie",          "country": "Algeria",    "iata": "HV", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Transavia_logo.svg/3840px-Transavia_logo.svg.png"},
    "FDC": {"name": "Air Caraibes",       "country": "France",         "iata": "TX", "logo": None},
    "XKF": {"name": "Air Corsica",        "country": "France",         "iata": "XK", "logo": None},
    "XKE": {"name": "Air Europa Lineas",        "country": "France",         "iata": "XK", "logo": None},
    "XKE": {"name": "Amelia",        "country": "France",         "iata": "XK", "logo": None},
    "XKE": {"name": "ASL Airlines France SA",        "country": "France",         "iata": "XK", "logo": None},
    "XKE": {"name": "Chalair Aviation",        "country": "France",         "iata": "XK", "logo": None},
    "IBE": {"name": "Iberia",             "country": "Spain",          "iata": "IB", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/Iberia_logo.svg/200px-Iberia_logo.svg.png"},
    "XKE": {"name": "Corsair",            "country": "France",         "iata": "SS", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7f/Corsair_International_logo.svg/3840px-Corsair_International_logo.svg.png"},
    "FPO": {"name": "La Compagnie",       "country": "France",         "iata": "B0", "logo": None},
    "TAP": {"name": "TAP Air Portugal",   "country": "Portugal",       "iata": "TP", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/TAP_Air_Portugal_logo.svg/3840px-TAP_Air_Portugal_logo.svg.png"},
    "EZY": {"name": "easyJet",            "country": "United Kingdom", "iata": "U2", "logo": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSFTHhPP07rCKdpaOon-HW46V6L6d-mqiOnox4FYhYNy9qwHBV3Pm4OsQ0&s=10"},
    "RYR": {"name": "Ryanair",            "country": "Ireland",        "iata": "FR", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b4/Ryanair_Logo.svg/200px-Ryanair_Logo.svg.png"},
    "BAW": {"name": "British Airways",    "country": "United Kingdom", "iata": "BA", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/42/British_Airways_Logo.svg/200px-British_Airways_Logo.svg.png"},
    "DLH": {"name": "Lufthansa",          "country": "Germany",        "iata": "LH", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Lufthansa_Logo_2018.svg/200px-Lufthansa_Logo_2018.svg.png"},
    "KLM": {"name": "KLM",               "country": "Netherlands",    "iata": "KL", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/KLM_logo.svg/200px-KLM_logo.svg.png"},
    "VLG": {"name": "Vueling",            "country": "Spain",          "iata": "VY", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Logo_Vueling.svg/960px-Logo_Vueling.svg.png"},
    "BEL": {"name": "Brussels Airlines",  "country": "Belgium",        "iata": "SN", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Brussels_Airlines_logo_2018.svg/200px-Brussels_Airlines_logo_2018.svg.png"},
    "SWR": {"name": "Swiss",              "country": "Switzerland",    "iata": "LX", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Swiss_International_Air_Lines_Logo_2011.svg/200px-Swiss_International_Air_Lines_Logo_2011.svg.png"},
    "WZZ": {"name": "Wizz Air",           "country": "Hungary",        "iata": "W6", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Wizz_Air_logo.svg/200px-Wizz_Air_logo.svg.png"},
    "NAX": {"name": "Norwegian",          "country": "Norway",         "iata": "DY", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/Norwegian_logo.svg/200px-Norwegian_logo.svg.png"},
    "RAM": {"name": "Royal Air Maroc",    "country": "Morocco",        "iata": "AT", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Royal_Air_Maroc_Logo.svg/200px-Royal_Air_Maroc_Logo.svg.png"},
    "TAR": {"name": "Tunisair",           "country": "Tunisia",        "iata": "TU", "logo": "https://upload.wikimedia.org/wikipedia/fr/5/5c/Tunisair_%28logo%29.svg"},
    "THY": {"name": "Turkish Airlines",   "country": "Turkey",         "iata": "TK", "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Turkish_Airlines_logo_2019_compact.svg/200px-Turkish_Airlines_logo_2019_compact.svg.png"},
    "VLU": {"name": "Volotea",            "country": "Spain",          "iata": "V7", "logo": None},
    "ASL": {"name": "ASL Airlines",       "country": "France",         "iata": "5O", "logo": None},
}

_UNKNOWN = {"name": "Unknown", "country": "—", "iata": "—", "logo": None}


def get_airline(airline_icao):
    """Returns airline info dict for a given ICAO code."""
    if not airline_icao:
        return dict(_UNKNOWN)
    return AIRLINES.get(
        str(airline_icao).upper().strip(),
        dict(_UNKNOWN, name="Unknown ({})".format(airline_icao))
    )


def flight_phase(on_ground, altitude, vertical_speed):
    """
    Returns a human-readable flight phase.
    Safe against pandas NA / None values.
    Compatible with Python 3.8+.
    """
    import pandas as pd

    # Safely convert values — handles pandas NA, None, NaN
    try:
        alt = 0 if pd.isna(altitude) else int(altitude)
    except (TypeError, ValueError):
        alt = 0

    try:
        vs = 0 if pd.isna(vertical_speed) else int(vertical_speed)
    except (TypeError, ValueError):
        vs = 0

    try:
        grounded = bool(on_ground) if not pd.isna(on_ground) else False
    except (TypeError, ValueError):
        grounded = False

    if grounded:
        return "🟡 On ground"
    if alt < 1000 and vs > 100:
        return "🛫 Taking off"
    if alt < 2000 and vs < -100:
        return "🛬 On approach"
    if vs > 200:
        return "📈 Climbing"
    if vs < -200:
        return "📉 Descending"
    return "✈️  Cruising"
