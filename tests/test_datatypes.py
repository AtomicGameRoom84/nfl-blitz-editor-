"""Typed encode/decode and user input parsing."""

from __future__ import annotations

import pytest

from core.datatypes import DataType, Endian, parse_hex_bytes, parse_number


@pytest.mark.parametrize("data_type", list(DataType))
def test_encode_decode_round_trip(data_type):
    value = 1.5 if data_type.is_float else 1
    for endian in Endian:
        encoded = data_type.encode(value, endian)
        assert len(encoded) == data_type.size
        assert data_type.decode(encoded, endian) == value


def test_endianness_matters():
    assert DataType.U16.encode(1, Endian.BIG) == b"\x00\x01"
    assert DataType.U16.encode(1, Endian.LITTLE) == b"\x01\x00"


def test_out_of_range_is_rejected_not_wrapped():
    with pytest.raises(ValueError, match="outside the range"):
        DataType.U8.encode(256)
    with pytest.raises(ValueError, match="outside the range"):
        DataType.S8.encode(-129)


def test_decode_requires_enough_bytes():
    with pytest.raises(ValueError, match="needs 4 bytes"):
        DataType.U32.decode(b"\x00\x01")


def test_from_string_aliases():
    assert DataType.from_string("Byte") is DataType.U8
    assert DataType.from_string("uint16") is DataType.U16
    assert DataType.from_string("float") is DataType.F32
    with pytest.raises(ValueError):
        DataType.from_string("quadword")


@pytest.mark.parametrize(
    "text,expected",
    [("100", 100), ("0x64", 100), ("$64", 100), ("0b1100100", 100),
     ("0x00_12_34", 0x1234), ("-5", -5)],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_parse_number_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_number("banana")
    with pytest.raises(ValueError):
        parse_number("")


@pytest.mark.parametrize("text", ["banana", "0xZZ", "0b12"])
def test_parse_number_explains_itself(text):
    """The message reaches the user verbatim in dialogs and status lines.

    int()'s own "invalid literal for int() with base 10" told a person
    nothing about what to type instead.
    """
    with pytest.raises(ValueError) as caught:
        parse_number(text)
    message = str(caught.value)
    assert "invalid literal" not in message
    assert text in message
    assert "hex" in message and "0x" in message


def test_parse_hex_bytes():
    assert parse_hex_bytes("DE AD BE EF") == b"\xde\xad\xbe\xef"
    assert parse_hex_bytes("de:ad-beef") == b"\xde\xad\xbe\xef"
    with pytest.raises(ValueError):
        parse_hex_bytes("ABC")


def test_endian_short_labels():
    assert Endian.BIG.short == "BE"
    assert Endian.LITTLE.short == "LE"


# -- binary-coded decimal -------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [(0x00, 0), (0x08, 8), (0x21, 21), (0x22, 22), (0x36, 36), (0x80, 80), (0x99, 99)],
)
def test_bcd_decode(raw, expected):
    from core.datatypes import bcd_decode

    assert bcd_decode(raw) == expected


@pytest.mark.parametrize("value", [0, 1, 8, 22, 36, 80, 99])
def test_bcd_round_trip(value):
    from core.datatypes import bcd_decode, bcd_encode

    assert bcd_decode(bcd_encode(value)) == value


def test_bcd_rejects_invalid_nibbles():
    from core.datatypes import bcd_decode

    with pytest.raises(ValueError, match="not valid BCD"):
        bcd_decode(0xAB)


def test_bcd_encode_is_bounded_by_size():
    from core.datatypes import bcd_encode

    with pytest.raises(ValueError, match="does not fit"):
        bcd_encode(100, size=1)
    assert bcd_encode(1234, size=2) == 0x1234
