import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from part2_implementation.gemini_provider import run_with_tools as gemini_run_with_tools
from part2_implementation.servers.osm_server import OSMServer
from part2_implementation.servers.ors_server import ORSServer


# Tool schemas (Agents SDK-style via function calling)
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "osm_geocode",
            "description": "Geocode a place name to coordinates using OpenStreetMap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "place": {"type": "string", "description": "Place name to geocode"},
                },
                "required": ["place"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "osm_reverse",
            "description": "Reverse geocode coordinates to an address using OpenStreetMap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "osm_search_poi",
            "description": "Search for points of interest in a city using OpenStreetMap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "city": {"type": "string"},
                    "max_count": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["query", "city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ors_route",
            "description": "Compute a route and duration using OpenRouteService.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[lon, lat]",
                    },
                    "destination": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[lon, lat]",
                    },
                    "profile": {"type": "string", "default": "driving-car"},
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ors_distance",
            "description": "Compute distance only using OpenRouteService.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[lon, lat]",
                    },
                    "destination": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "[lon, lat]",
                    },
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ors_nearby",
            "description": "Find nearby POIs around a coordinate using OpenRouteService.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ors_distance_places",
            "description": "Compute driving distance between two place names (auto-geocodes, country bias may apply).",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_place": {"type": "string"},
                    "destination_place": {"type": "string"},
                },
                "required": ["origin_place", "destination_place"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ors_route_places",
            "description": "Compute route between two place names (auto-geocodes, driving-car).",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_place": {"type": "string"},
                    "destination_place": {"type": "string"},
                },
                "required": ["origin_place", "destination_place"],
            },
        },
    },
]


class AgentsSDKMapAssistant:
    def __init__(self):
        self.osm = OSMServer()
        self.ors = ORSServer()
        self.place_cache: Dict[str, Tuple[float, float]] = {}

    def _heuristic_route(self, prompt: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        p = prompt.lower()
        # Prefer distance tool when explicitly asked
        if "distance" in p:
            import re
            m = re.search(r"from\s+(.+?)\s+to\s+(.+)$", prompt, flags=re.IGNORECASE)
            if not m:
                m = re.search(r"between\s+(.+?)\s+and\s+(.+)$", prompt, flags=re.IGNORECASE)
            if m:
                return (
                    "ors_distance_places",
                    {"origin_place": m.group(1).strip(), "destination_place": m.group(2).strip()},
                )
            return (
                "ors_distance",
                {"origin": [35.5018, 33.8938], "destination": [35.8497, 34.4367]},
            )
        if "route" in p:
            import re
            m = re.search(r"from\s+(.+?)\s+to\s+(.+)$", prompt, flags=re.IGNORECASE)
            if not m:
                m = re.search(r"between\s+(.+?)\s+and\s+(.+)$", prompt, flags=re.IGNORECASE)
            if m:
                return (
                    "ors_route_places",
                    {"origin_place": m.group(1).strip(), "destination_place": m.group(2).strip()},
                )
            return (
                "ors_route",
                {"origin": [35.5018, 33.8938], "destination": [35.8497, 34.4367], "profile": "driving-car"},
            )
        if any(k in p for k in ("hospital", "restaurant", "poi")):
            return ("osm_search_poi", {"query": "hospitals", "city": "Beirut"})
        # default to geocoding
        return ("osm_geocode", {"place": prompt})

    async def _dispatch_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == "osm_geocode":
            res = await self.osm.geocode(args["place"])
            try:
                lat = float(res.get("lat"))
                lon = float(res.get("lon"))
                key = str(args["place"]).strip().lower()
                self.place_cache[key] = (lon, lat)  # store as [lon, lat]
            except Exception:
                pass
            return res
        if name == "osm_reverse":
            return await self.osm.reverse(args["lat"], args["lon"])
        if name == "osm_search_poi":
            return await self.osm.search_poi(args["query"], args["city"], args.get("max_count", 5))
        if name == "ors_route":
            return await self.ors.route(args["origin"], args["destination"], args.get("profile", "driving-car"))
        if name == "ors_distance":
            return await self.ors.distance(args["origin"], args["destination"])
        if name == "ors_distance_places":
            async def _coords(place: str) -> Tuple[float, float]:
                key = place.strip().lower()
                if key in self.place_cache:
                    return self.place_cache[key]
                g = await self.osm.geocode(place)
                if "error" in g:
                    raise ValueError(g["error"])
                lon = float(g["lon"])  # OSM returns strings
                lat = float(g["lat"])  # keep as floats
                self.place_cache[key] = (lon, lat)
                return (lon, lat)

            try:
                o = await _coords(args["origin_place"])
                d = await _coords(args["destination_place"])
            except Exception as e:
                return {"error": f"Geocoding failed: {e}"}
            out = await self.ors.distance(list(o), list(d))
            out.update({"origin": list(o), "destination": list(d)})
            return out
        if name == "ors_route_places":
            async def _coords(place: str) -> Tuple[float, float]:
                key = place.strip().lower()
                if key in self.place_cache:
                    return self.place_cache[key]
                g = await self.osm.geocode(place)
                if "error" in g:
                    raise ValueError(g["error"])
