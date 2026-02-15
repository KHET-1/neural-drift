"""Tests for neuraldrift.helpers — utility functions."""

import pytest
import json
from pathlib import Path
from neuraldrift.helpers import save_json, load_json, timestamp


class TestJsonRoundTrip:
    def test_save_load_json(self, tmp_path):
        """Atomic JSON round-trip."""
        filepath = tmp_path / "test.json"
        data = {"key": "value", "nested": {"a": 1, "b": [1, 2, 3]}}
        save_json(data, str(filepath))
        loaded = load_json(str(filepath))
        assert loaded == data

    def test_save_json_atomic(self, tmp_path):
        """File exists after atomic save (no partial writes)."""
        filepath = tmp_path / "atomic.json"
        save_json({"hello": "world"}, str(filepath))
        assert filepath.exists()
        # Verify it's valid JSON
        with open(filepath) as f:
            data = json.load(f)
        assert data["hello"] == "world"


class TestLoadJsonEdgeCases:
    def test_load_json_missing_file(self, tmp_path):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_json(str(tmp_path / "nonexistent.json"))


class TestTimestamp:
    def test_timestamp_format(self):
        """Timestamp returns expected default format."""
        ts = timestamp()
        # Default format: %Y-%m-%d_%H-%M-%S
        parts = ts.split("_")
        assert len(parts) == 2
        date_part = parts[0]
        time_part = parts[1]
        # Date: YYYY-MM-DD
        assert len(date_part.split("-")) == 3
        # Time: HH-MM-SS
        assert len(time_part.split("-")) == 3

    def test_timestamp_custom_format(self):
        """Timestamp accepts custom format."""
        ts = timestamp(fmt="%Y%m%d")
        assert len(ts) == 8
        assert ts.isdigit()
