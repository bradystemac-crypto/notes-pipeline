# app.py

import os
import sys
import json
import time
import queue
import threading
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, send_file, Response, render_template

app = Flask(__name__)

# Thread-safe queue for streaming progress updates
progress_queues = {}

def stream_progress(job_id, message, stage=None, done=False, error=False, download_url=None, stats=None):
    """Push a progress event into the job's queue"""
    if job_id not in progress_queues:
        return
    progress_queues[job_id].put({
        "message": message,
        "stage": stage,
        "done": done,
        "error": error,
        "download_url": download_url,
        "stats": stats
    })


def run_pipeline_threaded(job_id, pdf_path, course, topic, output_path):
    """Runs the full pipeline in a background thread, pushing progress updates"""
    try:
        # --- Import pipeline modules ---
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from pdf_to_images import pdf_to_images
        from transcribe import transcribe_images, PRIMARY_MODEL, FALLBACK_MODEL
        from format_notes import format_notes
        from cache import get_cached_transcription, save_transcription_to_cache
        from connections import find_connections, inject_connections
        from obsidian_writer import write_to_obsidian
        from tracker import register_note
        from config import OBSIDIAN_VAULT_PATH, OUTPUT_DIR

        stats = {
            "model": PRIMARY_MODEL,
            "fallback_model": FALLBACK_MODEL,
            "total_tokens": 0,
            "cached": False,
            "pages": 0,
            "connections": 0
        }

        # --- Stage 1: PDF to Images ---
        stream_progress(job_id, "Converting PDF to images...", stage=1)
        images = pdf_to_images(pdf_path)
        stats["pages"] = len(images)
        stream_progress(job_id, f"Converted {len(images)} pages", stage=1)
        time.sleep(0.3)

        # --- Stage 2: Transcription ---
        stream_progress(job_id, "Checking transcription cache...", stage=2)
        transcriptions = get_cached_transcription(pdf_path)

        if transcriptions is not None:
            stats["cached"] = True
            stream_progress(job_id, "Cache hit — skipping Gemini transcription", stage=2)
        else:
            stream_progress(job_id, f"Transcribing with {PRIMARY_MODEL}...", stage=2)
            transcriptions, usage_log = transcribe_images(images, sleep_between_calls=2.0, max_retries=5)
            save_transcription_to_cache(pdf_path, transcriptions)

            total_tokens = sum(u.get("total_tokens", 0) or 0 for u in usage_log)
            stats["total_tokens"] += total_tokens
            model_used = usage_log[0].get("model_used", PRIMARY_MODEL) if usage_log else PRIMARY_MODEL
            stats["model"] = model_used
            stream_progress(job_id, f"Transcription complete — {total_tokens:,} tokens used", stage=2)

        time.sleep(0.3)

        # --- Stage 3: Formatting ---
        stream_progress(job_id, "Formatting notes into Obsidian template...", stage=3)
        formatted = format_notes(transcriptions, course, topic)
        stream_progress(job_id, "Formatting complete", stage=3)
        time.sleep(0.3)

        # --- Stage 4: Connections ---
        stream_progress(job_id, "Scanning vault for connections...", stage=4)
        connections = find_connections(formatted, OBSIDIAN_VAULT_PATH)
        if connections:
            formatted = inject_connections(formatted, connections)
            stats["connections"] = len(connections)
            stream_progress(job_id, f"Found {len(connections)} connection(s)", stage=4)
        else:
            stream_progress(job_id, "No connections found", stage=4)
        time.sleep(0.3)

        # --- Stage 5: Write to Obsidian + save download copy ---
        stream_progress(job_id, "Writing to Obsidian vault...", stage=5)
        note_path = write_to_obsidian(formatted, course, topic)

        # Also save to output_path for browser download
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted)

        stream_progress(job_id, "Saved to Obsidian vault", stage=5)
        time.sleep(0.3)

        # --- Stage 6: Tracker ---
        stream_progress(job_id, "Registering in spaced repetition tracker...", stage=6)
        register_note(note_path)
        stream_progress(job_id, "Registered in tracker", stage=6)

        # --- Done ---
        stream_progress(
            job_id,
            "Pipeline complete",
            stage=6,
            done=True,
            download_url=f"/download/{job_id}",
            stats=stats
        )

    except Exception as e:
        stream_progress(job_id, f"Error: {str(e)}", error=True, done=True)
    finally:
        # Clean up the uploaded PDF
        try:
            os.remove(pdf_path)
        except Exception:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    """Receives the uploaded PDF and form inputs, starts pipeline thread"""
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf_file = request.files["pdf"]
    course = request.form.get("course", "").strip()
    topic = request.form.get("topic", "").strip()

    if not course or not topic:
        return jsonify({"error": "Course and topic are required"}), 400

    # Save uploaded PDF to a temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_file.save(tmp.name)
    tmp.close()

    # Create output path for the .md file
    job_id = f"{int(time.time() * 1000)}"
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{job_id}.md")

    # Set up progress queue for this job
    progress_queues[job_id] = queue.Queue()

    # Start pipeline in background thread
    thread = threading.Thread(
        target=run_pipeline_threaded,
        args=(job_id, tmp.name, course, topic, output_path),
        daemon=True
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def progress(job_id):
    """Server-Sent Events stream for live progress updates"""
    def generate():
        if job_id not in progress_queues:
            yield f"data: {json.dumps({'error': 'Job not found', 'done': True})}\n\n"
            return

        while True:
            try:
                event = progress_queues[job_id].get(timeout=60)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("done"):
                    # Clean up queue after job is done
                    del progress_queues[job_id]
                    break
            except queue.Empty:
                # Send keepalive ping
                yield f"data: {json.dumps({'message': 'waiting...'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/download/<job_id>")
def download(job_id):
    """Serves the finished .md file for download"""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_outputs")
    output_path = os.path.join(output_dir, f"{job_id}.md")

    if not os.path.exists(output_path):
        return "File not found", 404

    return send_file(output_path, as_attachment=True, download_name="notes.md")


if __name__ == "__main__":
    app.run(debug=True, port=5000)