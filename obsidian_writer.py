# obsidian_writer.py

import os
from datetime import datetime
from config import OBSIDIAN_VAULT_PATH

def write_to_obsidian(content, course, topic):
    # Write to actual Obsidian vault under course folder
    course_folder = os.path.join(OBSIDIAN_VAULT_PATH, course)
    os.makedirs(course_folder, exist_ok=True)

    filename = f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y-%m-%d')}.md"
    path = os.path.join(course_folder, filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Saved to Obsidian: {path}")
    return path