# dashboard.py

import os
import json
from datetime import date
from config import OBSIDIAN_VAULT_PATH
from tracker import load_tracker, get_due_notes

OUTPUT_HTML = "dashboard.html"

def scan_vault(vault_path):
    """Scans Obsidian vault and returns structured data per course"""
    courses = {}

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for file in files:
            if not file.endswith(".md"):
                continue

            course = os.path.basename(root)
            if course == os.path.basename(vault_path):
                course = "Uncategorized"

            full_path = os.path.join(root, file)
            modified = date.fromtimestamp(os.path.getmtime(full_path))

            # Read frontmatter tags and topic
            topic = ""
            tags = []
            questions = 0

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Count flagged questions
                questions = content.count("- [ ]")

                # Parse frontmatter
                if content.startswith("---"):
                    fm_end = content.find("---", 3)
                    if fm_end != -1:
                        fm = content[3:fm_end]
                        for line in fm.splitlines():
                            if line.startswith("topic:"):
                                topic = line.replace("topic:", "").strip().strip('"')
                            if line.startswith("tags:"):
                                tags = line.replace("tags:", "").strip().strip("[]").split(",")
                                tags = [t.strip() for t in tags]
            except Exception:
                pass

            if course not in courses:
                courses[course] = []

            courses[course].append({
                "name": os.path.splitext(file)[0],
                "topic": topic or os.path.splitext(file)[0],
                "modified": str(modified),
                "questions": questions,
                "tags": tags
            })

    return courses

def generate_dashboard():
    """Generates an HTML dashboard from vault data"""
    courses = scan_vault(OBSIDIAN_VAULT_PATH)
    due_notes = get_due_notes()
    today = str(date.today())

    total_notes = sum(len(notes) for notes in courses.values())
    total_questions = sum(
        note["questions"] for notes in courses.values() for note in notes
    )

    # Build course cards HTML
    course_cards = ""
    for course, notes in sorted(courses.items()):
        notes_html = ""
        for note in sorted(notes, key=lambda x: x["modified"], reverse=True):
            q_badge = f'<span class="badge">❓ {note["questions"]}</span>' if note["questions"] > 0 else ""
            notes_html += f"""
            <div class="note-row">
                <span class="note-name">{note["topic"]}</span>
                <span class="note-date">{note["modified"]}</span>
                {q_badge}
            </div>"""

        course_cards += f"""
        <div class="card">
            <div class="card-header">
                <h3>{course}</h3>
                <span class="count">{len(notes)} notes</span>
            </div>
            {notes_html}
        </div>"""

    # Build due notes HTML
    due_html = ""
    if due_notes:
        for note in due_notes[:5]:
            overdue = f"({note['days_overdue']}d overdue)" if note['days_overdue'] > 0 else "due today"
            due_html += f"""
            <div class="due-row">
                <span>{note["name"]}</span>
                <span class="overdue">{overdue}</span>
            </div>"""
    else:
        due_html = '<p class="all-good">✅ All caught up!</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Notes Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 2rem; }}
        h1 {{ font-size: 1.6rem; margin-bottom: 0.25rem; color: #ffffff; }}
        .subtitle {{ color: #888; font-size: 0.9rem; margin-bottom: 2rem; }}
        .stats {{ display: flex; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap; }}
        .stat {{ background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 1rem 1.5rem; min-width: 140px; }}
        .stat-value {{ font-size: 2rem; font-weight: 700; color: #7c6aff; }}
        .stat-label {{ font-size: 0.8rem; color: #888; margin-top: 0.25rem; }}
        .section-title {{ font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: #ccc; text-transform: uppercase; letter-spacing: 0.05em; }}
        .due-box {{ background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 1.25rem; margin-bottom: 2rem; }}
        .due-row {{ display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #222; font-size: 0.9rem; }}
        .due-row:last-child {{ border-bottom: none; }}
        .overdue {{ color: #ff6b6b; font-size: 0.8rem; }}
        .all-good {{ color: #6bff9e; font-size: 0.9rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }}
        .card {{ background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 1.25rem; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .card-header h3 {{ font-size: 1rem; color: #ffffff; }}
        .count {{ font-size: 0.75rem; background: #7c6aff22; color: #7c6aff; padding: 0.2rem 0.6rem; border-radius: 20px; }}
        .note-row {{ display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0; border-bottom: 1px solid #222; font-size: 0.85rem; gap: 0.5rem; }}
        .note-row:last-child {{ border-bottom: none; }}
        .note-name {{ color: #ccc; flex: 1; }}
        .note-date {{ color: #555; font-size: 0.75rem; white-space: nowrap; }}
        .badge {{ background: #ff6b6b22; color: #ff6b6b; font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 10px; white-space: nowrap; }}
    </style>
</head>
<body>
    <h1>📚 Notes Dashboard</h1>
    <p class="subtitle">Generated {today}</p>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{total_notes}</div>
            <div class="stat-label">Total Notes</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(courses)}</div>
            <div class="stat-label">Courses</div>
        </div>
        <div class="stat">
            <div class="stat-value">{len(due_notes)}</div>
            <div class="stat-label">Due for Review</div>
        </div>
        <div class="stat">
            <div class="stat-value">{total_questions}</div>
            <div class="stat-label">Open Questions</div>
        </div>
    </div>

    <div class="due-box">
        <div class="section-title">📅 Due for Review</div>
        {due_html}
    </div>

    <div class="section-title">📁 Notes by Course</div>
    <div class="grid">
        {course_cards}
    </div>
</body>
</html>"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Dashboard generated → {OUTPUT_HTML}")
    print("Open it in your browser to view.")

if __name__ == "__main__":
    generate_dashboard()