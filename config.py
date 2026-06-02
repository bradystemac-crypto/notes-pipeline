# config.py

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Your Obsidian vault path
OBSIDIAN_VAULT_PATH = r"C:\Users\brady\OneDrive\Documents\Class notes"

GEMINI_MODEL = "gemini-3.5-flash"
MAX_RETRIES = 5
BASE_SLEEP_SECONDS = 2
PDF_DPI = 300