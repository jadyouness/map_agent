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
                lon = float(g["lon"])  # OSM returns strings
                lat = float(g["lat"])  # keep as floats
                self.place_cache[key] = (lon, lat)
                return (lon, lat)

            try:
                o = await _coords(args["origin_place"])
                d = await _coords(args["destination_place"])
            except Exception as e:
                return {"error": f"Geocoding failed: {e}"}
            return await self.ors.route(list(o), list(d), "driving-car")
        if name == "ors_nearby":
            return await self.ors.nearby(args["lat"], args["lon"])
        return {"error": f"Unknown tool: {name}"}

    async def run(self, prompt: str) -> Dict[str, Any]:
        # Provider routing: openai (default), ollama, gemini, or offline
        provider = os.getenv("MAP_AGENT_PROVIDER", "openai").lower()
        if os.getenv("MAP_AGENT_DISABLE_OPENAI") or provider == "ollama":
            # Try Ollama tool selection if provider set; otherwise fallback heuristic
            selected: Optional[Tuple[str, Dict[str, Any]]] = None
            if provider == "ollama":
                choice = await self._ollama_choose_tool(prompt)
                if choice:
                    selected = (choice["tool"], choice.get("arguments", {}))

            if not selected:
                selected = self._heuristic_route(prompt)

            tool, args = selected
            result = await self._dispatch_tool(tool, args)

            # If Ollama is in use, request a short summary from it as well
            if provider == "ollama":
                summary = await self._ollama_summarize(prompt, tool, result)
                return {"answer": summary, "tool_results": [{"tool": tool, "content": result}]}

            return {"answer": f"[offline] {tool}: {result}", "tool_results": [{"tool": tool, "content": result}]}

        if provider == "gemini":
            try:
                return await gemini_run_with_tools(prompt, TOOLS, self._dispatch_tool)
            except Exception as e:
                tool, args = self._heuristic_route(prompt)
                result = await self._dispatch_tool(tool, args)
                return {"answer": f"[gemini fallback] {tool}: {result} (no model: {e})",
                        "tool_results": [{"tool": tool, "content": result}]}

        # Default: OpenAI provider (lazy import to avoid requiring OPENAI_API_KEY unless used)
        def _get_openai_client():
            from part2_implementation.openai_client import client as _client
            return _client

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": "You are a helpful map assistant. Use tools when helpful."},
            {"role": "user", "content": prompt},
        ]

        # First call: let the model decide whether to call tools
        try:
            client = _get_openai_client()
            resp = client.chat.completions.create(
                model=os.getenv("MAP_AGENT_MODEL", "gpt-4o"),
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            # Fallback: run a single heuristic tool and return raw results
            tool, args = self._heuristic_route(prompt)
            result = await self._dispatch_tool(tool, args)
            return {
                "answer": f"[fallback] {tool}: {result} (no model: {e})",
                "tool_results": [{"tool": tool, "content": result}],
            }

        msg = resp.choices[0].message
        tool_messages: List[Dict[str, Any]] = []

        if getattr(msg, "tool_calls", None):
            # Execute each tool call and append tool results
            for call in msg.tool_calls:
                tool_name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except Exception:
                    args = {}
                result = await self._dispatch_tool(tool_name, args)
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )

            # Second call: provide tool results and get final answer
            messages.extend([
                {"role": msg.role, "tool_calls": [tc.model_dump() for tc in msg.tool_calls], "content": msg.content},
                *tool_messages,
            ])

            try:
                client = _get_openai_client()
                final = client.chat.completions.create(
                    model=os.getenv("MAP_AGENT_MODEL", "gpt-4o"),
                    messages=messages,
                )
                answer = final.choices[0].message.content
                return {"answer": answer, "tool_results": tool_messages}
            except Exception as e:
                # Return tool outputs without model summary
                return {
                    "answer": f"Results from tools: {[tm['content'] for tm in tool_messages]} (no model: {e})",
                    "tool_results": tool_messages,
                }

        # No tool calls — just return the model’s reply
        return {"answer": msg.content, "tool_results": []}

    async def _ollama_choose_tool(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Ask a local Ollama model to choose a tool and JSON args.

        Expects Ollama running at http://localhost:11434. Configure model via OLLAMA_MODEL and context via OLLAMA_NUM_CTX.
        """
        import requests

        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct")
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

        tool_list = [t["function"]["name"] for t in TOOLS]
        sys = (
            "You are a tool selector. Given a user prompt, choose the single best tool "
            "from the list and return strictly JSON in the format: {\"tool\": \"<name>\", \"arguments\": { ... }}. "
            f"Tools: {tool_list}. Do not include any other text."
        )
        user = f"Prompt: {prompt}"

        try:
            r = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"num_ctx": num_ctx},
                },
                timeout=30,
            )
            data = r.json()
            content = data.get("message", {}).get("content", "{}")
            return json.loads(content)
        except Exception:
            return None

    async def _ollama_summarize(self, prompt: str, tool: str, result: Dict[str, Any]) -> str:
        """Ask a local Ollama model to summarize tool results into a friendly answer."""
        import requests

        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct")
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

        sys = "You are a helpful map assistant. Write a short, friendly answer."
        user = (
            f"User asked: {prompt}\n"
            f"Tool used: {tool}\n"
            f"Tool result JSON: {json.dumps(result)}"
        )

        try:
            r = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"num_ctx": num_ctx},
                },
                timeout=30,
            )
            data = r.json()
            return data.get("message", {}).get("content", "") or str(result)
        except Exception:
            return str(result)


async def demo():
    agent = AgentsSDKMapAssistant()
    return await agent.run("Find a driving route from Beirut to Tripoli and summarize it.")


if __name__ == "__main__":
    print(asyncio.run(demo()))
