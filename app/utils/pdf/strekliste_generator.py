from __future__ import annotations

import io
import os
import re
from typing import TYPE_CHECKING

from config import AppConfig

if TYPE_CHECKING:
    import fitz
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

try:
    import fitz  # PyMuPDF

    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


"""
Strekliste Generator Module
Generates shift timeline PNG images from strekliste PDF files.

This module extracts individual shift rows from a strekliste PDF and renders
them as PNG images with an hour ruler (0-23).

Adapted from the standalone strekliste API.
"""

# Shift numbers appear in the leftmost "Nr." column
# For rotated pages, we need to transform coordinates from PDF space to visual space
SHIFT_NR_VISUAL_X_MAX = 50  # Shift numbers are within 50 pixels of left edge visually

# Sets the resolution of the .png files. Higher value = Higher resolution and file size.
PDF_ZOOM = 4


def get_paths(version: str) -> dict:
    """
    Get the PDF path and images directory for a given version.

    Args:
        version: The turnus version identifier (e.g., 'r26')

    Returns:
        dict with 'pdf_path', 'images_dir', and 'exists' status
    """
    version = version.lower()
    base_dir = os.path.join(AppConfig.turnusfiler_dir, version, "streklister")
    pdf_path = os.path.join(base_dir, f"{version}_streker.pdf")
    images_dir = os.path.join(base_dir, "png")

    return {
        "pdf_path": pdf_path,
        "images_dir": images_dir,
        "pdf_exists": os.path.exists(pdf_path),
        "images_dir_exists": os.path.exists(images_dir),
    }


def get_strekliste_status(version: str) -> dict:
    """
    Check the status of strekliste for a given version.

    Returns:
        dict with status information:
        - pdf_exists: bool
        - image_count: int (number of PNG files)
        - status: str ('no_pdf', 'pdf_ready', 'images_generated')
    """
    paths = get_paths(version)

    image_count = 0
    if paths["images_dir_exists"]:
        try:
            image_count = len(
                [f for f in os.listdir(paths["images_dir"]) if f.endswith(".png")]
            )
        except OSError:
            image_count = 0

    if not paths["pdf_exists"]:
        status = "no_pdf"
    elif image_count == 0:
        status = "pdf_ready"
    else:
        status = "images_generated"

    return {
        "pdf_exists": paths["pdf_exists"],
        "image_count": image_count,
        "status": status,
        "pdf_path": paths["pdf_path"],
        "images_dir": paths["images_dir"],
    }


def get_shift_rows(page) -> list:
    """
    Find all shift numbers and their visual y-positions on a page.
    Handles page rotation by transforming coordinates.
    Returns list of dicts with {nr, nr_base, visual_y, bbox, suffix} sorted by visual y position.
    """
    if not FITZ_AVAILABLE:
        raise RuntimeError("PyMuPDF (fitz) is required but not installed")

    shifts = []
    leftmost_texts = []  # All text in leftmost column for suffix detection
    blocks = page.get_text("dict")["blocks"]
    pattern = re.compile(r"^(\d{4,5})(?:-.*)?$")

    # Get transformation matrix from PDF coords to visual coords
    # Inverse of derotation_matrix transforms to visual space
    transform = ~page.derotation_matrix

    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue
                bbox = span["bbox"]

                # Transform bbox to visual coordinates
                visual_point = fitz.Point(bbox[0], bbox[1]) * transform

                # Look for text in the leftmost column (visually)
                if visual_point.x < SHIFT_NR_VISUAL_X_MAX:
                    match = pattern.match(text)
                    if match:
                        shifts.append(
                            {
                                "nr": text,
                                "nr_base": match.group(1),
                                "visual_y": visual_point.y,
                                "visual_x": visual_point.x,
                                "bbox": bbox,
                                "suffix": None,  # Will be populated later
                            }
                        )
                    else:
                        # Non-shift text in leftmost column (potential suffix)
                        leftmost_texts.append(
                            {
                                "text": text,
                                "visual_y": visual_point.y,
                                "visual_x": visual_point.x,
                            }
                        )

    # Sort by visual y position (top to bottom as seen)
    shifts.sort(key=lambda x: x["visual_y"])

    # Find suffix text for each shift
    # Suffix is text that appears below a shift number but before the next shift
    # Pattern to detect time strings (e.g., "20:20", "7:30") which should not be suffixes
    time_pattern = re.compile(r"^\d{1,2}:\d{2}$")

    for i, shift in enumerate(shifts):
        # Determine y-range for suffix: between this shift and next shift
        y_start = shift["visual_y"]
        if i < len(shifts) - 1:
            y_end = shifts[i + 1]["visual_y"]
        else:
            # Last shift on page - use conservative distance to avoid capturing
            # text from below the separator line (like times from next shift)
            y_end = shift["visual_y"] + 25

        # Find suffix texts in this range (with some tolerance)
        x_tolerance = 15  # Must be close to same x position
        suffix_parts = []
        for txt in leftmost_texts:
            # Skip time strings - they belong to shift schedules, not names
            if time_pattern.match(txt["text"]):
                continue
            if (
                txt["visual_y"] > y_start + 5  # Below shift number
                and txt["visual_y"] < y_end - 5  # Above next shift
                and abs(txt["visual_x"] - shift["visual_x"]) < x_tolerance
            ):
                suffix_parts.append((txt["visual_y"], txt["text"]))

        if suffix_parts:
            # Sort by y position and join
            suffix_parts.sort(key=lambda x: x[0])
            shift["suffix"] = " ".join(part[1] for part in suffix_parts)

    return shifts


