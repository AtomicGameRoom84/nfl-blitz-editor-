"""GameShark code parsing, conversion and application."""

from __future__ import annotations

import pytest

from core.address_db import GameDefinition, RamRange
from tools.gameshark import (
    KSEG0_BASE,
    GameSharkError,
    MappedRange,
    RamMap,
    apply_to_rom,
    codes_to_text,
    convert,
    float_high_half,
    make_code,
    parse_line,
    parse_list,
)


# -- parsing --------------------------------------------------------------


def test_parses_a_constant_write():
    code = parse_line("802997E3 0003")
    assert code.type_byte == 0x80
    assert code.normalised_address == 0x802997E3
    assert code.value == 3
    assert code.width == 1
    assert code.payload == b"\x03"
    assert code.writes_memory


def test_parses_a_16_bit_write():
    code = parse_line("812ADD6C 42C8")
    assert code.width == 2
    assert code.payload == b"\x42\xc8"
    assert code.normalised_address == 0x802ADD6C


def test_uncached_addresses_normalise_to_kseg0():
    code = parse_line("A02997E3 0001")
    assert code.address == 0xA02997E3
    assert code.normalised_address == 0x802997E3


def test_accepts_comments_and_tight_formatting():
    assert parse_line("802997E3 0003 ; Fast Passes").comment == "Fast Passes"
    assert parse_line("802997E30003").value == 3
    assert parse_line("") is None
    assert parse_line("# a heading") is None
    assert parse_line("[NFL Blitz]") is None


def test_rejects_nonsense():
    with pytest.raises(GameSharkError):
        parse_line("hello world")


def test_parse_list_keeps_going_after_a_bad_line():
    codes, problems = parse_list(
        "802997E3 0003\nnot a code\n812ADD6C 42C8\n"
    )
    assert len(codes) == 2
    assert len(problems) == 1
    assert "line 2" in problems[0]


def test_conditional_and_directive_codes_are_recognised_but_do_not_write():
    for text in ("D004FD24 0020", "D104FD24 1234", "5000FF01 0000", "EE000000 0000"):
        code = parse_line(text)
        assert code.supported, text
        assert not code.writes_memory, text


def test_unknown_type_is_reported_not_guessed():
    code = parse_line("77123456 0001")
    assert not code.supported
    assert "unsupported" in code.describe()


# -- generation -----------------------------------------------------------


def test_make_code_round_trips():
    code = make_code(0x802997E3, 3)
    assert code.format() == "802997E3 0003"
    assert parse_line(code.format()).normalised_address == 0x802997E3


def test_make_code_widths_and_button_variants():
    assert make_code(0x80299700, 1, 1).type_byte == 0x80
    assert make_code(0x80299700, 1, 2).type_byte == 0x81
    assert make_code(0x80299700, 1, 1, gs_button=True).type_byte == 0x88
    assert make_code(0x80299700, 1, 2, gs_button=True).type_byte == 0x89
    with pytest.raises(ValueError):
        make_code(0x80299700, 1, width=4)


def test_float_high_half_matches_the_published_turbo_code():
    # The community "Infinite Turbo" code writes 42C8, the top half of 100.0.
    assert float_high_half(100.0) == 0x42C8


def test_codes_to_text():
    codes = [make_code(0x80299700, 1), make_code(0x80299704, 2)]
    assert codes_to_text(codes) == "80299700 0001\n80299704 0002"


# -- mapping --------------------------------------------------------------


@pytest.fixture
def ram_map() -> RamMap:
    return RamMap([MappedRange(0x802DE3D8, 0x802E9058, 0x0009D070, "roster region")])


def test_mapping_converts_inside_the_range(ram_map):
    assert ram_map.to_rom(0x802DE3D8) == 0x0009D070
    assert ram_map.to_rom(0x802E8A98) == 0x000A7730


def test_mapping_refuses_outside_the_range(ram_map):
    assert ram_map.to_rom(0x802997E3) is None
    assert ram_map.to_rom(0x80000000) is None


def test_mapping_is_built_from_the_definition():
    definition = GameDefinition(
        id="x", game="X",
        ram_map=[RamRange(0x80200000, 0x80210000, 0x1000, note="test")],
    )
    mapping = RamMap.from_definition(definition)
    assert mapping.to_rom(0x80200010) == 0x1010
    assert mapping.to_rom(0x80300000) is None


# -- conversion -----------------------------------------------------------


def test_conversion_reports_why_a_code_cannot_be_applied(ram_map, rom):
    codes, _ = parse_list(
        "802997E3 0003\n"      # outside the mapped range
        "D004FD24 0020\n"      # not a write
        "77123456 0001\n"      # unsupported type
    )
    results = convert(codes, ram_map, rom)
    reasons = [r.reason for r in results]
    assert "not in a verified" in reasons[0]
    assert "does not write" in reasons[1]
    assert "unsupported" in reasons[2]
    assert not any(r.convertible for r in results)


def test_conversion_maps_and_applies_inside_the_range(rom):
    # Map a window of the demo ROM so the conversion has somewhere to land.
    mapping = RamMap([MappedRange(0x80200000, 0x80210000, 0x2000)])
    before = rom.read_bytes(0x2010, 1)
    codes, _ = parse_list("80200010 00AB")
    results = convert(codes, mapping, rom)

    assert results[0].convertible
    assert results[0].rom_offset == 0x2010
    assert results[0].current_bytes == before
    assert results[0].changes_anything

    assert apply_to_rom(rom, results) == 1
    assert rom.read_bytes(0x2010, 1) == b"\xab"

    # One undo step, and it reverses cleanly.
    assert len(rom.undo.history) == 1
    rom.undo_last()
    assert rom.read_bytes(0x2010, 1) == before


