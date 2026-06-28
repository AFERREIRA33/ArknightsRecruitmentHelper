from arkrecruit.ocr import tags_from_slot_texts


def test_slot_texts_are_source_of_truth_without_full_screen_noise():
    known_tags = [
        "AoE",
        "Defender",
        "Defense",
        "Guard",
        "Medic",
        "Slow",
        "Vanguard",
    ]

    tags = tags_from_slot_texts(
        ["Defender", "Medic", "Vanguard", "Defense", "Slow"],
        known_tags,
    )

    assert tags == ["Defender", "Defense", "Medic", "Slow", "Vanguard"]

