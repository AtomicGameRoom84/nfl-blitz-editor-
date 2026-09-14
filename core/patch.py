"""Patch creation and application (IPS and BPS).

A patch contains only the *difference* between an original ROM and a
modified one, which is what makes it legal and practical to share a mod:
the recipient supplies their own legally obtained ROM and applies the patch
to it.  No copyrighted data leaves this application through a patch file.

Two formats are supported:

IPS
    Ancient, universally supported, and limited: offsets must fit in 24 bits,
    so it cannot address changes past 16 MiB.  Many N64 ROMs are larger than
    that, so the builder refuses rather than producing a broken patch.
BPS
    The modern "beat" format.  No size limit, and it stores CRC32 checksums
    of the source and target so an application to the wrong ROM is detected
    instead of silently corrupting it.  Prefer this for N64.
"""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Tuple

from tools.comparator import diff_buffers

IPS_MAGIC = b"PATCH"
IPS_EOF = b"EOF"
IPS_MAX_OFFSET = 0xFFFFFF
IPS_MAX_CHUNK = 0xFFFF
#: An IPS record cannot start at the offset that spells "EOF".
IPS_EOF_OFFSET = 0x454F46

BPS_MAGIC = b"BPS1"


class PatchError(Exception):
    """Base class for patch creation and application failures."""


class PatchFormatError(PatchError):
    """The patch file is malformed or not the expected format."""


class PatchMismatchError(PatchError):
    """The patch does not belong to the ROM it is being applied to."""


class PatchTooLargeError(PatchError):
    """The changes cannot be represented in the chosen format."""


@dataclass
class PatchMetadata:
    """Human-facing information about a patch.

    BPS carries this inline in its metadata block.  IPS has nowhere to put
    it, so :meth:`PatchBuilder.build_ips` writes a sidecar ``.json`` file
    alongside the patch instead of dropping the information.
    """

    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    game: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "created": self.created,
            "game": self.game,
            "notes": self.notes,
            "generator": "NFL Blitz Mod Suite",
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, payload: dict) -> "PatchMetadata":
        return cls(
            name=payload.get("name", ""),
            version=payload.get("version", ""),
            description=payload.get("description", ""),
            author=payload.get("author", ""),
            created=payload.get("created", ""),
            game=payload.get("game", ""),
            notes=payload.get("notes", ""),
        )

    def is_empty(self) -> bool:
        return not any(
            (self.name, self.version, self.description, self.author, self.game, self.notes)
        )


# ---------------------------------------------------------------------------
# IPS
# ---------------------------------------------------------------------------


def _ips_records(
    source: bytes, target: bytes, merge_gap: int = 4
) -> Iterator[Tuple[int, bytes]]:
    """Yield ``(offset, data)`` chunks covering every difference.

    Small gaps of identical bytes are absorbed into a record because each
    record costs five bytes of header; splitting on every single byte would
    bloat the patch.
    """
    for start, end in diff_buffers(source, target, merge_gap):
        # When the target is shorter than the source the final "difference"
        # is data that simply no longer exists; the truncate extension
        # handles that, not a record.
        end = min(end, len(target))
        position = start
        while position < end:
            chunk_end = min(position + IPS_MAX_CHUNK, end)
            yield position, bytes(target[position:chunk_end])
            position = chunk_end


def _encode_ips_record(offset: int, data: bytes) -> bytes:
    """Encode one record, using RLE when it is clearly smaller."""
    # RLE pays off only for a long run of one byte: 3 + 2 + 2 + 1 = 8 bytes of
    # overhead versus 5 + len.  Require a healthy margin before using it.
    if len(data) >= 16 and data.count(data[0:1]) == len(data):
        return (
            offset.to_bytes(3, "big")
            + (0).to_bytes(2, "big")
            + len(data).to_bytes(2, "big")
            + data[0:1]
        )
    return offset.to_bytes(3, "big") + len(data).to_bytes(2, "big") + data


