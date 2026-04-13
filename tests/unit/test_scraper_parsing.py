"""Unit tests for scraper parsing helpers (no network calls)."""

import pytest
from datetime import date

from scraper.rbi_scraper import _parse_date, _normalize_circular_id


class TestParseDate:
    def test_long_month_format(self):
        assert _parse_date("January 15, 2024") == date(2024, 1, 15)

    def test_dmy_dash(self):
        assert _parse_date("15-01-2024") == date(2024, 1, 15)

    def test_dmy_slash(self):
        assert _parse_date("15/01/2024") == date(2024, 1, 15)

    def test_iso_format(self):
        assert _parse_date("2024-01-15") == date(2024, 1, 15)

    def test_unparseable_returns_none(self):
        assert _parse_date("not a date") is None

    def test_whitespace_stripped(self):
        assert _parse_date("  2024-01-15  ") == date(2024, 1, 15)


class TestNormalizeCircularId:
    def test_standard_format(self):
        assert _normalize_circular_id("RBI/2024-25/67") == "RBI/2024-25/67"

    def test_department_format(self):
        result = _normalize_circular_id("RBI/DPSS/2023-24/123 Some Title")
        assert result == "RBI/DPSS/2023-24/123"

    def test_not_found_returns_none(self):
        assert _normalize_circular_id("Some random text without ID") is None

    def test_embedded_in_sentence(self):
        result = _normalize_circular_id("Circular No. RBI/2024-25/45 dated")
        assert result == "RBI/2024-25/45"
