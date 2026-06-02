# pdf_to_images.py

import fitz
import os
import numpy as np
from PIL import Image
from config import OUTPUT_DIR, PDF_DPI

# ─────────────────────────────────────────────────────────────
# Tuning constants for diagram detection
# ─────────────────────────────────────────────────────────────

# A region must have variance above this to be considered image-heavy
VARIANCE_THRESHOLD  = 180

# Minimum fraction of page width/height a crop must be to keep it
MIN_CROP_WIDTH_FRAC  = 0.15
MIN_CROP_HEIGHT_FRAC = 0.08

# Grid size for variance sampling (rows × cols)
GRID_ROWS = 20
GRID_COLS = 20


# ─────────────────────────────────────────────────────────────
# White ink fix
# ─────────────────────────────────────────────────────────────

def fix_white_ink(img):
    """Remaps near-white ink to black, leaves all other colors untouched"""
    arr = np.array(img.convert("RGB")).astype(np.uint8)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    near_white       = (r > 200) & (g > 200) & (b > 200)
    pure_background  = (r > 250) & (g > 250) & (b > 250)
    white_ink_mask   = near_white & ~pure_background
    arr[white_ink_mask] = [0, 0, 0]
    return Image.fromarray(arr)


# ─────────────────────────────────────────────────────────────
# Duplicate detection
# ─────────────────────────────────────────────────────────────

def image_hash(img):
    """Returns array for duplicate comparison"""
    return np.array(img.resize((64, 64)).convert("L")).flatten().astype(int)

def is_duplicate(img, previous_arrays, threshold=5):
    """Returns True if page is visually identical to a recent page"""
    current = image_hash(img)
    for prev in previous_arrays[-3:]:
        if np.abs(current - prev).mean() < threshold:
            return True
    return False


# ─────────────────────────────────────────────────────────────
# Diagram detection + cropping
# ─────────────────────────────────────────────────────────────

def _variance_grid(gray_arr, rows=GRID_ROWS, cols=GRID_COLS):
    """
    Splits the grayscale image into a grid and computes
    pixel variance for each cell. Returns a 2D numpy array.
    """
    h, w   = gray_arr.shape
    cell_h = h // rows
    cell_w = w // cols
    grid   = np.zeros((rows, cols), dtype=float)

    for r in range(rows):
        for c in range(cols):
            cell = gray_arr[r*cell_h:(r+1)*cell_h, c*cell_w:(c+1)*cell_w]
            grid[r, c] = float(np.var(cell))

    return grid


def _find_diagram_regions(img):
    """
    Finds bounding boxes of image-heavy (high variance) regions.
    Returns list of (x0, y0, x1, y1) pixel coords in original image space.
    Uses connected-component expansion on the variance grid.
    """
    w, h       = img.size
    gray_arr   = np.array(img.convert("L"))
    grid       = _variance_grid(gray_arr)
    hot        = grid > VARIANCE_THRESHOLD        # bool mask of hot cells

    if not hot.any():
        return []

    cell_h = h // GRID_ROWS
    cell_w = w // GRID_COLS

    # Find bounding box of all connected hot-cell clusters
    # Simple approach: find contiguous row/col spans
    hot_rows = np.where(hot.any(axis=1))[0]
    hot_cols = np.where(hot.any(axis=0))[0]

    if len(hot_rows) == 0 or len(hot_cols) == 0:
        return []

    # Split into separate vertical regions (gap > 3 rows = new region)
    regions = []
    row_groups = _split_into_groups(hot_rows, gap=3)

    for row_group in row_groups:
        # For this row band, find which cols are hot
        band_hot    = hot[row_group[0]:row_group[-1]+1, :]
        band_cols   = np.where(band_hot.any(axis=0))[0]
        if len(band_cols) == 0:
            continue

        col_groups = _split_into_groups(band_cols, gap=3)
        for col_group in col_groups:
            r0 = row_group[0]
            r1 = row_group[-1]
            c0 = col_group[0]
            c1 = col_group[-1]

            # Convert grid coords → pixel coords with padding
            pad_cells = 1
            x0 = max(0, (c0 - pad_cells) * cell_w)
            y0 = max(0, (r0 - pad_cells) * cell_h)
            x1 = min(w, (c1 + 1 + pad_cells) * cell_w)
            y1 = min(h, (r1 + 1 + pad_cells) * cell_h)

            # Filter out tiny regions
            if (x1 - x0) < w * MIN_CROP_WIDTH_FRAC:
                continue
            if (y1 - y0) < h * MIN_CROP_HEIGHT_FRAC:
                continue

            regions.append((x0, y0, x1, y1))

    return regions


