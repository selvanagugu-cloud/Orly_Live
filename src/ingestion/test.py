from FlightRadarAPI import FlightRadar24API

fr = FlightRadar24API()

# Test 1 — bounds string direct
bounds = "49.2233,48.2233,1.8794,2.8794"
flights = fr.get_flights(bounds=bounds)
print(f"Test 1 (bounds string): {len(flights)} flights")

# Test 2 — sans bounds, toute la France
flights_all = fr.get_flights()
print(f"Test 2 (no bounds): {len(flights_all)} flights")
if flights_all:
    f = flights_all[0]
    print(f"  Sample: {f.callsign} lat={f.latitude} lon={f.longitude}")

# Test 3 — avec get_bounds_by_point
bounds2 = fr.get_bounds_by_point(48.7233, 2.3794, 50000)
print(f"Test 3 (bounds object): {bounds2}")
flights2 = fr.get_flights(bounds=bounds2)
print(f"Test 3 result: {len(flights2)} flights")