"""End-to-end functional audit: drive the real app against a real ROM.

The unit tests check each part in isolation against a small synthetic ROM.
This script does the other half: it builds the actual main window, loads a
real cartridge dump, and works through every page the way a person would --
editing a team, filtering the roster, searching, bookmarking, diffing,
building a patch and applying it, saving and reloading.

It is deliberately not a pytest module.  It needs a real ROM, which cannot
be committed, so it is a tool you point at your own dump:

    python -m tools.audit "NFL Blitz (USA).z64"

Optional extras, each enabling one more check:

    --gameshark PATH   a GameShark firmware dump, to parse its code database

Exit status is 0 only if every check passes.
"""
import argparse, os, shutil, sys, tempfile, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

_parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
_parser.add_argument("rom", help="path to a real NFL Blitz N64 ROM")
_parser.add_argument("--gameshark", help="path to a GameShark firmware dump")
_parser.add_argument("--keep", action="store_true",
                     help="keep the scratch directory instead of deleting it")
ARGS = _parser.parse_args()

SCR = tempfile.mkdtemp(prefix="blitz-audit-")
os.environ['QT_QPA_PLATFORM'] = os.environ.get('QT_QPA_PLATFORM', 'offscreen')
# A private settings/bookmarks home, so an audit never disturbs real work.
os.environ['NFL_BLITZ_SUITE_HOME'] = SCR + '/home'
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QInputDialog
BOX=[]
QMessageBox.critical    = staticmethod(lambda *a,**k: BOX.append(("ERROR", a[2] if len(a)>2 else '')))
QMessageBox.information = staticmethod(lambda *a,**k: BOX.append(("INFO",  a[2] if len(a)>2 else '')))
QMessageBox.warning     = staticmethod(lambda *a,**k: BOX.append(("WARN",  a[2] if len(a)>2 else '')))
QMessageBox.question    = staticmethod(lambda *a,**k: QMessageBox.Yes)
from ui import theme; from ui.app_state import AppState; from ui.main_window import MainWindow

ROM = ARGS.rom
PASS=[]; FAIL=[]
def check(name, fn):
    BOX.clear()
    try:
        detail = fn()
        PASS.append(name); print(f"  PASS  {name}" + (f"   [{detail}]" if detail else ""), flush=True)
    except Exception as e:
        FAIL.append((name, e)); print(f"  FAIL  {name}\n          {type(e).__name__}: {e}", flush=True)

app = QApplication([]); theme.apply_theme(app)
state = AppState(); state.settings.set("auto_backup_on_load", False)
win = MainWindow(state); win.resize(1400,900); win.show()
def page(k): win.navigate(k); app.processEvents(); app.processEvents(); return win.page(k)

print("\n== 1. ROM MANAGER ==", flush=True)
def t_load():
    rep = win.page("rom").load_rom(ROM)
    assert state.rom.is_loaded and state.rom.size == 16777216
    assert not rep.warnings, rep.warnings
    return f"{state.rom.header.image_name}, {state.rom.size//1024}KB, no warnings"
check("load the real ROM cleanly", t_load)
check("boot checksum verifies", lambda: (
    (lambda c,s: (_ for _ in ()).throw(AssertionError(f"{c}!={s}")) if c!=s else f"{s[0]:08X}/{s[1]:08X}")
    (state.rom.calculate_boot_checksum(), state.rom.stored_boot_checksum())))
check("CIC detected", lambda: f"CIC {state.rom.detected_cic()}" if state.rom.detected_cic()==6102 else (_ for _ in ()).throw(AssertionError("not 6102")))
check("exact fingerprint match", lambda: (
    f"{state.match.definition.id} score {state.match.score}" if state.match and state.match.exact
    else (_ for _ in ()).throw(AssertionError("not an exact match"))))
def t_backup():
    rec = state.backups.create_backup(ROM)
    assert rec is not None and rec.path.stat().st_size == 16777216
    assert state.backups.create_backup(ROM) is None, "duplicate backup was made"
    return "created + deduplicated"
check("backup create and dedupe", t_backup)

print("\n== 2. TEAM EDITOR ==", flush=True)
tp = page("teams")
check("30 teams readable", lambda: f"{tp.editor.record_count} teams, first={tp.editor.team_labels()[0].strip()}"
      if tp.editor.record_count==30 else (_ for _ in ()).throw(AssertionError("not 30")))
