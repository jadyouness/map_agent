"""OpenStreetMap helper server (geocode, reverse, POI)."""
import os
import requests
from part2_implementation.mcp_base import MCPCommand

class OSMServer:
    """
    Simulated MCPServer for OpenStreetMap (geocoding, reverse, POI search)
    """

    async def geocode(self, place: str):
        """Get coordinates from a place name (robust to network errors)."""
        url = "https://nominatim.openstreetmap.org/search"
        # Ask only for one result; allow optional country bias; keep request lean
        params = {"q": place, "format": "json", "limit": 1, "addressdetails": 0}
        countrycodes = os.getenv("OSM_COUNTRYCODES")
        if countrycodes:
            params["countrycodes"] = countrycodes

        # Allow overriding UA via env (Nominatim requires a meaningful UA)
        ua = os.getenv("OSM_USER_AGENT", "C5-MapAgent (educational)")
        headers = {"User-Agent": ua}

        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException as e:
            return {"error": "Network error contacting Nominatim", "detail": str(e), "place": place}

        if not r.ok:
            # Surface HTTP error body when possible
            text = None
            try:
                text = r.text
            except Exception:
                pass
            return {"error": f"Nominatim HTTP {r.status_code}", "detail": text, "place": place}

        try:
            data = r.json()
        except ValueError:
            return {"error": "Nominatim returned non-JSON response", "place": place}

        if not data:
            return {"error": f"No results for {place}"}

        d = data[0]
        return {
            "place": place,
            "lat": d.get("lat"),
            "lon": d.get("lon"),
            "display": d.get("display_name"),
        }

    async def reverse(self, lat: float, lon: float):
        """Get address from coordinates"""
        url = "https://nominatim.openstreetmap.org/reverse"
        r = requests.get(url, params={"lat": lat, "lon": lon, "format": "json"},
                         headers={"User-Agent": "C5-MapAgent"})
        return {"address": r.json().get("display_name", "Unknown")}

    async def search_poi(self, query: str, city: str, max_count: int = 5):
        """Find POIs by keyword + city.

        Uses Nominatim text search but filters results to relevant healthcare
        features (e.g., hospitals/clinics) when the query suggests it.
        """
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": f"{query}, {city}", "format": "json"}
        countrycodes = os.getenv("OSM_COUNTRYCODES")
        if countrycodes:
            params["countrycodes"] = countrycodes
        r = requests.get(
            url,
            params=params,
            headers={"User-Agent": "C5-MapAgent"},
        )

        try:
            n = int(max_count)
        except Exception:
            n = 5
        n = 1 if n <= 0 else (20 if n > 20 else n)

        results = r.json() or []

        # Heuristic filtering: when user asks for hospitals/clinics, prefer
        # OSM objects tagged as amenity/healthcare with hospital/clinic types.
        q_lower = (query or "").lower()
        wants_hospitals = any(k in q_lower for k in ("hospital", "hospitals", "clinic", "clinics"))

        def is_healthcare(x: dict) -> bool:
            cls = x.get("class") or ""
            typ = x.get("type") or ""
            if cls in ("amenity", "healthcare") and typ in (
                "hospital",
                "clinic",
                "doctors",
                "health_centre",
            ):
                return True
            # Fallback: detect common words in name/display (English/Arabic)
            name = (x.get("display_name") or "").lower()
            if any(w in name for w in ("hospital", "clinic", "مستشفى")):
                return True
            return False

        filtered = results
        if wants_hospitals:
            filtered = [x for x in results if is_healthcare(x)] or results

        # Truncate to requested count and normalize fields
        out = [
            {"name": x.get("display_name"), "lat": x.get("lat"), "lon": x.get("lon")}
            for x in filtered[:n]
        ]
        return out

    @property
    def server_params(self):
        return [
            MCPCommand("geocode", ["place"], "Geocode a place name"),
            MCPCommand("reverse", ["lat", "lon"], "Reverse geocode coordinates"),
            MCPCommand("search_poi", ["query", "city"], "Search POIs in a city"),
        ]