def _split_into_groups(indices, gap=3):
    """Splits a sorted array of indices into contiguous groups."""
    if len(indices) == 0:
        return []
    groups  = []
    current = [indices[0]]
    for idx in indices[1:]:
        if idx - current[-1] <= gap:
            current.append(idx)
        else:
            groups.append(current)
            current = [idx]
    groups.append(current)
    return groups


def extract_diagrams(img, page_filename_stem, output_dir):
    """
    Runs diagram detection on a page image and saves crops.

    Args:
        img:                  PIL Image of the full page
        page_filename_stem:   e.g. "page_003" (no extension)
        output_dir:           folder to save crops into

    Returns:
        list of saved crop paths (may be empty if no diagrams found)
    """
    regions   = _find_diagram_regions(img)
    crop_paths = []

    for i, (x0, y0, x1, y1) in enumerate(regions, 1):
        crop          = img.crop((x0, y0, x1, y1))
        crop_filename = f"{page_filename_stem}_diagram_{i}.png"
        crop_path     = os.path.join(output_dir, crop_filename)
        crop.save(crop_path, format="PNG")
        crop_paths.append(crop_path)
        print(f"    Diagram crop {i}: ({x0},{y0})→({x1},{y1}) → {crop_filename}")

    return crop_paths


# ─────────────────────────────────────────────────────────────
# Main pipeline function
# ─────────────────────────────────────────────────────────────

def pdf_to_images(pdf_path):
    """
    Converts each PDF page to a high quality PNG, skipping duplicates.
    Also runs a second pass to detect and crop diagram regions.

    Returns:
        image_paths: list of full-page PNG paths (unchanged from before)
        diagram_map: dict mapping page stem → list of crop paths
                     e.g. { "page_003": ["…/page_003_diagram_1.png"] }
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    doc              = fitz.open(pdf_path)
    image_paths      = []
    diagram_map      = {}
    previous_arrays  = []
    skipped          = 0

    print(f"Found {len(doc)} pages in {os.path.basename(pdf_path)}")

    for page_num in range(len(doc)):
        page = doc[page_num]
        mat  = fitz.Matrix(PDF_DPI / 72, PDF_DPI / 72)
        pix  = page.get_pixmap(matrix=mat)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        img = fix_white_ink(img)

        current_arr = image_hash(img)
        if is_duplicate(img, previous_arrays):
            print(f"  Page {page_num + 1}: duplicate detected, skipping")
            skipped += 1
            previous_arrays.append(current_arr)
            continue

        previous_arrays.append(current_arr)

        # Save full-page PNG
        page_stem      = f"page_{page_num + 1:03d}"
        image_filename = f"{page_stem}.png"
        image_path     = os.path.join(OUTPUT_DIR, image_filename)
        img.save(image_path, format="PNG")
        image_paths.append(image_path)
        print(f"  Saved page {page_num + 1} → {image_filename}")

        # Second pass — diagram crops
        crops = extract_diagrams(img, page_stem, OUTPUT_DIR)
        if crops:
            diagram_map[page_stem] = crops
            print(f"    └─ {len(crops)} diagram(s) extracted")

    doc.close()
    print(f"\nDone. {len(image_paths)} pages kept, {skipped} duplicates skipped, "
          f"{sum(len(v) for v in diagram_map.values())} diagram crop(s) total.")

    return image_paths, diagram_map


if __name__ == "__main__":
    test_pdf = input("Enter path to a test PDF: ").strip().strip('"')
    images, diagrams = pdf_to_images(test_pdf)
    print(f"\nDiagram map:")
    for page, crops in diagrams.items():
        for c in crops:
            print(f"  {page} → {os.path.basename(c)}")