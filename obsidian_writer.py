# obsidian_writer.py
 
import os
import re
import shutil
from datetime import datetime
from config import OBSIDIAN_VAULT_PATH
 
 
def _copy_diagrams_to_vault(diagram_map, course_folder):
    """
    Copies all diagram crop PNGs from OUTPUT_DIR into the course folder.
    Returns a dict mapping original crop basename → destination path.
    e.g. { "page_003_diagram_1.png": "/vault/BME3503/page_003_diagram_1.png" }
    """
    copied = {}
    for page_stem, crop_paths in diagram_map.items():
        for crop_path in crop_paths:
            basename = os.path.basename(crop_path)
            dest     = os.path.join(course_folder, basename)
            try:
                shutil.copy2(crop_path, dest)
                copied[basename] = dest
            except Exception as e:
                print(f"  ⚠️  Could not copy {basename}: {e}")
    return copied
 
 
def _inject_diagram_embeds(content, diagram_map):
    """
    Replaces [IMAGE: description] placeholders with Obsidian image embeds.
 
    Matching strategy:
    - Placeholders are written by the transcriber as [IMAGE: some description]
    - We pair them in order with diagram crops sorted by page then crop index
    - If more placeholders than crops, remaining placeholders get a fallback comment
    - If more crops than placeholders, extra crops are appended at the end
 
    Returns the updated content string.
    """
    # Build ordered list of crop filenames across all pages
    all_crops = []
    for page_stem in sorted(diagram_map.keys()):
        for crop_path in sorted(diagram_map[page_stem]):
            all_crops.append(os.path.basename(crop_path))
 
    if not all_crops:
        return content
 
    # Find all [IMAGE: ...] placeholders
    pattern     = re.compile(r'\[IMAGE:\s*([^\]]+)\]')
    placeholder_count = len(pattern.findall(content))
 
    crop_index  = [0]  # use list for closure mutability
 
    def replace_placeholder(match):
        description = match.group(1).strip()
        if crop_index[0] < len(all_crops):
            filename = all_crops[crop_index[0]]
            crop_index[0] += 1
            return f"![[{filename}]]\n*{description}*"
        else:
            # No crop available for this placeholder
            return f"<!-- [IMAGE: {description}] — no diagram extracted -->"
 
    content = pattern.sub(replace_placeholder, content)
 
    # Append any unmatched crops at the end (after the last section)
    remaining_crops = all_crops[crop_index[0]:]
    if remaining_crops:
        appendix = "\n\n## Additional Diagrams\n"
        for filename in remaining_crops:
            appendix += f"\n![[{filename}]]\n"
        content += appendix
 
    matched = min(placeholder_count, len(all_crops))
    print(f"  Injected {matched} diagram embed(s) "
          f"({placeholder_count} placeholder(s), {len(all_crops)} crop(s))")
 
    return content
 
 
def write_to_obsidian(content, course, topic, diagram_map=None):
    """
    Writes the formatted note to the Obsidian vault.
 
    Args:
        content:     formatted markdown string
        course:      course code e.g. "BME3503"
        topic:       topic string e.g. "Membrane Potential"
        diagram_map: optional dict from pdf_to_images()
                     { "page_003": ["/tmp/page_003_diagram_1.png", ...] }
 
    Returns:
        path to the written .md file
    """
    course_folder = os.path.join(OBSIDIAN_VAULT_PATH, course)
    os.makedirs(course_folder, exist_ok=True)
 
    # Copy diagram images into vault first
    if diagram_map:
        copied = _copy_diagrams_to_vault(diagram_map, course_folder)
        if copied:
            print(f"  Copied {len(copied)} diagram image(s) to vault")
            # Replace placeholders using the copied filenames
            content = _inject_diagram_embeds(content, diagram_map)
 
    filename = f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y-%m-%d')}.md"
    path     = os.path.join(course_folder, filename)
 
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
 
    print(f"✅ Saved to Obsidian: {path}")
    return path