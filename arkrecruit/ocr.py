from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Iterable


MAX_RECRUITMENT_TAG_SLOTS = 6


@dataclass(frozen=True)
class ScreenRegion:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class ScanResult:
    text: str
    capture_area: str
    image_size: tuple[int, int]
    image_path: Path
    screen_size: tuple[int, int]
    button_texts: tuple[str, ...]
    button_boxes: tuple[str, ...]


def scan_screen_text(region: ScreenRegion | None = None) -> ScanResult:
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError(
            "Screen OCR needs pyautogui and pillow installed. "
            "Run: pip install -r requirements.txt"
        ) from exc

    tesseract = _find_tesseract()
    box = None
    capture_area = "full screen"
    if region:
        box = (region.left, region.top, region.width, region.height)
        capture_area = (
            f"left={region.left}, top={region.top}, "
            f"width={region.width}, height={region.height}"
        )

    screen_size = tuple(pyautogui.size())
    image = pyautogui.screenshot(region=box)
    image_path = _debug_image_path()

    image.save(image_path)
    image_size = tuple(image.size)

    button_texts, button_boxes = _ocr_tag_buttons(tesseract, image)
    if button_texts:
        combined_text = "\n".join(button_texts)
    else:
        full_text = _ocr_image(tesseract, image, psm="6")
        sparse_text = _ocr_image(tesseract, _prepare_for_ocr(image), psm="11")
        combined_text = "\n".join([full_text, sparse_text])

    return ScanResult(
        text=combined_text,
        capture_area=capture_area,
        image_size=image_size,
        image_path=image_path,
        screen_size=screen_size,
        button_texts=button_texts,
        button_boxes=button_boxes,
    )


def screenshot_text(region: ScreenRegion | None = None) -> str:
    return scan_screen_text(region).text


def tags_from_text(text: str, known_tags: Iterable[str]) -> list[str]:
    normalized_text = _normalize(text)
    found: set[str] = set()
    tag_lookup = {_normalize(tag): tag for tag in known_tags}
    normalized_lines = [
        _normalize(line)
        for line in text.splitlines()
        if _normalize(line)
    ]

    for normalized, original in tag_lookup.items():
        if re.search(rf"\b{re.escape(normalized)}\b", normalized_text):
            found.add(original)
        elif _compact(normalized) and _compact(normalized) in _compact(normalized_text):
            found.add(original)

    words = [word for word in re.split(r"[^a-z0-9]+", normalized_text) if word]
    for normalized, original in tag_lookup.items():
        if original in found:
            continue
        match = get_close_matches(normalized, words, n=1, cutoff=0.86)
        if match:
            found.add(original)
            continue
        if _line_matches_tag(normalized, normalized_lines):
            found.add(original)

    return sorted(found)


def tags_from_slot_texts(slot_texts: Iterable[str], known_tags: Iterable[str]) -> list[str]:
    found: set[str] = set()
    tag_lookup = {_normalize(tag): tag for tag in known_tags}

    for slot_text in slot_texts:
        normalized_slot = _normalize(slot_text)
        compact_slot = _compact(normalized_slot)
        if not compact_slot:
            continue

        best_tag = None
        best_ratio = 0.0
        for normalized_tag, original in tag_lookup.items():
            compact_tag = _compact(normalized_tag)
            if not compact_tag:
                continue
            ratio = SequenceMatcher(None, compact_tag, compact_slot).ratio()
            if compact_tag in compact_slot or compact_slot in compact_tag:
                ratio = max(ratio, 0.95)
            if ratio > best_ratio:
                best_ratio = ratio
                best_tag = original

        if best_tag and best_ratio >= 0.72:
            found.add(best_tag)

    return sorted(found)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("-", " ")).strip()


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _line_matches_tag(normalized_tag: str, lines: list[str]) -> bool:
    tag_compact = _compact(normalized_tag)
    if len(tag_compact) < 4:
        return False

    for line in lines:
        line_compact = _compact(line)
        if not line_compact:
            continue
        if len(line_compact) > len(tag_compact) + 4:
            continue
        ratio = SequenceMatcher(None, tag_compact, line_compact).ratio()
        if ratio >= 0.72:
            return True
    return False


def _ocr_image(tesseract: Path, image, psm: str, extra_args: list[str] | None = None) -> str:
    temp_image_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as file:
            temp_image_path = Path(file.name)
        image.save(temp_image_path)
        command = [str(tesseract), str(temp_image_path), "stdout", "--psm", psm]
        if extra_args:
            command.extend(extra_args)
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        if temp_image_path:
            temp_image_path.unlink(missing_ok=True)

    if result.returncode != 0:
        detail = result.stderr.strip() or "Tesseract failed to read the screenshot."
        raise RuntimeError(detail)

    return result.stdout.strip()


def _prepare_for_ocr(image):
    prepared = image.convert("L")
    prepared = prepared.resize((prepared.width * 2, prepared.height * 2))
    return prepared.point(lambda pixel: 255 if pixel > 145 else 0)


def _ocr_tag_buttons(tesseract: Path, image) -> tuple[tuple[str, ...], tuple[str, ...]]:
    prepared_images = []
    boxes: list[str] = []
    for index, (box, crop) in enumerate(_tag_button_crops(image), start=1):
        crop_path = _debug_slot_image_path(index)
        crop.save(crop_path)
        prepared_images.append(_prepare_for_button_ocr(crop))
        left, top, right, bottom = box
        boxes.append(
            f"left={left}, top={top}, width={right - left}, "
            f"height={bottom - top}, image={crop_path}"
        )

    if not prepared_images:
        return (), tuple(boxes)

    whitelist = [
        "-c",
        "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz- ",
    ]
    batch_image = _stack_images(prepared_images)
    text = _ocr_image(tesseract, batch_image, psm="6", extra_args=whitelist)
    texts = [
        cleaned
        for line in text.splitlines()
        if (cleaned := _clean_ocr_text(line))
    ]

    if not texts:
        for prepared in prepared_images:
            text = _ocr_image(tesseract, prepared, psm="7", extra_args=whitelist)
            cleaned = _clean_ocr_text(text)
            if cleaned:
                texts.append(cleaned)

    return tuple(dict.fromkeys(texts)), tuple(boxes)


