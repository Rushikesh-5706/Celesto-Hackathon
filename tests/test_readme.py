"""Verification of README structure, required sections, and banned phrasing."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_FILE = REPO_ROOT / "README.md"

REQUIRED_HEADINGS = [
    "Problem statement",
    "How I used Celesto",
    "Eval report",
    "Containment test",
    "State and failure design",
    "Setup",
]

BANNED_WORDS = [
    "delve",
    "comprehensive",
    "robust",
    "seamless",
    "leverage",
    "utilize",
    "streamline",
    "cutting-edge",
    "state-of-the-art",
    "game-changer",
    "empower",
    "holistic",
    "synergy",
    "tapestry",
    "crucial",
    "pivotal",
    "ensure that",
    "it is worth noting",
    "in conclusion",
    "moreover",
    "furthermore",
    "additionally",
    "in today's",
]


def test_readme_exists_and_contains_required_headings():
    assert README_FILE.exists(), "README.md is missing"
    content = README_FILE.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        assert (
            heading.lower() in content.lower()
        ), f"Missing required heading in README: '{heading}'"


def test_readme_no_secrets():
    content = README_FILE.read_text(encoding="utf-8")
    assert "cel_pat_" not in content, "README must not leak Celesto personal access tokens"
    assert "gsk_" not in content, "README must not leak Groq API keys"


def test_readme_no_banned_words_and_dashes():
    content = README_FILE.read_text(encoding="utf-8")

    assert "\u2013" not in content, "README must not contain en dashes"
    assert "\u2014" not in content, "README must not contain em dashes"

    emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)
    assert not emoji_pattern.findall(content), "README must not contain emojis"

    words = re.findall(r"\b[a-zA-Z-']+\b", content.lower())

    violations = []
    for banned in BANNED_WORDS:
        if " " in banned:
            if banned in content.lower():
                violations.append(banned)
        else:
            if banned in words:
                violations.append(banned)

    assert not violations, f"Banned marketing/AI phrases found in README: {violations}"
