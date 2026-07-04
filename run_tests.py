"""Run the test suite with a DEBUG log and a JSON results summary in `logs/`.

Usage: python run_tests.py
"""
from __future__ import annotations

from tests.json_test_runner import run

if __name__ == "__main__":
    raise SystemExit(run())
