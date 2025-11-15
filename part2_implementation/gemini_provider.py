import os
import json
import requests
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load .env from package dir and default cwd
_BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(_BASE_DIR, ".env"))
load_dotenv()


def _to_gemini_tools(TOOLS: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fns = []
    for t in TOOLS:
        fn = t["function"]
        fns.append(
            {
                "name": fn["name"],
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object"}),
            }
        )
    return [{"functionDeclarations": fns}]


def _user_msg(text: str) -> Dict[str, Any]:
    return {"role": "user", "parts": [{"text": text}]}


def _model_function_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


def _tool_function_response(name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    # Gemini expects functionResponse.response with a name and content parts
    if isinstance(result, (dict, list)):
        text = json.dumps(result, ensure_ascii=False)
    else:
        text = str(result)
    return {
        "role": "tool",
        "parts": [
            {
                "functionResponse": {
                    "name": name,
                    "response": {
                        "name": name,
                        "content": [{"text": text}],
                    },
                }
            }
        ],
    }


def _generate(contents: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, auto: bool = True,
              generation_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set. Add it to part2_implementation/.env or environment.")

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    base = "https://generativelanguage.googleapis.com/v1beta"
    url = f"{base}/models/{model}:generateContent"

    body: Dict[str, Any] = {"contents": contents}
    if tools:
        body["tools"] = tools
        body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO" if auto else "ANY"}}
    if generation_config:
        body["generationConfig"] = generation_config

    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    r = requests.post(url, headers=headers, data=json.dumps(body), timeout=60)
    if not r.ok:
        # Surface API error details to aid debugging
        raise requests.HTTPError(f"{r.status_code} {r.reason}: {r.text}", response=r)
    return r.json()


async def run_with_tools(prompt: str, TOOLS: List[Dict[str, Any]], dispatch_tool_async) -> Dict[str, Any]:
    """
    Run a single-turn Gemini interaction with optional tool-calling.
    dispatch_tool_async: async function (name, args) -> dict
    """
    policy = (
        "You are a strict map assistant. Tool policy: if the user asks for a driving route"
        " between two places, call ors_route_places (or ors_route) and return only the route"
        " steps as a numbered list of turn-by-turn instructions. If the user asks for distance,"
        " call ors_distance_places (or ors_distance) and return only the numeric distance in km."
        " Do not echo raw geocode results in the final answer."
    )
    contents = [_user_msg(policy), _user_msg(prompt)]
    tools = _to_gemini_tools(TOOLS)

    # Let Gemini decide tools
    resp = _generate(contents, tools=tools, auto=True)
    cand = resp.get("candidates", [{}])[0]
    parts = cand.get("content", {}).get("parts", []) or []

    tool_results: List[Dict[str, Any]] = []
    made_call = False
    for p in parts:
        call = p.get("functionCall")
        if call:
            made_call = True
            name = call.get("name")
            args = call.get("args", {})
            result = await dispatch_tool_async(name, args)
            tool_results.append({"tool": name, "content": result})
            contents.append(_model_function_call(name, args))
            contents.append(_tool_function_response(name, result))

    if made_call:
        # Ask for final answer after tool responses; keep tool declarations
        final = _generate(contents, tools=tools, auto=False)
        text = (
            final.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not (text or "").strip():
            # Fallback: synthesize a brief answer from tool_results
            def _fmt_tool(tr: Dict[str, Any]) -> str:
                name = tr.get("tool", "tool")
                data = tr.get("content")
                try:
                    if name == "osm_search_poi" and isinstance(data, list) and data:
                        items = data[:3]
                        parts = [
                            f"- {i.get('name','?')} ({i.get('lat','?')}, {i.get('lon','?')})"
                            for i in items
                        ]
                        return "Top places:\n" + "\n".join(parts)
                    if name == "osm_geocode" and isinstance(data, dict):
                        # Provide a concise geocode summary instead of blank
                        place = data.get("place") or "Place"
                        lat = data.get("lat")
                        lon = data.get("lon")
                        disp = data.get("display")
                        if lat and lon:
                            txt = f"Geocode: {place} → {lat}, {lon}"
                            if disp:
                                txt += f"\n{disp}"
                            return txt
                        # If no coordinates, surface the error text if any
                        if "error" in data:
                            return f"Geocode error: {data.get('error')}"
                        return json.dumps(data)[:200]
                    if name == "osm_reverse" and isinstance(data, dict):
                        return f"Address: {data.get('address','Unknown')}"
                    if name in ("ors_distance", "ors_distance_places") and isinstance(data, dict):
                        d = data.get("cumulative_distance_km") or data.get("distance_km")
                        if d is not None:
                            return f"Distance: {d} km"
                        # Show error if present
                        if "error" in data:
                            return f"Distance error: {data.get('error')}"
                        return json.dumps(data)[:200]
                    if name in ("ors_route", "ors_route_places") and isinstance(data, dict):
                        steps = data.get("steps")
                        if isinstance(steps, list) and steps:
                            lines = []
                            for idx, st in enumerate(steps, 1):
                                ins = st.get("instruction") or "Continue"
                                lines.append(f"{idx}. {ins}")
                                if len(lines) >= 30:
                                    break
                            return "\n".join(lines)
                        # Fallback to summary
                        dist = data.get("cumulative_distance_km") or data.get("distance_km")
                        dur = data.get("cumulative_duration_min") or data.get("duration_min")
                        if dist is not None and dur is not None:
                            return f"Route: {dist} km, {dur} min"
                        return json.dumps(data)[:400]
                    if name.startswith("ors_"):
                        return f"{name}: {json.dumps(data)[:400]}"
                    return json.dumps(data)[:400]
                except Exception:
                    return str(data)[:400]

            text = "\n".join(_fmt_tool(tr) for tr in tool_results)
        return {"answer": text, "tool_results": tool_results}

    # No tool calls; return model text
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    return {"answer": text, "tool_results": []}


def call_gemini(prompt: str, max_tokens: int = 100) -> str:
    """Simple text-only Gemini call using .env GEMINI_API_KEY and GEMINI_MODEL.

    Example:
        from part2_implementation.gemini_provider import call_gemini
        print(call_gemini("Explain how AI works in simple words."))
    """
    contents = [_user_msg(prompt)]
    resp = _generate(contents, tools=None, auto=False, generation_config={"maxOutputTokens": max_tokens})
    cand = resp.get("candidates", [{}])[0]
    parts = cand.get("content", {}).get("parts", []) or []
    for p in parts:
        if isinstance(p, dict) and "text" in p:
            return p["text"]
    return ""