def get_full_shift_name(shift: dict) -> str:
    """Create filename-safe full shift name with underscores instead of whitespace."""
    name = shift["nr"]
    if shift.get("suffix"):
        # Remove invalid filename chars
        suffix = re.sub(r'[\\/*?:"<>|]', "", shift["suffix"])
        name = f"{name}{suffix}"
    # Replace all whitespace with underscores for consistent matching
    name = re.sub(r"\s+", "_", name)
    return name


def find_row_bounds(page, shift_nr: str) -> tuple | None:
    """
    Find the visual y-bounds (row) for a specific shift on a page.
    Returns (y_top, y_bottom, shift_info) or None if not found.
    """
    shifts = get_shift_rows(page)

    # Get visual page dimensions
    if page.rotation in (90, 270):
        visual_height = page.rect.width
    else:
        visual_height = page.rect.height

    for i, shift in enumerate(shifts):
        if (
            shift["nr"] == shift_nr
            or shift["nr_base"] == shift_nr
            or shift_nr in shift["nr"]
        ):
            # Top of row: slightly above this shift
            y_top = shift["visual_y"] - 5

            # Bottom of row: midpoint to next shift, or reasonable height
            if i < len(shifts) - 1:
                y_bottom = (shift["visual_y"] + shifts[i + 1]["visual_y"]) / 2 + 5
            else:
                y_bottom = min(shift["visual_y"] + 60, visual_height - 10)

            return (y_top, y_bottom, shift)

    return None


