"""Byte order detection and conversion."""

from __future__ import annotations

import pytest

from core.byte_order import ByteOrder, ByteOrderConverter, Z64_MAGIC


@pytest.mark.parametrize("order", list(ByteOrder))
def test_conversion_round_trips(order):
    payload = bytes(range(64))
    converted = ByteOrderConverter.to_big_endian(payload, order)
    assert ByteOrderConverter.from_big_endian(converted, order) == payload


def test_z64_is_identity():
    payload = bytes(range(32))
    assert ByteOrderConverter.to_big_endian(payload, ByteOrder.Z64) == payload


def test_known_swaps():
    payload = bytes([0x00, 0x01, 0x02, 0x03])
    assert bytes(ByteOrderConverter.swap16(payload)) == bytes([0x01, 0x00, 0x03, 0x02])
    assert bytes(ByteOrderConverter.swap32(payload)) == bytes([0x03, 0x02, 0x01, 0x00])
    assert bytes(ByteOrderConverter.swap_words(payload)) == bytes([0x02, 0x03, 0x00, 0x01])


@pytest.mark.parametrize(
    "magic,expected",
    [
        (b"\x80\x37\x12\x40", ByteOrder.Z64),
        (b"\x37\x80\x40\x12", ByteOrder.V64),
        (b"\x40\x12\x37\x80", ByteOrder.N64),
        (b"\x12\x40\x80\x37", ByteOrder.WORDSWAPPED),
    ],
)
def test_detection(magic, expected):
    assert ByteOrderConverter.detect(magic + b"\x00" * 60) is expected


def test_detection_rejects_unknown():
    assert ByteOrderConverter.detect(b"NOPE" + b"\x00" * 60) is None
    assert ByteOrderConverter.detect(b"\x80") is None


def test_odd_length_buffers_do_not_crash():
    # A truncated dump must not raise; the trailing partial word is left as is.
    assert len(ByteOrderConverter.swap16(b"\x01\x02\x03")) == 3
    assert len(ByteOrderConverter.swap32(b"\x01\x02\x03\x04\x05")) == 5


def test_v64_dump_converts_to_the_same_image(demo_rom_bytes):
    swapped = ByteOrderConverter.from_big_endian(demo_rom_bytes, ByteOrder.V64)
    assert bytes(swapped[:4]) == b"\x37\x80\x40\x12"
    assert ByteOrderConverter.detect(bytes(swapped)) is ByteOrder.V64
    assert bytes(ByteOrderConverter.to_big_endian(swapped, ByteOrder.V64)) == demo_rom_bytes
    assert demo_rom_bytes[:4] == Z64_MAGIC
