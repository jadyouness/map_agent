"""OpenRouteService helper server (routing, distance, POIs)."""
import os, requests
from part2_implementation.mcp_base import MCPCommand
from dotenv import load_dotenv

# Load .env from the part2_implementation folder explicitly, then any default .env
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # .../part2_implementation
load_dotenv(os.path.join(_BASE_DIR, ".env"))
load_dotenv()
ORS_KEY = os.getenv("ORS_API_KEY")

class ORSServer:
    """
    Simulated MCPServer for OpenRouteService (routing, distance, nearby)
    """

    async def route(self, origin: list, destination: list, profile: str = "driving-car"):
        """Compute driving route and duration.

        Returns an error dict instead of raising if API/key issues occur.
        """
        if not ORS_KEY:
            return {"error": "Missing ORS_API_KEY. Add it to part2_implementation/.env or environment."}

        url = f"https://api.openrouteservice.org/v2/directions/{profile}"
        try:
            r = requests.post(
                url,
                headers={"Authorization": ORS_KEY, "Content-Type": "application/json"},
                json={"coordinates": [origin, destination]},
                timeout=30,
            )
        except requests.RequestException as e:
            return {"error": "Network error contacting ORS", "detail": str(e)}

        # Try to parse JSON, but be robust to non-JSON responses
        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text}

        if not r.ok:
            return {"error": f"ORS HTTP {r.status_code}", "detail": data}

        # ORS can return either GeoJSON-like (features[..].properties.summary)
        # or plain JSON (routes[..].summary). Support both.
        try:
            s = data["features"][0]["properties"]["summary"]
            segments_src = data["features"][0]["properties"].get("segments", [])
        except (KeyError, IndexError, TypeError):
            try:
                route0 = data["routes"][0]
                s = route0["summary"]
                segments_src = route0.get("segments", [])
            except (KeyError, IndexError, TypeError):
                return {"error": "Unexpected ORS response format", "detail": data}

        # Compute cumulative totals and extract readable steps
        cumulative_distance_m = None
        cumulative_duration_s = None
        steps_list = None
        try:
            segments = segments_src or []
            if segments:
                cumulative_distance_m = sum(float(seg.get("distance", 0.0)) for seg in segments)
                cumulative_duration_s = sum(float(seg.get("duration", 0.0)) for seg in segments)
                steps_list = []
                for seg in segments:
                    for st in seg.get("steps", []) or []:
                        steps_list.append({
                            "instruction": st.get("instruction"),
                            "name": st.get("name"),
                            "distance_m": st.get("distance"),
                            "duration_s": st.get("duration"),
                            "type": st.get("type"),
                        })
        except Exception:
            pass

        try:
            dist_km = round(float(s["distance"]) / 1000, 2)
            dur_min = round(float(s["duration"]) / 60, 1)
            out = {"distance_km": dist_km, "duration_min": dur_min}
            if cumulative_distance_m is not None:
                out["cumulative_distance_km"] = round(cumulative_distance_m / 1000, 2)
            if cumulative_duration_s is not None:
                out["cumulative_duration_min"] = round(cumulative_duration_s / 60, 1)
            if steps_list is not None:
                out["steps"] = steps_list
            return out
        except (KeyError, TypeError, ValueError):
            # Fall back to cumulative if summary missing
            if cumulative_distance_m is not None:
                out = {"distance_km": round(cumulative_distance_m / 1000, 2)}
                if cumulative_duration_s is not None:
                    out["duration_min"] = round(cumulative_duration_s / 60, 1)
                if steps_list is not None:
                    out["steps"] = steps_list
                return out
            return {"error": "Missing distance/duration in ORS summary", "detail": s}

    async def distance(self, origin: list, destination: list):
        """Shortcut for route distance only"""
        result = await self.route(origin, destination)
        # Pass through errors or unexpected formats gracefully
        try:
            if isinstance(result, dict) and "distance_km" in result:
                return {"distance_km": result["distance_km"]}
            return result
        except Exception:
            return {"error": "Unexpected distance computation error", "detail": result}

    async def nearby(self, lat: float, lon: float):
        """Find nearby POIs within small bbox"""
        url = "https://api.openrouteservice.org/pois"
        body = {
            "request": "pois",
            "geometry": {
                "bbox": [[lon - 0.01, lat - 0.01], [lon + 0.01, lat + 0.01]]
            }
        }
        r = requests.post(
            url,
            headers={"Authorization": ORS_KEY, "Content-Type": "application/json"},
            json=body,
        )
        return r.json()

    @property
    def server_params(self):
        return [
            MCPCommand("route", ["origin", "destination", "profile"], "Route with summary"),
            MCPCommand("distance", ["origin", "destination"], "Distance only"),
            MCPCommand("nearby", ["lat", "lon"], "Nearby POIs"),
        ]
