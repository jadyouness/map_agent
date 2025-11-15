Assignment: Map Servers with Agents and Tools

Overview
- Implements two map servers (OSM and ORS) and an agent that exposes them as JSON tools to LLM providers (OpenAI, Gemini, or local Ollama). Includes a CLI demo and an optional notebook.

Repository Structure
```
hw5/
  __init__.py
  README.md
  Reflection.md
  reading_exploration/
    mcp summary.md
  part2_implementation/
    __init__.py
    .env                      # put keys here (see below)
    requirement.txt           # minimal deps
    map_agent.ipynb           # optional notebook demo
    demo_runner.py            # CLI entry to run the agent
    agent_sdk_app.py          # main Agent orchestrator + tools
    openai_client.py          # OpenAI client (reads OPENAI_API_KEY)
    gemini_provider.py        # direct Gemini calls + tool-calling bridge
    litellm_agents_demo.py    # Agents SDK via LiteLLM + Gemini
    servers/
      __init__.py
      osm_server.py           # OSM geocode/reverse/search
      ors_server.py           # ORS route/distance/nearby
  # tests previously lived under test/ but were removed
```

Tools Used
- Language/runtime: Python 3.10+
- HTTP + utils: `requests`, `python-dotenv`
- LLM SDKs:
  - OpenAI Python SDK (`openai`) for function calling
  - Gemini via direct REST in `gemini_provider.py`
  - Optional OpenAI Agents SDK routed through LiteLLM (see `part2_implementation/litellm_agents_demo.py`)
- Local LLM: Optional Ollama (`http://localhost:11434`) for offline tool selection/summarization

Map Servers (Used in Code)
- OSM/Nominatim
  - Role: forward geocoding, reverse geocoding, simple text POI search
  - Endpoints: search and reverse under `https://nominatim.openstreetmap.org`
  - Notes: public rate limits; include proper User-Agent; optional `OSM_COUNTRYCODES` bias
- OpenRouteService (ORS)
  - Role: routing (turn-by-turn), distance/duration, nearby/POIs by area
  - Endpoints: `v2/directions/{profile}`, `pois` under `https://api.openrouteservice.org/`
  - Notes: requires `ORS_API_KEY`; profiles like `driving-car`, `foot-walking`, `cycling-regular`

MCP and Agents SDK
- MCP framing: `part2_implementation/mcp_base.py` defines minimal types (`MCPCommand`, `MCPMapServer`) to describe server commands and make tool schemas explicit.
- Agents approach: `part2_implementation/agent_sdk_app.py` registers tools (e.g., `osm_geocode`, `osm_reverse`, `osm_search_poi`, `ors_route`, `ors_distance`, `ors_nearby`, plus helpers that auto-geocode places) and orchestrates tool calling across providers.
- Providers:
  - OpenAI (default): function calling with a tools-first then final answer pattern
  - Gemini: `gemini_provider.run_with_tools()` translates our tool schema to Gemini format and stitches function responses
  - Ollama: local fallback that picks a tool and summarizes results without cloud calls
- Optional: `part2_implementation/litellm_agents_demo.py` shows using OpenAI Agents SDK pointed at a LiteLLM gateway configured for Gemini

LLM Models
- OpenAI: examples tested with `gpt-4o` and `gpt-4o-mini` (configurable via `MAP_AGENT_MODEL`)
- Gemini: e.g., `gemini-2.0-flash` via REST (set `MAP_AGENT_PROVIDER=gemini`)
- Ollama: default `llama3.1:8b-instruct` (configurable via `OLLAMA_MODEL`)

Key Workflows
- Distance between two places: OSM geocode A and B → ORS directions/distance → compact JSON summary
- Route from A to B: OSM geocode → ORS `v2/directions/{profile}` → steps/summary
- POIs in a city: OSM search with text + city → top-N items (name, lat, lon)

Setup
1) Create a virtual environment and install deps
   - `python -m venv .venv`
   - Activate venv (Windows: `.venv\Scripts\activate`, macOS/Linux: `source .venv/bin/activate`)
   - `pip install -r part2_implementation/requirement.txt`
2) Add keys to `part2_implementation/.env`
   - Required for OpenAI: `OPENAI_API_KEY=...`
   - Required for ORS: `ORS_API_KEY=...`
   - Optional: `GEMINI_API_KEY=...` (Gemini provider)
   - Optional: `MAP_AGENT_PROVIDER=gemini|ollama` (default: OpenAI)
   - Optional: `MAP_AGENT_MODEL=gpt-4o` (or `gpt-4o-mini`), `OLLAMA_MODEL=llama3.1:8b-instruct`

Run the Agent (CLI)
- OpenAI default:
  - `python -m part2_implementation.demo_runner "Find a driving route from Beirut to Tripoli"`
- Gemini provider:
  - Set `MAP_AGENT_PROVIDER=gemini` and `GEMINI_API_KEY`, then run the same command
- Local Ollama (no cloud):
  - Start Ollama, pull a model, set `MAP_AGENT_PROVIDER=ollama`, then run the same command

Notebook Demo
- Open `part2_implementation/map_agent.ipynb` and run cells like:
  ```python
  import asyncio
  from part2_implementation.agent_sdk_app import AgentsSDKMapAssistant
  agent = AgentsSDKMapAssistant()
  await agent.run("Find a driving route from Beirut to Tripoli and summarize it.")
  await agent.run("Find 3 hospitals in Beirut")
  await agent.run("Geocode Tripoli Lebanon")
  ```

Gradio Chat UI (Notebook)
- Location: `part2_implementation/map_agent.ipynb` (final cells).
- Usage:
  - Run the optional pre-install cell to install `gradio` quickly.
  - Run the final UI cell to launch a chat interface in the notebook.
  - Ask natural questions (e.g., `Distance from Beirut to Tripoli?`, `Find 3 hospitals in Tripoli`).
- Behavior:
  - Uses your existing agent (`run_with_tools`, `TOOLS`, `AgentsSDKMapAssistant`).
  - If ORS returns an HTTP error (e.g., quota/400), the UI computes an approximate Haversine distance as a fallback for distance queries.
  - Reads keys from `part2_implementation/.env` (`GEMINI_API_KEY`, `ORS_API_KEY`).

Testing in Notebook
- We manually test the full agent end-to-end in `part2_implementation/map_agent.ipynb`.
- Covered scenarios:
  - Geocoding and reverse geocoding via OSM/Nominatim
  - City POI search via OSM (top-N results)
  - Routing and distance between places via ORS (with OSM pre-geocode)
  - Provider modes: OpenAI, Gemini, and local Ollama
  - Error surfacing for missing keys and HTTP failures

Configuration Notes
- Nominatim usage: add a descriptive User-Agent; respect public rate limits
- ORS keys: ensure `ORS_API_KEY` is set; errors surface as `{error, detail}` without crashing
- Country bias: set `OSM_COUNTRYCODES` (e.g., `lb,us`) to bias geocoding

Troubleshooting
- Missing keys: check `part2_implementation/.env`
- Rate limits: retry later, reduce frequency, or cache geocodes
- Gemini path: confirm `GEMINI_API_KEY` and provider flag
- Ollama path: ensure `ollama serve` is running and model is pulled

References
- OSM: https://www.openstreetmap.org
- Nominatim: https://nominatim.org
- OpenRouteService: https://openrouteservice.org
- OpenAI Assistants/Tools: https://platform.openai.com/docs/assistants/overview
- Gemini function calling: https://ai.google.dev/gemini-api/docs/function-calling