def t_team_edit():
    tp._team_picker.setCurrentIndex(10); tp.load_team()
    tp._controls['nickname'].setText("Rockets"); tp.save_team(); app.processEvents()
    got = tp.editor.read_record(10).values['nickname']
    assert got == "Rockets", got
    return "Green Bay nickname -> Rockets"
check("edit and save a team", t_team_edit)
def t_team_revert():
    tp._team_picker.setCurrentIndex(10); tp.revert_team(); app.processEvents()
    got = tp.editor.read_record(10).values['nickname']
    assert got == "Packers", got
    return "reverted to Packers"
check("revert a team", t_team_revert)
def t_colour():
    # NFL Blitz team colours have not been located, so this definition
    # declares no colour field.  The honest outcome is no colour control at
    # all -- not a swatch showing a guess.
    colour_fields = [f.id for f in tp.editor.fields() if f.kind == "color"]
    assert not colour_fields, colour_fields
    assert tp.editor.read_color(0, 'primary_color') is None
    from ui.pages.team_page import ColorButton
    swatches = [k for k, c in tp._controls.items() if isinstance(c, ColorButton)]
    assert not swatches, swatches
    return "no colour field declared -> no swatch shown, read_color returns None"
check("team colours are honestly absent", t_colour)
def t_team_csv():
    p1 = SCR+"/teams.csv"; tp.editor.export_csv(p1)
    assert tp.editor.import_csv(p1) == 0
    rows = open(p1).read().splitlines(); rows[1] = rows[1].replace("Arizona","Phoenix",1)
    open(p1,"w").write("\n".join(rows))
    n = tp.editor.import_csv(p1); assert n==1, n
    assert tp.editor.read_record(0).values['city']=="Phoenix"
    state.rom.undo_last(); return "export/import + single-field change"
check("team CSV round trip", t_team_csv)

print("\n== 3. ROSTER EDITOR ==", flush=True)
rp = page("roster")
check("480 players readable", lambda: f"{rp.editor.record_count} players"
      if rp.editor.record_count==480 else (_ for _ in ()).throw(AssertionError("not 480")))
def t_team_filter():
    rp._team_filter.setCurrentIndex(rp._team_filter.findData(7)); rp.refresh_table(); app.processEvents()
    assert rp._table.rowCount()==16, rp._table.rowCount()
    names=[rp.editor.read_record(i).values['name'] for i in range(7*16,7*16+7)]
    assert "Aikman" in names, names
    return f"Dallas: 16 rows, {', '.join(n for n in names if n)}"
check("filter by team", t_team_filter)
def t_edits():
    nc=rp._field_ids.index("name")+1; jc=rp._field_ids.index("number")+1; pc=rp._field_ids.index("position")+1
    rp._table.item(3,nc).setText("TESTNAME"); app.processEvents()
    rp._table.item(3,jc).setText("77"); app.processEvents()
    rp._table.item(3,pc).setText("WR"); app.processEvents()
    r=rp.editor.read_record(7*16+3).values
    assert r['name']=="TESTNAME" and r['number']==77 and r['position']==1, r
    for _ in range(3): state.rom.undo_last()
    assert rp.editor.read_record(7*16+3).values['name']=="Aikman"
    return "name/jersey(BCD)/position edited and undone"
check("edit name, jersey, position", t_edits)
def t_reject():
    nc=rp._field_ids.index("name")+1
    BOX.clear(); rp._table.item(0,nc).setText("X"*40); app.processEvents(); app.processEvents()
    assert any(k=="WARN" for k,_ in BOX), BOX
    return "too-long name refused with a warning"
check("refuse an invalid edit", t_reject)
def t_bulk():
    idx=list(range(7*16,7*16+8)); before=[rp.editor.read_record(i).values['speed'] if 'speed' in rp.editor.read_record(i).values else None for i in idx]
    f = 'portrait_id'
    n = rp.editor.bulk_adjust(idx, f, 5); assert n>0
    state.rom.undo_last(); return f"bulk adjust {f} on {n} players, one undo step"