def create_ips(source: bytes, target: bytes) -> bytes:
    """Build an IPS patch turning ``source`` into ``target``.

    Raises
    ------
    PatchTooLargeError
        If any change lies at or beyond 16 MiB, or the target exceeds the
        24-bit addressable range.  IPS simply cannot express these.
    """
    if len(target) > IPS_MAX_OFFSET + 1:
        raise PatchTooLargeError(
            f"IPS cannot address beyond 16 MiB, but the modified ROM is "
            f"{len(target) / (1024 * 1024):.1f} MiB. Use BPS instead."
        )

    out = bytearray(IPS_MAGIC)
    for offset, data in _ips_records(source, target):
        if offset + len(data) > IPS_MAX_OFFSET + 1:
            raise PatchTooLargeError(
                f"A change at 0x{offset:X} is outside the 16 MiB range IPS "
                "can address. Use BPS instead."
            )
        # A record may not begin at the offset spelling "EOF"; shifting the
        # record one byte earlier is the conventional workaround.
        if offset == IPS_EOF_OFFSET:
            if offset == 0:  # pragma: no cover - unreachable, kept for clarity
                raise PatchTooLargeError("cannot shift a record at offset 0")
            offset -= 1
            data = bytes(target[offset : offset + 1]) + data
        out += _encode_ips_record(offset, data)

    out += IPS_EOF
    if len(target) < len(source):
        # "Truncate" extension: three big endian bytes giving the new length.
        out += len(target).to_bytes(3, "big")
    return bytes(out)


def apply_ips(source: bytes, patch: bytes) -> bytes:
    """Apply an IPS patch to ``source`` and return the patched image."""
    if not patch.startswith(IPS_MAGIC):
        raise PatchFormatError("not an IPS patch (missing 'PATCH' signature)")

    data = bytearray(source)
    position = len(IPS_MAGIC)
    while True:
        if position + 3 > len(patch):
            raise PatchFormatError("IPS patch ended without an EOF marker")
        marker = patch[position : position + 3]
        if marker == IPS_EOF:
            position += 3
            break
        offset = int.from_bytes(marker, "big")
        position += 3
        if position + 2 > len(patch):
            raise PatchFormatError(f"truncated IPS record at 0x{offset:X}")
        size = int.from_bytes(patch[position : position + 2], "big")
        position += 2

        if size == 0:  # RLE record
            if position + 3 > len(patch):
                raise PatchFormatError(f"truncated IPS RLE record at 0x{offset:X}")
            run_length = int.from_bytes(patch[position : position + 2], "big")
            value = patch[position + 2 : position + 3]
            position += 3
            chunk = value * run_length
        else:
            if position + size > len(patch):
                raise PatchFormatError(f"truncated IPS record at 0x{offset:X}")
            chunk = patch[position : position + size]
            position += size

        if offset + len(chunk) > len(data):
            data.extend(b"\x00" * (offset + len(chunk) - len(data)))
        data[offset : offset + len(chunk)] = chunk

    # Optional truncate extension.
    if len(patch) - position >= 3:
        new_length = int.from_bytes(patch[position : position + 3], "big")
        del data[new_length:]

    return bytes(data)


# ---------------------------------------------------------------------------
# BPS
# ---------------------------------------------------------------------------


def _encode_varint(value: int) -> bytes:
    """BPS variable-width number encoding (low bits first, 0x80 terminates)."""
    out = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(0x80 | chunk)
            break
        out.append(chunk)
        value -= 1
    return bytes(out)


def _decode_varint(data: bytes, position: int) -> Tuple[int, int]:
    """Decode a varint; returns ``(value, new_position)``."""
    value = 0
    shift = 1
    while True:
        if position >= len(data):
            raise PatchFormatError("BPS patch ended inside a number")
        byte = data[position]
        position += 1
        value += (byte & 0x7F) * shift
        if byte & 0x80:
            return value, position
        shift <<= 7
        value += shift


def create_bps(
    source: bytes,
    target: bytes,
    metadata: Optional[PatchMetadata] = None,
) -> bytes:
    """Build a BPS patch turning ``source`` into ``target``.

    The encoder is deliberately "linear": unchanged stretches become
    ``SourceRead`` actions and changed stretches become ``TargetRead``.  It
    does not search for moved blocks, which a general-purpose delta
    compressor would; for ROM edits -- where data stays in place and only
    values change -- the result is already within a few bytes of optimal and
    the encoder stays simple enough to trust.
    """
    metadata_bytes = b""
    if metadata is not None and not metadata.is_empty():
        metadata_bytes = metadata.to_json().encode("utf-8")

    out = bytearray(BPS_MAGIC)
    out += _encode_varint(len(source))
    out += _encode_varint(len(target))
    out += _encode_varint(len(metadata_bytes))
    out += metadata_bytes

    common = min(len(source), len(target))
    position = 0
    for start, end in diff_buffers(source[:common], target[:common], merge_gap=0):
        if start > position:
            # Unchanged run: read it straight out of the source.
            out += _encode_varint(((start - position - 1) << 2) | 0)
        literal = bytes(target[start:end])
        out += _encode_varint(((len(literal) - 1) << 2) | 1)
        out += literal
        position = end
    if position < common:
        out += _encode_varint(((common - position - 1) << 2) | 0)
        position = common
    if len(target) > common:
        tail = bytes(target[common:])
        out += _encode_varint(((len(tail) - 1) << 2) | 1)
        out += tail

    out += (zlib.crc32(bytes(source)) & 0xFFFFFFFF).to_bytes(4, "little")
    out += (zlib.crc32(bytes(target)) & 0xFFFFFFFF).to_bytes(4, "little")
    out += (zlib.crc32(bytes(out)) & 0xFFFFFFFF).to_bytes(4, "little")
    return bytes(out)


