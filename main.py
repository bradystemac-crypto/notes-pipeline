# main.py

import os
import time
import shutil
from datetime import datetime

from pdf_to_images import pdf_to_images
from transcribe import transcribe_images
from format_notes import format_notes
from obsidian_writer import write_to_obsidian
from cache import get_cached_transcription, save_transcription_to_cache
from connections import find_connections, inject_connections
from tracker import register_note
from config import OUTPUT_DIR, OBSIDIAN_VAULT_PATH


def safe_cleanup(folder):
    """Windows-safe cleanup"""
    if not os.path.exists(folder):
        return
    for root, dirs, files in os.walk(folder, topdown=False):
        for f in files:
            try:
                os.remove(os.path.join(root, f))
            except Exception:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except Exception:
                pass
    try:
        os.rmdir(folder)
    except Exception:
        pass
    os.makedirs(folder, exist_ok=True)


def run_pipeline(pdf_path, course, topic):
    print("\n🚀 Starting pipeline...\n")

    # -------------------------
    # Stage 1 — PDF → Images
    # -------------------------
    print("📄 Stage 1: PDF → Images")
    images = pdf_to_images(pdf_path)
    time.sleep(0.5)

    # -------------------------
    # Stage 2 — Transcription (with cache)
    # -------------------------
    print("\n🤖 Stage 2: Transcription")
    transcriptions = get_cached_transcription(pdf_path)

    if transcriptions is None:
        transcriptions, usage_log = transcribe_images(
            images,
            sleep_between_calls=2.0,
            max_retries=5
        )
        save_transcription_to_cache(pdf_path, transcriptions)

        total_tokens = sum(
            u.get("total_tokens", 0) or 0 for u in usage_log
        )
        print(f"  📊 Tokens used: {total_tokens}")
    else:
        print("  ⚡ Using cached transcription — no API call made")

    # -------------------------
    # Stage 3 — Formatting
    # -------------------------
    print("\n📝 Stage 3: Formatting")
    formatted = format_notes(transcriptions, course, topic)

    # -------------------------
    # Stage 4 — Connections
    # -------------------------
    print("\n🔗 Stage 4: Finding connections")
    connections = find_connections(formatted, OBSIDIAN_VAULT_PATH)

    if connections:
        print(f"  Found {len(connections)} connections: {connections}")
        formatted = inject_connections(formatted, connections)
    else:
        print("  No connections found")

    # -------------------------
    # Stage 5 — Write to Obsidian
    # -------------------------
    print("\n💾 Stage 5: Writing to Obsidian")
    note_path = write_to_obsidian(formatted, course, topic)

    # -------------------------
    # Stage 6 — Register in Tracker
    # -------------------------
    print("\n📅 Stage 6: Registering in spaced repetition tracker")
    register_note(note_path)

    # -------------------------
    # Cleanup
    # -------------------------
    print("\n🧹 Cleaning up temp files...")
    safe_cleanup(OUTPUT_DIR)

    print("\n✅ Pipeline complete!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4:
        pdf, course, topic = sys.argv[1], sys.argv[2], sys.argv[3]
    else:
        pdf = input("PDF path: ").strip().strip('"')
        course = input("Course: ").strip()
        topic = input("Topic: ").strip()
    run_pipeline(pdf, course, topic)