def test_applying_a_code_that_changes_nothing_is_a_no_op(rom):
    mapping = RamMap([MappedRange(0x80200000, 0x80210000, 0x2000)])
    current = rom.read_bytes(0x2010, 1)[0]
    codes, _ = parse_list(f"80200010 {current:04X}")
    results = convert(codes, mapping, rom)
    assert results[0].convertible
    assert not results[0].changes_anything
    assert apply_to_rom(rom, results) == 0
    assert not rom.undo.can_undo


def test_conversion_refuses_to_write_past_the_end_of_the_rom(rom):
    mapping = RamMap([MappedRange(0x80200000, 0x80210000, rom.size - 1)])
    codes, _ = parse_list("80200004 0001")
    results = convert(codes, mapping, rom)
    assert not results[0].convertible
    assert "past the end" in results[0].reason


# -- the shipped NFL Blitz catalogue --------------------------------------


def test_blitz_catalogue_generates_usable_codes(builtin_games_dir):
    from core.address_db import AddressDatabase

    definition = AddressDatabase(builtin_dir=builtin_games_dir).load_all().get(
        "nfl_blitz_1997"
    )
    passing = {c.id: c for c in definition.ram_codes_in("passing")}
    assert "fast_passes" in passing

    code = make_code(passing["fast_passes"].address, 3)
    assert code.format() == "802997E3 0003"

    # And it is honestly reported as *not* convertible to a ROM edit.
    mapping = RamMap.from_definition(definition)
    assert mapping.to_rom(passing["fast_passes"].address) is None


def test_blitz_turbo_code_uses_the_float_high_half(builtin_games_dir):
    """The turbo meter is a float; codes set only its upper halfword."""
    from core.address_db import AddressDatabase

    definition = AddressDatabase(builtin_dir=builtin_games_dir).load_all().get(
        "nfl_blitz_1997"
    )
    turbo = definition.ram_code("turbo_away_team")
    assert turbo.float_high_half
    assert turbo.width == 2
    assert turbo.address == 0x802ADD6C
    assert make_code(turbo.address, float_high_half(100.0), 2).format() == "812ADD6C 42C8"


def test_blitz_catalogue_comes_from_the_device_database(builtin_games_dir):
    """Provenance must point at the GameShark firmware, not a fan site."""
    from core.address_db import AddressDatabase

    definition = AddressDatabase(builtin_dir=builtin_games_dir).load_all().get(
        "nfl_blitz_1997"
    )
    assert definition.ram_codes
    for code in definition.ram_codes:
        assert "GameShark Pro" in code.source


def test_ambiguous_names_are_kept_distinct(builtin_games_dir):
    """Two addresses shipped under one name must not silently collapse."""
    from core.address_db import AddressDatabase

    definition = AddressDatabase(builtin_dir=builtin_games_dir).load_all().get(
        "nfl_blitz_1997"
    )
    big_heads = [c for c in definition.ram_codes if c.id.startswith("big_head")]
    assert len(big_heads) == 2
    assert len({c.address for c in big_heads}) == 2
    for code in big_heads:
        assert "not settled" in code.notes


# -- the GameShark firmware database --------------------------------------


def _fake_firmware() -> bytes:
    """A minimal database in the device's record format."""
    body = bytearray()
    body += b"Test Game\x00"
    body += bytes([2])                     # declared entry count
    body += b"Infinite Health\x00" + bytes([0x01])
    body += bytes([0x80]) + (0x123456).to_bytes(3, "big") + (0x0063).to_bytes(2, "big")
    body += b"\xff"
    body += b"Max Score\x00" + bytes([0x02])
    body += bytes([0x81]) + (0x2ADF4F).to_bytes(3, "big") + (0x0032).to_bytes(2, "big")
    body += bytes([0x80]) + (0x2ADF57).to_bytes(3, "big") + (0x0032).to_bytes(2, "big")
    return b"\x00" * 16 + bytes(body) + b"\x00" * 16


def test_firmware_database_parses_a_game():
    from tools.gameshark_db import find_game

    game = find_game(_fake_firmware(), "Test Game")
    assert game is not None
    assert game.declared_count == 2
    assert [e.name for e in game.entries] == ["Infinite Health", "Max Score"]
    assert game.entries[0].codes[0].format() == "80123456 0063"
    assert len(game.entries[1].codes) == 2


def test_firmware_database_lists_games():
    from tools.gameshark_db import list_games

    games = list_games(_fake_firmware(), minimum_entries=2)
    assert [g.name for g in games] == ["Test Game"]


def test_firmware_parse_stops_at_an_illegal_code_type():
    """A misaligned parse must yield nothing, not nonsense."""
    from tools.gameshark_db import parse_entries

    data = b"Bad Entry\x00" + bytes([0x01]) + bytes([0x77]) + b"\x00" * 5
    entries, _ = parse_entries(data, 0)
    assert entries == []


def test_firmware_codes_flatten():
    from tools.gameshark_db import codes_for, find_game

    game = find_game(_fake_firmware(), "Test Game")
    assert len(codes_for(game)) == 3
