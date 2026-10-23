"""Verification of README structure, required sections, and banned phrasing."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_FILE = REPO_ROOT / "README.md"

REQUIRED_PHRASES = [
    "Why Celesto and not a Docker container or E2B",
    "What would break at 1,000 users",
    "AI coding assistants are allowed. Disclose which ones you used in your README.",
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


def test_readme_exists_and_contains_required_phrases():
    assert README_FILE.exists(), "README.md is missing"
    content = README_FILE.read_text(encoding="utf-8")

    for phrase in REQUIRED_PHRASES:
        assert phrase.lower() in content.lower(), f"Missing required phrase in README: '{phrase}'"


def test_readme_no_secrets():
    content = README_FILE.read_text(encoding="utf-8")
    assert "cel_pat_" not in content, "README must not leak Celesto personal access tokens"
    assert "gsk_" not in content, "README must not leak Groq API keys"


def test_readme_no_banned_words():
    content = README_FILE.read_text(encoding="utf-8")
    # Exclude code fences or markdown links if any
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
