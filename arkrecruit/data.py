from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATA_ROOT = Path(
    os.environ.get("ARKRECRUIT_DATA_DIR", Path.cwd() / ".arkrecruit_cache")
)
GAME_DATA_BASE = (
    "https://raw.githubusercontent.com/ArknightsAssets/ArknightsGamedata/master/"
    "en/gamedata/excel"
)

CHARACTER_TABLE_URL = f"{GAME_DATA_BASE}/character_table.json"
GACHA_TABLE_URL = f"{GAME_DATA_BASE}/gacha_table.json"

RARITY_LABELS = {
    0: "1★",
    1: "2★",
    2: "3★",
    3: "4★",
    4: "5★",
    5: "6★",
}

POSITION_TAGS = {
    "MELEE": "Melee",
    "RANGED": "Ranged",
}

PROFESSION_TAGS = {
    "PIONEER": "Vanguard",
    "WARRIOR": "Guard",
    "TANK": "Defender",
    "SNIPER": "Sniper",
    "CASTER": "Caster",
    "MEDIC": "Medic",
    "SUPPORT": "Supporter",
    "SPECIAL": "Specialist",
}


@dataclass(frozen=True)
class Operator:
    id: str
    name: str
    rarity: int
    tags: frozenset[str]

    @property
    def rarity_label(self) -> str:
        return RARITY_LABELS.get(self.rarity, f"{self.rarity + 1}★")


def ensure_data(cache_dir: Path = DATA_ROOT) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    character_path = cache_dir / "character_table.json"
    gacha_path = cache_dir / "gacha_table.json"

    _download_if_missing(CHARACTER_TABLE_URL, character_path)
    _download_if_missing(GACHA_TABLE_URL, gacha_path)

    return character_path, gacha_path


def refresh_data(cache_dir: Path = DATA_ROOT) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    character_path = cache_dir / "character_table.json"
    gacha_path = cache_dir / "gacha_table.json"

    _download(CHARACTER_TABLE_URL, character_path)
    _download(GACHA_TABLE_URL, gacha_path)

    return character_path, gacha_path


def load_operators(cache_dir: Path = DATA_ROOT) -> list[Operator]:
    character_path, gacha_path = ensure_data(cache_dir)
    characters = _read_json(character_path)
    gacha = _read_json(gacha_path)
    recruit_names = _extract_recruitment_names(gacha)

    operators: list[Operator] = []
    for character_id, raw in characters.items():
        name = raw.get("name")
        if not name or name not in recruit_names:
            continue
        if raw.get("isNotObtainable"):
            continue

        tags = _operator_tags(raw)
        if tags:
            operators.append(
                Operator(
                    id=character_id,
                    name=name,
                    rarity=_rarity_index(raw.get("rarity", 0)),
                    tags=frozenset(tags),
                )
            )

    return sorted(operators, key=lambda op: (-op.rarity, op.name))


def _download_if_missing(url: str, target: Path) -> None:
    if target.exists():
        return
    _download(url, target)


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "arkrecruit/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        target.write_bytes(response.read())


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _extract_recruitment_names(gacha: dict[str, Any]) -> set[str]:
    details = str(gacha.get("recruitDetail", ""))
    names = _names_from_recruit_detail(details)

    # The table format has changed a few times. These nested keys are cheap to
    # support and keep the loader resilient when the public game data shifts.
    for key in ("recruitPool", "recruitCharPool"):
        pool = gacha.get(key)
        if isinstance(pool, list):
            for item in pool:
                if isinstance(item, str):
                    names.add(item)
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    names.add(item["name"])

    if not names:
        raise ValueError("Could not find recruitment operator names in gacha_table.json")

    return names


def _names_from_recruit_detail(details: str) -> set[str]:
    names: set[str] = set()
    cleaned = re.sub(r"<[^>]+>", "", details).replace("\\n", "\n")
    lines = [line.strip() for line in cleaned.splitlines()]

    in_operator_section = False
    expecting_names = False
    for line in lines:
        if "All Possible Operators" in line:
            in_operator_section = True
            continue
        if not in_operator_section:
            continue
        if line.startswith("-"):
            expecting_names = False
            continue
        if line and set(line) <= {"★"}:
            expecting_names = True
            continue
        if expecting_names and line:
            names.update(_split_operator_names(line))
            expecting_names = False

    return names


def _split_operator_names(line: str) -> set[str]:
    names: set[str] = set()
    for name in line.split("/"):
        cleaned = name.strip()
        if cleaned:
            names.add(cleaned)
    return names


def _operator_tags(raw: dict[str, Any]) -> set[str]:
    tags: set[str] = set()

    position = raw.get("position")
    if position in POSITION_TAGS:
        tags.add(POSITION_TAGS[position])

    profession = raw.get("profession")
    if profession in PROFESSION_TAGS:
        tags.add(PROFESSION_TAGS[profession])

    for tag in raw.get("tagList") or []:
        if isinstance(tag, str):
            tags.add(tag)

    rarity = _rarity_index(raw.get("rarity", 0))
    if rarity == 4:
        tags.add("Senior Operator")
    if rarity == 5:
        tags.add("Top Operator")

    return tags


def _rarity_index(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"TIER_(\d+)", value)
        if match:
            return int(match.group(1)) - 1
        if value.isdigit():
            return int(value)
    return 0
