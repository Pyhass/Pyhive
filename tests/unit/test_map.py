"""Unit tests for Map — dot-notation dict wrapper."""

import pytest
from apyhiveapi.helper.map import Map


def test_attribute_read():
    """Test attribute-style read access on Map."""
    m = Map({"key": "value"})
    assert m.key == "value"


def test_dict_read():
    """Test bracket-style dict read access on Map."""
    m = Map({"key": "value"})
    assert m["key"] == "value"


def test_missing_key_raises_attribute_error():
    """Missing attribute access raises AttributeError."""
    m = Map({})
    with pytest.raises(AttributeError):
        _ = m.missing


def test_missing_bracket_key_raises_key_error():
    """Missing bracket access raises KeyError (standard dict behaviour)."""
    m = Map({})
    with pytest.raises(KeyError):
        _ = m["missing"]


def test_nested_access():
    """Test nested dict access through Map."""
    m = Map({"products": {"id-1": {"state": "ON"}}})
    assert m.products["id-1"]["state"] == "ON"


def test_attribute_write():
    """Test attribute-style write access on Map."""
    m = Map({})
    m.foo = "bar"
    assert m["foo"] == "bar"


class TestMapDelAttr:
    """Map.__delattr__ must raise AttributeError (not KeyError) for missing keys."""

    def test_delattr_missing_key_raises_attribute_error(self):
        """del m.missing raises AttributeError, not KeyError."""
        m = Map({"a": 1})
        with pytest.raises(AttributeError):
            del m.nonexistent
