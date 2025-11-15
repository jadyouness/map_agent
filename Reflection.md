Reflection

What went well
- Implemented two map servers (OSM, ORS) each exposing 3+ operations and documented them.
- Added an Agent SDK–style orchestrator that registers tool schemas and dispatches tool calls to async servers.
- Hardened error handling (explicit .env loading, graceful ORS failures, model fallback).

Challenges
- Import path issues (misnamed directories with leading spaces) required careful renaming and aliasing to satisfy both package and test imports.
- Network/API constraints: ORS requires a valid key and can return non‑uniform errors; handling JSON/HTTP error paths cleanly improved stability.
- Integrating a tool‑calling flow while keeping the code simple enough for a short demo.

Next steps
- Add structured JSON schemas to the servers themselves and generate tool specs automatically from `server_params` to avoid duplication.
- Cache or debounce external calls to handle rate limits and improve responsiveness during demos.
- Extend with a small map UI (e.g., Folium/Leaflet) to visualize routes and POIs alongside the agent’s textual summary.

