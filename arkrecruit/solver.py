from __future__ import annotations

from itertools import combinations

from .data import Operator


def available_tags(operators: list[Operator]) -> list[str]:
    tags = {tag for operator in operators for tag in operator.tags}
    return sorted(tags)


def solve_combinations(
    selected_tags: list[str],
    operators: list[Operator],
    max_size: int = 3,
) -> list[tuple[tuple[str, ...], list[Operator]]]:
    selected = sorted(set(selected_tags))
    results: list[tuple[tuple[str, ...], list[Operator]]] = []

    for size in range(1, min(max_size, len(selected)) + 1):
        for combo in combinations(selected, size):
            combo_set = set(combo)
            matches = [
                operator
                for operator in operators
                if combo_set.issubset(operator.tags)
            ]
            if matches:
                results.append((combo, sorted(matches, key=lambda op: (-op.rarity, op.name))))

    return sorted(
        results,
        key=lambda item: (
            -_min_rarity(item[1]),
            len(item[1]),
            -len(item[0]),
            item[0],
        ),
    )


def _min_rarity(operators: list[Operator]) -> int:
    return min(operator.rarity for operator in operators)

