# secrets.py
import os

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError(
        "Missing GEMINI_API_KEY. Set it in your environment variables."
    )