@dataclass
class BPSInfo:
    """Header information read out of a BPS patch without applying it."""

    source_size: int
    target_size: int
    source_crc32: int
    target_crc32: int
    metadata: Optional[PatchMetadata]
    raw_metadata: str


def read_bps_info(patch: bytes) -> BPSInfo:
    """Parse a BPS header and footer so a patch can be described before use."""
    if not patch.startswith(BPS_MAGIC) or len(patch) < len(BPS_MAGIC) + 12:
        raise PatchFormatError("not a BPS patch (missing 'BPS1' signature)")
    position = len(BPS_MAGIC)
    source_size, position = _decode_varint(patch, position)
    target_size, position = _decode_varint(patch, position)
    metadata_size, position = _decode_varint(patch, position)
    raw_metadata = patch[position : position + metadata_size].decode(
        "utf-8", errors="replace"
    )
    metadata: Optional[PatchMetadata] = None
    if raw_metadata.strip().startswith("{"):
        try:
            metadata = PatchMetadata.from_dict(json.loads(raw_metadata))
        except json.JSONDecodeError:
            metadata = None
    return BPSInfo(
        source_size=source_size,
        target_size=target_size,
        source_crc32=int.from_bytes(patch[-12:-8], "little"),
        target_crc32=int.from_bytes(patch[-8:-4], "little"),
        metadata=metadata,
        raw_metadata=raw_metadata,
    )


def apply_bps(source: bytes, patch: bytes, verify: bool = True) -> bytes:
    """Apply a BPS patch to ``source``.

    Raises
    ------
    PatchFormatError
        The patch is malformed or its own checksum does not match.
    PatchMismatchError
        ``source`` is not the ROM this patch was built against, or the
        result does not match the expected target checksum.
    """
    if not patch.startswith(BPS_MAGIC) or len(patch) < len(BPS_MAGIC) + 12:
        raise PatchFormatError("not a BPS patch (missing 'BPS1' signature)")

    body, footer = patch[:-12], patch[-12:]
    source_crc = int.from_bytes(footer[0:4], "little")
    target_crc = int.from_bytes(footer[4:8], "little")
    patch_crc = int.from_bytes(footer[8:12], "little")

    if verify and (zlib.crc32(patch[:-4]) & 0xFFFFFFFF) != patch_crc:
        raise PatchFormatError("BPS patch is corrupt (patch checksum mismatch)")
    if verify and (zlib.crc32(bytes(source)) & 0xFFFFFFFF) != source_crc:
        raise PatchMismatchError(
            "This patch was not made for the ROM you loaded "
            f"(expected CRC32 {source_crc:08X}, got "
            f"{zlib.crc32(bytes(source)) & 0xFFFFFFFF:08X})."
        )

    position = len(BPS_MAGIC)
    source_size, position = _decode_varint(body, position)
    target_size, position = _decode_varint(body, position)
    metadata_size, position = _decode_varint(body, position)
    position += metadata_size

    if verify and source_size != len(source):
        raise PatchMismatchError(
            f"This patch expects a {source_size} byte ROM; the loaded ROM is "
            f"{len(source)} bytes."
        )

    output = bytearray(target_size)
    output_offset = 0
    source_relative = 0
    target_relative = 0

    while position < len(body):
        value, position = _decode_varint(body, position)
        action = value & 3
        length = (value >> 2) + 1

        if output_offset + length > target_size:
            raise PatchFormatError("BPS action writes past the end of the target")

        if action == 0:  # SourceRead
            if output_offset + length > len(source):
                raise PatchFormatError("BPS SourceRead reads past the end of the source")
            output[output_offset : output_offset + length] = source[
                output_offset : output_offset + length
            ]
            output_offset += length
        elif action == 1:  # TargetRead
            if position + length > len(body):
                raise PatchFormatError("BPS TargetRead reads past the end of the patch")
            output[output_offset : output_offset + length] = body[
                position : position + length
            ]
            position += length
            output_offset += length
        elif action == 2:  # SourceCopy
            raw, position = _decode_varint(body, position)
            source_relative += (-1 if raw & 1 else 1) * (raw >> 1)
            if source_relative < 0 or source_relative + length > len(source):
                raise PatchFormatError("BPS SourceCopy is out of range")
            output[output_offset : output_offset + length] = source[
                source_relative : source_relative + length
            ]
            source_relative += length
            output_offset += length
        else:  # TargetCopy -- may overlap itself, so copy byte by byte.
            raw, position = _decode_varint(body, position)
            target_relative += (-1 if raw & 1 else 1) * (raw >> 1)
            if target_relative < 0:
                raise PatchFormatError("BPS TargetCopy is out of range")
            for _ in range(length):
                output[output_offset] = output[target_relative]
                target_relative += 1
                output_offset += 1

    result = bytes(output)
    if verify and (zlib.crc32(result) & 0xFFFFFFFF) != target_crc:
        raise PatchMismatchError(
            "Patched result does not match the checksum stored in the patch."
        )
    return result