def _prepare_for_button_ocr(image):
    width, height = image.size
    image = image.crop(
        (
            int(width * 0.10),
            int(height * 0.18),
            int(width * 0.90),
            int(height * 0.82),
        )
    )
    prepared = image.convert("L")
    prepared = prepared.resize((prepared.width * 4, prepared.height * 4))
    return prepared.point(lambda pixel: 0 if pixel > 145 else 255)


def _clean_ocr_text(text: str) -> str:
    text = re.sub(r"[^A-Za-z -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _stack_images(images):
    from PIL import Image

    first = images[0]
    width = max(image.width for image in images)
    padding = max(18, first.height // 3)
    height = sum(image.height for image in images) + padding * (len(images) + 1)
    canvas = Image.new("L", (width, height), 255)

    y = padding
    for image in images:
        x = (width - image.width) // 2
        canvas.paste(image, (x, y))
        y += image.height + padding

    debug_path = Path.cwd() / "debug_screens" / "slots_batch.png"
    debug_path.parent.mkdir(exist_ok=True)
    canvas.save(debug_path)
    return canvas


def _tag_button_crops(image):
    # Arknights recruitment tags are dark, wide buttons in the lower middle of
    # the recruitment panel. Detecting these crops gives OCR a much easier job
    # than reading the entire screen at once.
    scale = 4
    small = image.convert("RGB").resize((image.width // scale, image.height // scale))
    width, height = small.size
    visited: set[tuple[int, int]] = set()
    crops = []

    def is_dark(x: int, y: int) -> bool:
        red, green, blue = small.getpixel((x, y))
        return red + green + blue < 240

    start_y = 0 if image.height < 500 else int(height * 0.35)
    end_y = height if image.height < 500 else int(height * 0.78)
    start_x = 0 if image.width < 900 else int(width * 0.18)
    end_x = width if image.width < 900 else int(width * 0.9)

    for y in range(start_y, end_y):
        for x in range(start_x, end_x):
            if (x, y) in visited or not is_dark(x, y):
                continue

            stack = [(x, y)]
            visited.add((x, y))
            min_x = max_x = x
            min_y = max_y = y

            while stack:
                current_x, current_y = stack.pop()
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)
                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if (
                        next_x < 0
                        or next_y < 0
                        or next_x >= width
                        or next_y >= height
                        or (next_x, next_y) in visited
                        or not is_dark(next_x, next_y)
                    ):
                        continue
                    visited.add((next_x, next_y))
                    stack.append((next_x, next_y))

            box_width = (max_x - min_x + 1) * scale
            box_height = (max_y - min_y + 1) * scale
            aspect = box_width / max(box_height, 1)
            if not (110 <= box_width <= 330 and 32 <= box_height <= 100 and 1.8 <= aspect <= 6):
                continue

            left = max(min_x * scale - 12, 0)
            top = max(min_y * scale - 8, 0)
            right = min((max_x + 1) * scale + 12, image.width)
            bottom = min((max_y + 1) * scale + 8, image.height)
            box = (left, top, right, bottom)
            crops.append((top, left, box, image.crop(box)))

    return _choose_tag_slot_crops(crops, image.width, image.height)


def _choose_tag_slot_crops(crops, image_width: int, image_height: int):
    if image_width >= 900 and image_height >= 500:
        # Full-screen captures include other dark controls. Recruitment tag
        # slots live in the lower-middle panel, so prefer that band and keep
        # only the six possible tag slots.
        crops = [
            item
            for item in crops
            if 0.47 <= ((item[2][1] + item[2][3]) / 2 / image_height) <= 0.68
        ]

        def score(item) -> tuple[float, int, int]:
            top, left, box, _crop = item
            box_left, box_top, box_right, box_bottom = box
            center_x = (box_left + box_right) / 2 / image_width
            center_y = (box_top + box_bottom) / 2 / image_height
            y_distance = _distance_from_range(center_y, 0.48, 0.66)
            x_distance = _distance_from_range(center_x, 0.25, 0.78)
            return (y_distance * 4 + x_distance, top, left)

        crops = sorted(crops, key=score)[:MAX_RECRUITMENT_TAG_SLOTS]

    crops.sort(key=lambda item: (item[0], item[1]))
    return [
        (box, crop)
        for _top, _left, box, crop in crops[:MAX_RECRUITMENT_TAG_SLOTS]
    ]


def _distance_from_range(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum - value
    if value > maximum:
        return value - maximum
    return 0.0


def _debug_image_path() -> Path:
    debug_dir = Path.cwd() / "debug_screens"
    debug_dir.mkdir(exist_ok=True)
    return debug_dir / "latest_scan.png"


def _debug_slot_image_path(index: int) -> Path:
    debug_dir = Path.cwd() / "debug_screens"
    debug_dir.mkdir(exist_ok=True)
    return debug_dir / f"slot_{index}.png"


def _find_tesseract() -> Path:
    path = shutil.which("tesseract")
    if path:
        return Path(path)

    common_paths = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    for candidate in common_paths:
        if candidate.exists():
            return candidate

    raise RuntimeError(
        "Tesseract OCR is not installed or is not in PATH. "
        "Install Tesseract OCR, then restart the app."
    )
