"""Tests for the benchmark metrics. These are pure functions and need no Ollama."""

from __future__ import annotations

from evaluate import auroc, calibration_table, format_matches, is_duplicate, keyword_match


def test_keyword_match_requires_all_keywords():
    assert keyword_match("Mira completed the episode schema", ["mira", "schema"])
    assert not keyword_match("Mira completed the episode schema", ["mira", "database"])


def test_duplicate_detection_is_type_and_text_aware():
    first = {
        "event_type": "preference",
        "title": "Communication preference",
        "summary": "User prefers concise bullet points.",
        "facts": ["User prefers concise bullet points."],
    }
    same = {
        "event_type": "preference",
        "title": "Communication preference",
        "summary": "User prefers concise bullet points.",
        "facts": ["User prefers concise bullet points."],
    }
    different_type = {**same, "event_type": "decision"}
    assert is_duplicate(first, same) is True
    assert is_duplicate(first, different_type) is False


def test_auroc_rewards_correct_ranking_and_handles_ties():
    assert auroc([0.9, 0.8, 0.2], [1, 0, 0]) == 1.0
    assert auroc([0.1, 0.2, 0.9], [1, 0, 0]) == 0.0
    assert auroc([0.5, 0.5], [1, 0]) == 0.5


def test_calibration_table_counts_every_point():
    pairs = [(0.1, 0), (0.5, 1), (0.9, 1), (0.7, 0)]
    table = calibration_table(pairs)
    assert sum(row["n"] for row in table) == len(pairs)
    high_band = next(row for row in table if row["band"] == "0.80-1.00")
    assert high_band["precision"] == 1.0


def test_format_matches_bullets_and_table():
    bullets = "- First point\n- Second point"
    table = "| A | B |\n|---|---|\n| 1 | 2 |"
    assert format_matches(bullets, "bullets") is True
    assert format_matches(table, "table") is True
    assert format_matches("plain prose", "bullets") is False
