"""IPS and BPS creation and application."""

from __future__ import annotations

import random

import pytest

from core.patch import (
    PatchBuilder,
    PatchFormatError,
    PatchMetadata,
    PatchMismatchError,
    PatchTooLargeError,
    apply_bps,
    apply_ips,
    create_bps,
    create_ips,
    read_bps_info,
)


@pytest.fixture
def source() -> bytes:
    generator = random.Random(1234)
    return bytes(generator.randrange(256) for _ in range(20_000))


@pytest.fixture
def target(source) -> bytes:
    data = bytearray(source)
    data[100:104] = b"\xde\xad\xbe\xef"
    data[5000] = (data[5000] + 1) % 256
    data[9000:9100] = b"\x41" * 100  # a long run, to exercise RLE
    return bytes(data)


@pytest.mark.parametrize("create,apply", [(create_ips, apply_ips), (create_bps, apply_bps)])
def test_round_trip(create, apply, source, target):
    assert apply(source, create(source, target)) == target


@pytest.mark.parametrize("create,apply", [(create_ips, apply_ips), (create_bps, apply_bps)])
def test_round_trip_with_no_changes(create, apply, source):
    assert apply(source, create(source, source)) == source


@pytest.mark.parametrize("create,apply", [(create_ips, apply_ips), (create_bps, apply_bps)])
def test_round_trip_when_the_rom_grows(create, apply, source, target):
    grown = target + b"\x99" * 512
    assert apply(source, create(source, grown)) == grown


@pytest.mark.parametrize("create,apply", [(create_ips, apply_ips), (create_bps, apply_bps)])
def test_round_trip_when_the_rom_shrinks(create, apply, source, target):
    shrunk = target[:15_000]
    assert apply(source, create(source, shrunk)) == shrunk


def test_patch_is_much_smaller_than_the_rom(source, target):
    assert len(create_bps(source, target)) < len(target) // 10
    assert len(create_ips(source, target)) < len(target) // 10


def test_bps_detects_the_wrong_source(source, target):
    patch = create_bps(source, target)
    with pytest.raises(PatchMismatchError, match="not made for the ROM"):
        apply_bps(b"\x00" * len(source), patch)


def test_bps_detects_a_corrupt_patch(source, target):
    patch = bytearray(create_bps(source, target))
    patch[20] ^= 0xFF
    with pytest.raises((PatchFormatError, PatchMismatchError)):
        apply_bps(source, bytes(patch))


def test_bps_carries_metadata(source, target):
    metadata = PatchMetadata(
        name="Speed mod", version="2.1", author="Someone", description="Faster"
    )
    patch = create_bps(source, target, metadata)
    info = read_bps_info(patch)
    assert info.metadata is not None
    assert info.metadata.name == "Speed mod"
    assert info.metadata.author == "Someone"
    assert info.source_size == len(source)
    assert info.target_size == len(target)
    # Metadata must not break application.
    assert apply_bps(source, patch) == target


def test_ips_refuses_addresses_it_cannot_encode():
    big = b"\x00" * (17 << 20)
    with pytest.raises(PatchTooLargeError, match="16 MiB"):
        create_ips(big, b"\x01" * len(big))


def test_format_detection_and_rejection(source, target):
    assert PatchBuilder.detect_format(create_ips(source, target)) == "ips"
    assert PatchBuilder.detect_format(create_bps(source, target)) == "bps"
    with pytest.raises(PatchFormatError, match="Unrecognised"):
        PatchBuilder.detect_format(b"nonsense")


def test_builder_writes_files_and_ips_metadata_sidecar(tmp_path, source, target):
    builder = PatchBuilder(PatchMetadata(name="Sidecar test", author="Tester"))

    bps_path = builder.build_to_file(source, target, tmp_path / "mod.bps")
    assert bps_path.exists()
    assert not (tmp_path / "mod.bps.json").exists()

    ips_path = builder.build_to_file(source, target, tmp_path / "mod.ips")
    sidecar = tmp_path / "mod.ips.json"
    assert ips_path.exists()
    assert sidecar.exists(), "IPS has no metadata block, so it must go beside the patch"
    assert "Sidecar test" in sidecar.read_text()


def test_describe(source, target):
    described = PatchBuilder.describe(create_bps(source, target))
    assert described["format"] == "BPS"
    assert described["source_size"] == len(source)

    described_ips = PatchBuilder.describe(create_ips(source, target))
    assert described_ips["format"] == "IPS"
    assert "cannot verify" in described_ips["note"]


def test_estimate(source, target):
    estimate = PatchBuilder.estimate(source, target)
    assert estimate["regions"] == 3
    assert estimate["changed_bytes"] == 105
    assert estimate["ips_possible"] is True
    assert estimate["size_changed"] is False


def test_apply_truncated_ips_is_reported():
    # A record header that runs off the end of the file.
    with pytest.raises(PatchFormatError, match="truncated IPS record"):
        apply_ips(b"\x00" * 10, b"PATCH\x00\x00\x00\x00\x04")
    # A patch with no EOF marker at all.
    with pytest.raises(PatchFormatError, match="without an EOF marker"):
        apply_ips(b"\x00" * 10, b"PATCH\x00\x00")


def test_demo_rom_patch_round_trip(rom):
    """The realistic case: edit a loaded ROM and patch a fresh copy to match."""
    from core.datatypes import DataType

    rom.write_value(0x8000, 175, DataType.U16)
    patch = create_bps(rom.original, bytes(rom.data))
    assert apply_bps(rom.original, patch) == bytes(rom.data)
