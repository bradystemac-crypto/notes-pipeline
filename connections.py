# connections.py

import os
from google import genai
from config import OBSIDIAN_VAULT_PATH

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL = "gemini-2.5-flash-lite"  # use cheaper model for this small task

def get_existing_notes(vault_path):
    """
    Scans your Obsidian vault and returns a list of all existing note names.
    """
    note_names = []
    for root, dirs, files in os.walk(vault_path):
        # Skip hidden folders like .obsidian
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            if file.endswith(".md"):
                name = os.path.splitext(file)[0]
                note_names.append(name)
    return note_names

def find_connections(formatted_note, vault_path):
    """
    Sends the formatted note + list of existing vault notes to Gemini.
    Gemini identifies which existing notes are conceptually related.
    Returns a list of [[wikilink]] strings.
    """
    existing_notes = get_existing_notes(vault_path)

    if not existing_notes:
        print("  No existing notes found in vault — skipping connections")
        return []

    notes_list = "\n".join(f"- {n}" for n in existing_notes)

    prompt = f"""
You are an academic knowledge graph assistant.

Below is a new lecture note and a list of existing notes in a student's Obsidian vault.
Your job is to identify which existing notes are genuinely conceptually related to the new note.

Only suggest connections that are directly relevant — not tangentially related.
Return ONLY a JSON array of note names exactly as they appear in the list, nothing else.
Example output: ["Membrane Potentials", "Action Potential Propagation"]

--- NEW NOTE ---
{formatted_note[:3000]}

--- EXISTING NOTES ---
{notes_list}
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt]
        )

        raw = response.text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        import json
        connections = json.loads(raw.strip())
        return [f"[[{c}]]" for c in connections]

    except Exception as e:
        print(f"  ⚠️ Connection detection failed: {e}")
        return []

def inject_connections(formatted_note, connections):
    """
    Replaces the placeholder connections section with actual wikilinks.
    """
    if not connections:
        return formatted_note

    links = "\n".join(f"- {c}" for c in connections)
    return formatted_note.replace(
        "- [ ] Add connections",
        links
    )