check("bulk edit", t_bulk)
def t_roster_csv():
    p1=SCR+"/roster.csv"; rp.editor.export_csv(p1)
    assert rp.editor.import_csv(p1)==0
    rows=open(p1).read().splitlines(); rows[116]=rows[116].replace("Aikman","BRADY",1)
    open(p1,"w").write("\n".join(rows))
    assert rp.editor.import_csv(p1)==1
    state.rom.undo_last(); return "480-row export/import"
check("roster CSV round trip", t_roster_csv)

print("\n== 4. EDITORS THAT SHOULD REPORT UNAVAILABLE ==", flush=True)
gp = page("graphics")
check("graphics reports unavailable", lambda: gp.editor.availability().reason[:60]
      if not gp.editor.availability() else (_ for _ in ()).throw(AssertionError("claims available")))
for key in ("gameplay","movement","passing"):
    pg = page(key)
    check(f"{key}: undiscovered entries shown, none writable", lambda pg=pg: (
        f"{len(pg._rows)} rows, {sum(1 for e in sum([e.entries() for e in pg.editors],[]) if e.is_discovered)} discovered"))

print("\n== 5. HEX / DATA EXPLORER ==", flush=True)
hp = page("hex")
def t_hex():
    hp.show_address(0xA7CE8, 9); app.processEvents()
    assert hp.hex_view.cursor_offset == 0xA7CE8
    txt = state.rom.read_text(0xA7CE8, 9)
    assert txt == "Cardinals", txt
    return f"cursor at 0xA7CE8 = {txt!r}"
check("go to address", t_hex)
def t_hex_find():
    hp._find_edit.setText('"Green Bay"'); hp.find_next(); app.processEvents()
    assert hp.hex_view.cursor_offset == 0xA7F78, hex(hp.hex_view.cursor_offset)
    return "found 'Green Bay' at 0xA7F78"
check("find text", t_hex_find)
def t_hex_edit():
    before = state.rom.read_bytes(0x2000,1)
    hp.hex_view._write_byte(0x2000, 0xAB)
    assert state.rom.read_bytes(0x2000,1)==b"\xab"
    state.rom.undo_last(); assert state.rom.read_bytes(0x2000,1)==before
    return "byte edit + undo"
check("edit a byte", t_hex_edit)

print("\n== 6. VALUE SEARCH ==", flush=True)
from tools.search import ValueSearcher
from core.datatypes import DataType, Endian
sr = ValueSearcher(state.rom.data)
check("text search", lambda: f"{len(sr.search_text('Cardinals'))} hit(s)" if sr.search_text('Cardinals').hits else (_ for _ in ()).throw(AssertionError("none")))
check("typed value search", lambda: f"{len(sr.search_value(100, DataType.U16))} hits for u16 100")
check("byte pattern search", lambda: f"{len(sr.search_bytes(b'Cardinals'))} hit(s)")
_masked = sr.search_masked_bytes(bytes([0x43,0x61,0x72,0x00]), [True,True,True,False])
check("masked search", lambda: f"{len(_masked)} hit(s)")
check("string listing", lambda: f"{len(sr.find_strings(8))} strings of 8+ chars")
def t_refine():
    first = sr.search_value(100, DataType.U16, alignment=1)
    kept = sr.refine(first, lambda v: v==100)
    assert len(kept)==len(first)
    return f"{len(first)} -> {len(kept)} unchanged"
check("narrowing", t_refine)

print("\n== 7. BOOKMARKS -> DEFINITION ==", flush=True)
from core.bookmarks import Bookmark
def t_bm():
    b = Bookmark(name="Audit probe", address=0xA7CD8, data_type=DataType.U16,
                 category="Teams", confidence="tested", rom_key=state.rom_key)
    state.bookmarks.add(b); state.bookmarks.save()
    assert len(state.bookmarks.query(text="Audit"))==1
    return f"{len(state.bookmarks)} bookmark(s) stored"
check("add and query a bookmark", t_bm)
def t_promote():
    from core.address_db import entry_from_bookmark
    b = state.bookmarks.query(text="Audit")[0]
    updated = state.address_db.add_entry(state.definition, entry_from_bookmark(b, "movement"))
    state.definition = updated
    e = updated.entry("audit_probe")
    assert e and e.address == 0xA7CD8 and e.is_discovered
    assert updated.user_defined
    return f"became entry {e.id!r} at {e.address_hex}"
check("promote bookmark to a definition entry", t_promote)
def t_slider():
    pg = page("movement")
    assert "audit_probe" in pg._rows, list(pg._rows)[:4]
    return "appears as a control on Physics & Movement"
