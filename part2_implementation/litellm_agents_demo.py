"""
LiteLLM + OpenAI Agents SDK demo using Gemini 2.0 via an OpenAI-compatible gateway.

Prerequisites
- pip install litellm
- pip install openai-agents (or the OpenAI Agents SDK package providing openai.agents)
- Set GEMINI_API_KEY in part2_implementation/.env
- Start LiteLLM gateway in a separate terminal:
    litellm --model gemini/gemini-2.0-flash --host 127.0.0.1 --port 4000

Then run:
    python -m part2_implementation.litellm_agents_demo
"""

import os
from dotenv import load_dotenv

# Load .env (GEMINI_API_KEY)
_BASE = os.path.dirname(__file__)
load_dotenv(os.path.join(_BASE, ".env"))
load_dotenv()

# Configure OpenAI SDK to talk to LiteLLM gateway
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:4000")
os.environ.setdefault("OPENAI_API_KEY", "dummy")  # LiteLLM accepts any non-empty token


def main():
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("[error] GEMINI_API_KEY not found in part2_implementation/.env")
        print("Add GEMINI_API_KEY and restart.")
        return

    try:
        from openai.agents import Agent, Runner
    except Exception as e:
        print("[error] openai.agents not available. Install the Agents SDK, e.g.:")
        print("    pip install openai-agents")
        print("Detail:", e)
        return

    print("Using OPENAI_BASE_URL=", os.getenv("OPENAI_BASE_URL"))
    print("Model= gemini/gemini-2.0-flash (via LiteLLM)")
    agent = Agent(
        name="Gemini Map Agent",
        instructions="Use map tools to answer user queries.",
        model="gemini/gemini-2.0-flash",
    )

    result = Runner.run(agent, input="Explain how geocoding works.")
    print("\nFinal output:\n", getattr(result, "final_output", result))


if __name__ == "__main__":
    main()