# ---------------------------------------------------------------------------
# Front end
# ---------------------------------------------------------------------------


class PatchBuilder:
    """Builds and applies patches, with format detection and reporting."""

    def __init__(self, metadata: Optional[PatchMetadata] = None) -> None:
        self.metadata = metadata or PatchMetadata()

    # -- creation ----------------------------------------------------------

    def build(self, source: bytes, target: bytes, fmt: str) -> bytes:
        fmt = fmt.lower().lstrip(".")
        if fmt == "ips":
            return create_ips(source, target)
        if fmt == "bps":
            return create_bps(source, target, self.metadata)
        raise PatchError(f"unsupported patch format: {fmt!r}")

    def build_to_file(
        self,
        source: bytes,
        target: bytes,
        path: str | Path,
        fmt: Optional[str] = None,
    ) -> Path:
        """Write a patch to ``path``; format defaults to the file extension."""
        path = Path(path)
        fmt = fmt or path.suffix.lstrip(".") or "bps"
        payload = self.build(source, target, fmt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if fmt.lower() == "ips" and not self.metadata.is_empty():
            # IPS has no metadata block; keep the information beside it.
            path.with_suffix(path.suffix + ".json").write_text(
                self.metadata.to_json(), encoding="utf-8"
            )
        return path

    # -- application -------------------------------------------------------

    @staticmethod
    def detect_format(patch: bytes) -> str:
        if patch.startswith(BPS_MAGIC):
            return "bps"
        if patch.startswith(IPS_MAGIC):
            return "ips"
        raise PatchFormatError(
            "Unrecognised patch file. Expected an IPS ('PATCH') or BPS "
            "('BPS1') header."
        )

    @classmethod
    def apply(cls, source: bytes, patch: bytes, verify: bool = True) -> bytes:
        fmt = cls.detect_format(patch)
        if fmt == "bps":
            return apply_bps(source, patch, verify=verify)
        return apply_ips(source, patch)

    @classmethod
    def describe(cls, patch: bytes) -> dict:
        """Summarise a patch file for the confirmation dialog."""
        fmt = cls.detect_format(patch)
        info: dict = {"format": fmt.upper(), "size": len(patch)}
        if fmt == "bps":
            bps = read_bps_info(patch)
            info.update(
                {
                    "source_size": bps.source_size,
                    "target_size": bps.target_size,
                    "source_crc32": f"0x{bps.source_crc32:08X}",
                    "target_crc32": f"0x{bps.target_crc32:08X}",
                    "metadata": bps.metadata.to_dict() if bps.metadata else None,
                }
            )
        else:
            info["note"] = (
                "IPS patches carry no checksum, so the suite cannot verify "
                "that this patch matches the loaded ROM."
            )
        return info

    # -- estimation --------------------------------------------------------

    @staticmethod
    def estimate(source: bytes, target: bytes) -> dict:
        """Report what a patch would contain, before building one."""
        regions = diff_buffers(source, target, merge_gap=16)
        changed = sum(end - start for start, end in regions)
        highest = max((end for _, end in regions), default=0)
        return {
            "regions": len(regions),
            "changed_bytes": changed,
            "highest_offset": highest,
            "ips_possible": highest <= IPS_MAX_OFFSET + 1 and len(target) <= IPS_MAX_OFFSET + 1,
            "size_changed": len(source) != len(target),
        }