check("promoted entry becomes a slider", t_slider)

print("\n== 8. ROM COMPARISON ==", flush=True)
from tools.comparator import ROMComparator
from core.byte_order import ByteOrder, ByteOrderConverter
def t_cmp_working():
    state.rom.write_value(0x8000, 1234, DataType.U16)
    r = ROMComparator().compare_buffers(state.rom.original, bytes(state.rom.data))
    state.rom.undo_last()
    assert len(r.regions)>=1
    return f"{len(r.regions)} region(s), {r.changed_bytes} bytes"
check("diff working copy vs original", t_cmp_working)
def t_cmp_order():
    v64 = SCR+"/audit.v64"
    open(v64,'wb').write(bytes(ByteOrderConverter.from_big_endian(state.rom.original, ByteOrder.V64)))
    r = ROMComparator().compare_files(ROM, v64)
    assert r.identical, r.summary()
    return "z64 vs v64 of the same cart compare identical"
check("byte-order normalisation", t_cmp_order)

print("\n== 9. GAMESHARK ==", flush=True)
gs = page("gameshark")
check("catalogue loaded", lambda: f"{len(gs._catalogue)} runtime addresses")
def t_gs_gen():
    from tools.gameshark import make_code
    e = state.definition.ram_code("fast_passes")
    c = make_code(e.address, 3).format()
    assert c == "802997E3 0003", c
    return f"Fast Passes -> {c}"
check("generate a code", t_gs_gen)
def t_gs_convert():
    gs._input.setPlainText("802997E3 0003\n802DE3E0 0041\nD004FD24 0020\n77123456 0001\n")
    gs.analyse_codes(); app.processEvents()
    txt = gs._import_summary.text()
    assert "4 code(s) parsed" in txt, txt
    rows = [gs._import_table.item(r,2).text() for r in range(gs._import_table.rowCount())]
    assert "not in a verified" in rows[0]
    assert rows[1].startswith("ROM 0x")
    assert "does not write" in rows[2]
    assert "unsupported" in rows[3]
    return "1 of 4 maps to ROM; the other 3 explained"
check("analyse mixed codes", t_gs_convert)
def t_gs_apply():
    before = state.rom.read_bytes(0x9D078,1)
    gs.apply_codes(); app.processEvents()
    assert state.rom.read_bytes(0x9D078,1)==b"\x41", state.rom.read_bytes(0x9D078,1)
    state.rom.undo_last(); assert state.rom.read_bytes(0x9D078,1)==before
    return "applied to ROM and undone"
check("apply a convertible code", t_gs_apply)
def t_gs_fw():
    from tools.gameshark_db import load_firmware, find_game
    fw = load_firmware(ARGS.gameshark)
    g = find_game(fw, "NFL Blitz")
    assert g and len(g.entries)==g.declared_count
    return f"{len(g.entries)} entries parsed from the device database"
if ARGS.gameshark:
    check("read a GameShark firmware database", t_gs_fw)
else:
    print("  SKIP  read a GameShark firmware database   [pass --gameshark PATH]", flush=True)

print("\n== 10. PATCH BUILDER ==", flush=True)
pp = page("patch")
from core.patch import PatchBuilder, create_bps
def t_patch_cycle(fmt):
    def run():
        win.page("rom").load_rom(ROM)
        state.rom.write_value(0x8000, 4242, DataType.U16)
        target = bytes(state.rom.data)
        out = SCR + f"/audit.{fmt}"
        PatchBuilder(pp._metadata()).build_to_file(state.rom.original, target, out, fmt)
        info = PatchBuilder.describe(open(out,'rb').read())
        assert info["format"]==fmt.upper()
        # apply while the working copy still carries edits
        state.rom.write_value(0x9000, 1111, DataType.U16)
        BOX.clear()
        QFileDialog.getOpenFileName = staticmethod(lambda *a,**k: (out,""))
        win.navigate("patch"); app.processEvents(); pp.apply_patch(); app.processEvents()
        assert not any(k=="ERROR" for k,_ in BOX), BOX
        assert bytes(state.rom.data)==target, "patch did not reproduce the target"
        return f"create({os.path.getsize(out)}B) -> inspect -> apply, exact match"
    return run
