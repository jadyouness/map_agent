import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env from package directory first, then any default .env in CWD
_BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(_BASE_DIR, ".env"))
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found. Add it to part2_implementation/.env or env vars.")

client = OpenAI(api_key=api_key)

