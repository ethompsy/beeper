"""Tests for Beeper Investigator main module."""

from beeper_investigator import __version__
from beeper_investigator.main import main


def test_version() -> None:
    """Test version is set."""
    assert __version__ == "0.1.0"


def test_main_runs() -> None:
    """Test main function runs without error."""
    # main() just logs and returns, no assertions needed
    main()