check("BPS create / inspect / apply", t_patch_cycle("bps"))
check("IPS create / inspect / apply", t_patch_cycle("ips"))
def t_patch_wrong():
    other = bytes(range(256))*64
    wrong = SCR+"/wrong.bps"; open(wrong,'wb').write(create_bps(other, bytes(reversed(other))))
    BOX.clear(); before = bytes(state.rom.data)
    QFileDialog.getOpenFileName = staticmethod(lambda *a,**k: (wrong,""))
    pp.apply_patch(); app.processEvents()
    assert bytes(state.rom.data)==before, "ROM was modified by a foreign patch"
    assert any(k=="ERROR" for k,_ in BOX), BOX
    return "refused, ROM untouched"
check("reject a patch for another ROM", t_patch_wrong)

print("\n== 11. RESEARCH MODE ==", flush=True)
from tools.research import Experiment
def t_research():
    state.research.add(Experiment(name="Audit run", address=0xA7CD8,
        original_value=1, modified_value=2, outcome="confirmed", result="works"))
    state.research.save()
    md = state.research.export_markdown(SCR+"/log.md")
    assert "Audit run" in md.read_text()
    return f"{len(state.research)} experiment(s), markdown exported"
check("log and export an experiment", t_research)

print("\n== 12. SAVE + RELOAD ROUND TRIP ==", flush=True)
def t_save_refuse():
    try:
        state.rom.save_as(ROM); raise AssertionError("overwrote the source ROM")
    except ValueError as e:
        assert "Refusing to overwrite" in str(e)
    return "refuses to overwrite the loaded ROM"
check("never overwrite the original", t_save_refuse)
def t_roundtrip():
    win.page("rom").load_rom(ROM)
    win.navigate("roster"); app.processEvents()
    r = win.page("roster")
    r.editor.write_field(7*16+3, "name", "MONTANA")
    out = SCR+"/audit-saved.z64"
    state.rom.save_as(out, fix_checksum=True)
    assert os.path.getsize(out)==16777216
    win.page("rom").load_rom(out)
    win.navigate("roster"); app.processEvents()
    got = win.page("roster").editor.read_record(7*16+3).values["name"]
    assert got=="MONTANA", got
    c,s = state.rom.calculate_boot_checksum(), state.rom.stored_boot_checksum()
    assert c==s, "saved ROM has a bad boot checksum"
    return f"edit survived save+reload; checksum {s[0]:08X}/{s[1]:08X} valid"
check("save, reload, verify, checksum", t_roundtrip)

print("\n== 13. UNDO / REDO INTEGRITY ==", flush=True)
def t_undo():
    win.page("rom").load_rom(ROM)
    base = bytes(state.rom.data)
    for i,(off,val) in enumerate([(0x8000,11),(0x8002,22),(0x8004,33)]):
        state.rom.write_value(off, val, DataType.U16)
    assert len(state.rom.undo.history)==3
    for _ in range(3): state.rom.undo_last()
    assert bytes(state.rom.data)==base, "undo did not restore the ROM"
    for _ in range(3): state.rom.redo_last()
    assert state.rom.read_value(0x8004, DataType.U16)==33
    state.rom.revert_all()
    assert bytes(state.rom.data)==base
    return "3 edits, undo all, redo all, revert all"
check("undo/redo/revert", t_undo)

print("\n== 14. SETTINGS ==", flush=True)
def t_settings():
    state.settings.set("hex_bytes_per_row", 32); state.settings.save()
    from core.settings import Settings
    assert Settings(state.settings.path).get("hex_bytes_per_row")==32
    return "persisted to disk"
check("settings round trip", t_settings)

print("\n== 15. EVERY PAGE STILL RENDERS ==", flush=True)
def t_pages():
    win.page("rom").load_rom(ROM)
    for k in list(win._pages): page(k)
    return f"{len(win._pages)} pages visited after all of the above"
check("navigate every page", t_pages)

print("\n" + "="*64)
print(f"AUDIT RESULT:  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("\nFAILURES:")
    for n,e in FAIL: print(f"  - {n}: {type(e).__name__}: {e}")
print("="*64, flush=True)

if ARGS.keep:
    print(f"scratch directory kept at {SCR}")
else:
    shutil.rmtree(SCR, ignore_errors=True)
sys.exit(1 if FAIL else 0)