def find_separator_lines(
    img, min_thickness: int = 2, max_brightness: int = 100
) -> list:
    """
    Detect horizontal black separator lines in the image.
    Returns list of y-positions where thick black lines are found.
    Only returns lines that are at least min_thickness pixels thick
    and where the darkest row in the group has mean brightness below max_brightness.
    Real separator lines span most of the page width, giving very low mean brightness
    (typically 30-80), while text/content rows are much brighter (140-180).
    """
    if not PIL_AVAILABLE:
        return []

    gray = img.convert("L")
    arr = np.array(gray)
    row_brightness = np.mean(arr, axis=1)

    threshold = 180
    dark_rows = np.where(row_brightness < threshold)[0]

    if len(dark_rows) == 0:
        return []

    # Group consecutive dark rows and filter by thickness + darkness
    lines = []
    start = dark_rows[0]
    prev = dark_rows[0]

    for row in dark_rows[1:]:
        if row - prev > 3:  # Gap indicates a new line
            thickness = prev - start + 1
            if thickness >= min_thickness:
                # Check that at least one row in the group is truly dark
                # (real separator lines have very low mean brightness)
                group_min_brightness = np.min(row_brightness[start : prev + 1])
                if group_min_brightness < max_brightness:
                    lines.append((start + prev) // 2)
            start = row
        prev = row

    # Don't forget the last group
    thickness = prev - start + 1
    if thickness >= min_thickness:
        group_min_brightness = np.min(row_brightness[start : prev + 1])
        if group_min_brightness < max_brightness:
            lines.append((start + prev) // 2)

    return lines


def create_hour_ruler(
    width: int, height: int = 30, zoom: int = 1
) -> Image.Image | None:
    """Create a horizontal ruler showing hours 0-23."""
    if not PIL_AVAILABLE:
        return None

    # Scale height with zoom for proportional appearance
    scaled_height = int(height * zoom / 3)
    ruler = Image.new("RGB", (width, scaled_height), "white")
    draw = ImageDraw.Draw(ruler)

    # Timeline positions as ratios of width (zoom-independent)
    # These ratios represent where the timeline starts and ends in the cropped image
    timeline_start_ratio = (
        0.149  # Timeline starts at ~30% from left (shift info column)
    )
    timeline_end_ratio = 0.969  # Timeline ends at ~97% (margin on right)

    timeline_start = int(width * timeline_start_ratio)
    timeline_end = int(width * timeline_end_ratio)

    # Font size scales with zoom - adjust base size (12) as needed
    font_size = int(5 * zoom)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    # Draw hour marks 0-23
    y_pos = scaled_height // 2
    for hour in range(24):
        x = timeline_start + (hour / 23) * (timeline_end - timeline_start)
        # Use anchor='mm' (middle-middle) to center text on both axes
        draw.text((x, y_pos), str(hour), fill="black", anchor="mm", font=font)

    return ruler


def render_shift_image(shift_nr: str, version: str) -> bytes | None:
    """Render a shift row as PNG image bytes."""
    if not FITZ_AVAILABLE or not PIL_AVAILABLE:
        return None

    paths = get_paths(version)
    pdf_path = paths["pdf_path"]

    if not os.path.exists(pdf_path):
        return None

    # Crop margins (base values for zoom=1, will be scaled)
    x_left_base = 22
    x_right_crop_base = 271  # Amount to crop from right side

    doc = fitz.open(pdf_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        bounds = find_row_bounds(page, shift_nr)

        if bounds:
            y_approx_top, y_approx_bottom, shift_info = bounds

            zoom = PDF_ZOOM
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL
            img = Image.open(io.BytesIO(pix.tobytes("png")))

            # Detect separator lines in the image
            separator_lines = find_separator_lines(img)

            # Find the shift's approximate y position in image coordinates
            shift_y = int(shift_info["visual_y"] * zoom)

            # Scale crop margins by zoom level
            x_left = int(x_left_base * zoom)
            x_right_crop = int(x_right_crop_base * zoom)

            # Find the separator line just above this shift (top boundary)
            lines_above = [y for y in separator_lines if y < shift_y]
            y_top = (
                max(lines_above) if lines_above else max(0, shift_y - int(10 * zoom))
            )

            # Find the separator line just below this shift (bottom boundary)
            lines_below = [y for y in separator_lines if y > shift_y]
            y_bottom = (
                min(lines_below) + 2
                if lines_below
                else min(img.height, shift_y + int(40 * zoom))
            )

            crop_box = (x_left, y_top, img.width - x_right_crop, y_bottom)

            cropped = img.crop(crop_box)

            # Create and attach hour ruler
            ruler = create_hour_ruler(cropped.width, zoom=zoom)
            if ruler is not None:
                combined = Image.new(
                    "RGB", (cropped.width, cropped.height + ruler.height), "white"
                )
                combined.paste(ruler, (0, 0))
                combined.paste(cropped, (0, ruler.height))
            else:
                combined = cropped

            # Convert back to bytes
            output = io.BytesIO()
            combined.save(output, format="PNG")
            img_bytes = output.getvalue()

            doc.close()
            return img_bytes

    doc.close()
    return None


def get_all_shifts(version: str) -> list:
    """Get all shifts from the PDF with their full info."""
    if not FITZ_AVAILABLE:
        return []

    paths = get_paths(version)
    pdf_path = paths["pdf_path"]

    if not os.path.exists(pdf_path):
        return []

    doc = fitz.open(pdf_path)
    all_shifts = []
    seen = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        shifts = get_shift_rows(page)

        for shift in shifts:
            full_name = get_full_shift_name(shift)
            if full_name not in seen:
                seen.add(full_name)
                all_shifts.append(shift)

    doc.close()
    return all_shifts


def generate_all_images(
    version: str, force: bool = False, progress_callback=None
) -> dict:
    """
    Pre-generate images for all shifts.

    Optimized to process page-by-page instead of shift-by-shift:
    - Opens PDF once
    - Renders each page once (reused for all shifts on that page)
    - Detects separator lines once per page

    Args:
        version: The turnus version (e.g., 'r26')
        force: If True, regenerate even if images already exist
        progress_callback: Optional callback function(current, total, shift_nr)

    Returns:
        dict with 'success', 'generated', 'skipped', 'errors', 'total'
    """
    if not FITZ_AVAILABLE:
        return {"success": False, "error": "PyMuPDF (fitz) is not installed"}

    if not PIL_AVAILABLE:
        return {"success": False, "error": "Pillow (PIL) is not installed"}

    paths = get_paths(version)

    if not paths["pdf_exists"]:
        return {"success": False, "error": f"PDF not found: {paths['pdf_path']}"}

    # Ensure output directory exists
    os.makedirs(paths["images_dir"], exist_ok=True)

    # Clear existing images if force regeneration
    if force:
        for filename in os.listdir(paths["images_dir"]):
            if filename.endswith(".png"):
                os.remove(os.path.join(paths["images_dir"], filename))

    # Open PDF once
    doc = fitz.open(paths["pdf_path"])

    # Collect all shifts with their page numbers in a single pass
    all_shifts = []
    seen = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        shifts = get_shift_rows(page)

        for shift in shifts:
            full_name = get_full_shift_name(shift)
            if full_name not in seen:
                seen.add(full_name)
                shift["page_num"] = page_num
                shift["full_name"] = full_name
                all_shifts.append(shift)

    total = len(all_shifts)
    generated = []
    skipped = []
    errors = []

    # Crop margins (base values for zoom=1, will be scaled)
    zoom = PDF_ZOOM
    x_left = int(22 * zoom)
    x_right_crop = int(271 * zoom)

    # Page-level cache
    current_page_num = None
    page_img = None
    separator_lines = None

    for idx, shift in enumerate(all_shifts):
        full_name = shift["full_name"]
        img_path = os.path.join(paths["images_dir"], f"{full_name}.png")

        if os.path.exists(img_path) and not force:
            skipped.append(full_name)
            if progress_callback:
                progress_callback(idx + 1, total, full_name)
            continue

        try:
            # Only re-render page if we moved to a new page
            if shift["page_num"] != current_page_num:
                current_page_num = shift["page_num"]
                page = doc[current_page_num]

                # Render page once
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                page_img = Image.open(io.BytesIO(pix.tobytes("png")))

                # Detect separator lines once per page
                separator_lines = find_separator_lines(page_img)

            # Safety check: ensure page was rendered
            if page_img is None or separator_lines is None:
                continue

            # Find crop bounds for this shift using cached separator lines
            shift_y = int(shift["visual_y"] * zoom)

            # Find the separator line just above this shift (top boundary)
            lines_above = [y for y in separator_lines if y < shift_y]
            y_top = (
                max(lines_above) if lines_above else max(0, shift_y - int(10 * zoom))
            )

            # Find the separator line just below this shift (bottom boundary)
            lines_below = [y for y in separator_lines if y > shift_y]
            y_bottom = (
                min(lines_below) + 2
                if lines_below
                else min(page_img.height, shift_y + int(40 * zoom))
            )

            crop_box = (x_left, y_top, page_img.width - x_right_crop, y_bottom)

            cropped = page_img.crop(crop_box)

            # Create and attach hour ruler
            ruler = create_hour_ruler(cropped.width, zoom=zoom)
            if ruler is not None:
                combined = Image.new(
                    "RGB", (cropped.width, cropped.height + ruler.height), "white"
                )
                combined.paste(ruler, (0, 0))
                combined.paste(cropped, (0, ruler.height))
            else:
                combined = cropped

            # Save to file
            combined.save(img_path, format="PNG")
            generated.append(full_name)

        except Exception as e:
            errors.append({"shift_nr": full_name, "error": str(e)})

        if progress_callback:
            progress_callback(idx + 1, total, full_name)

    doc.close()

    return {
        "success": True,
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
        "total": total,
    }


def delete_all_images(version: str) -> dict:
    """
    Delete all generated PNG images for a version.

    Args:
        version: The turnus version (e.g., 'r26')

    Returns:
        dict with 'success', 'deleted_count', or 'error'
    """
    paths = get_paths(version)

    if not paths["images_dir_exists"]:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "No images directory exists",
        }

    deleted_count = 0
    errors = []

    try:
        for filename in os.listdir(paths["images_dir"]):
            if filename.endswith(".png"):
                try:
                    os.remove(os.path.join(paths["images_dir"], filename))
                    deleted_count += 1
                except OSError as e:
                    errors.append({"file": filename, "error": str(e)})
    except OSError as e:
        return {"success": False, "error": f"Failed to access images directory: {e}"}

    return {"success": True, "deleted_count": deleted_count, "errors": errors}


def save_uploaded_pdf(file_storage, version: str) -> dict:
    """
    Save an uploaded PDF file to the correct location.

    Args:
        file_storage: Flask FileStorage object
        version: The turnus version (e.g., 'r26')

    Returns:
        dict with 'success' and 'path' or 'error'
    """
    version = version.lower()
    paths = get_paths(version)

    # Ensure directory exists
    base_dir = os.path.dirname(paths["pdf_path"])
    os.makedirs(base_dir, exist_ok=True)

    try:
        file_storage.save(paths["pdf_path"])
        return {"success": True, "path": paths["pdf_path"]}
    except Exception as e:
        return {"success": False, "error": str(e)}
