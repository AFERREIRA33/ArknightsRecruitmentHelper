from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from .data import DATA_ROOT, Operator


IMAGE_ROOT = DATA_ROOT / "operator_images"

ASSET_BASES = [
    "https://raw.githubusercontent.com/ArknightsAssets/ArknightsAssets2/refs/heads/cn/assets/dyn/arts",
    "https://raw.githubusercontent.com/ArknightsAssets/ArknightsAssets2/refs/heads/main/assets/dyn/arts",
]


def operator_image_path(operator: Operator) -> Path | None:
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)

    for path in _cached_candidates(operator):
        if path.exists():
            return path

    for url, target in _download_candidates(operator):
        if _download_image(url, target):
            return target

    return None


def _cached_candidates(operator: Operator) -> list[Path]:
    return [
        IMAGE_ROOT / f"{operator.id}_avatar.png",
        IMAGE_ROOT / f"{operator.id}_portrait_1.png",
        IMAGE_ROOT / f"{operator.id}_portrait_2.png",
    ]


def _download_candidates(operator: Operator) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    for base in ASSET_BASES:
        candidates.extend(
            [
                (
                    f"{base}/charavatars/{operator.id}.png",
                    IMAGE_ROOT / f"{operator.id}_avatar.png",
                ),
                (
                    f"{base}/charavatars/{operator.id}_1.png",
                    IMAGE_ROOT / f"{operator.id}_avatar.png",
                ),
                (
                    f"{base}/charportraits/{operator.id}_1.png",
                    IMAGE_ROOT / f"{operator.id}_portrait_1.png",
                ),
                (
                    f"{base}/charportraits/{operator.id}_2.png",
                    IMAGE_ROOT / f"{operator.id}_portrait_2.png",
                ),
            ]
        )
    return candidates


def _download_image(url: str, target: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "arkrecruit/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except (urllib.error.URLError, TimeoutError):
        return False

    if b"<html" in data[:200].lower() or "image" not in content_type.lower():
        return False

    target.write_bytes(data)
    return True

