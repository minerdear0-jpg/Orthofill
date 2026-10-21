import shutil
import subprocess
import sys

import pytest

from orthofill.controller import Controller, layout_mode
from orthofill.journal import Journal

from conftest import ORDER, ROOT

REF_RAW = ("активация, лигатурная,этап рабочий, класс по молярам 1 и клыкам, замена дуги "
           "на верху 18 25 нити. ношение эластиков перепел, явка через 4 недели. ")


@pytest.fixture
def clip():
    return []


@pytest.fixture
def ctl(tmp_path, clip):
    return Controller(Journal(tmp_path / "j.db"), clip.append)


def test_layout_mode():
    assert layout_mode(899) == "narrow" and layout_mode(900) == "wide"


def test_no_file(ctl):
    assert ctl.file_status == "Пресетов нет — импортируйте xlsx"
    assert ctl.generate("лигатурная").status == "Сначала импортируйте пресет (xlsx)"


def test_file_status_ok(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert ctl.file_status == "✓ пунктов: 124 · эталоны 1/1"
    assert ctl.journal.get_setting("preset_id") == str(ctl.preset_id)
    assert ctl.workbook.name == "order"


def test_file_status_mismatch(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная").text.replace("4 недели.", "6 недель.")
    ctl.save_reference("лигатурная", text)
    assert ctl.file_status == "⚠ эталоны 1/2 — подробнее"
    assert any("эталон 2" in d for d in ctl.details)


def test_file_with_problems_blocks_generate(ctl, tmp_path):
    import openpyxl
    p = tmp_path / "bad.xlsx"
    xl = openpyxl.Workbook()
    for r in [("ID_CLASS", "CLASS_LIST"), ("1", "Жалобы:"), ("1", "дубль")]:
        xl.active.append(r)
    xl.save(p)
    ctl.import_xlsx(p)
    assert ctl.file_status == "✗ ошибки в файле: 1 — подробнее"
    assert ctl.presets.list() == [] and ctl.workbook is None
    assert ctl.generate("x").status == "Сначала импортируйте пресет (xlsx)"


def test_generate_copies_and_logs(ctl, clip, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    r = ctl.generate(REF_RAW)
    assert r.copied and r.status == "Скопировано в буфер" and clip == [r.text]
    assert r.text.splitlines()[0] == "Жалобы: активация"
    assert "этап рабочий" not in r.defaults_line and "явка" not in r.defaults_line
    assert ctl.last_entry_id is not None


def test_generate_defaults_line(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert ctl.generate("лигатурная").defaults_line.startswith("по умолчанию: жалоб нет, этап рабочий")


def test_generate_empty_raw(ctl, clip, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    r = ctl.generate("   \n")
    assert r.status == "Введите краткую запись" and not r.copied and clip == []


def test_regenerate_needs_confirm_after_edit(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert not ctl.needs_confirm_regenerate("")
    text = ctl.generate("лигатурная").text
    assert not ctl.needs_confirm_regenerate(text)
    assert ctl.needs_confirm_regenerate(text + "\nправка")
    ctl.copy(text + "\nправка")
    assert not ctl.needs_confirm_regenerate(text + "\nправка")


def test_copy_logs(ctl, clip, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.generate("лигатурная")
    assert ctl.copy("правленый") == "Скопировано в буфер" and clip[-1] == "правленый"


def test_save_reference(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная, перепел").text
    assert ctl.save_reference("лигатурная, перепел", text) == "Эталон 2 сохранён в пресет «order»"
    assert ctl.file_status == "✓ пунктов: 124 · эталоны 2/2"
    assert ctl.needs_export_before_update(ctl.preset_id)


def test_cli_test_mode():
    r = subprocess.run([sys.executable, "-m", "orthofill", "--test", str(ORDER)],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[OK]" in r.stdout


def test_cli_raw_mode():
    r = subprocess.run([sys.executable, "-m", "orthofill", "--xlsx", str(ORDER), "--raw",
                        "замена дуги верх 14x25 ss"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and r.stdout.startswith("Жалобы: активация")
    assert "нет в классификаторе" in r.stderr


@pytest.mark.skipif(sys.platform != "win32" and not (
        __import__("os").environ.get("DISPLAY") or __import__("os").environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")
def test_cli_selftest_ui():
    r = subprocess.run([sys.executable, "-m", "orthofill", "--selftest-ui"],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr


# ---------- ревью: I7, I8 ----------
def test_save_reference_refuses_changed_note(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная, перепел").text
    assert ctl.save_reference("лигатурная, лиса", text) == \
        "Запись изменена — сформируйте протокол заново"
    assert len(ctl.presets.load(ctl.preset_id).references) == 1


def test_save_reference_unexpected_error_is_shown(ctl, order_xlsx, monkeypatch):
    import orthofill.controller as cmod
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная").text

    def boom(*a, **k):
        raise OSError("диск переполнен")
    monkeypatch.setattr(ctl.presets, "add_reference", boom)
    assert ctl.save_reference("лигатурная", text) == "✗ Ошибка: диск переполнен"


def test_import_unexpected_error_is_shown(ctl, order_xlsx, monkeypatch):
    import orthofill.controller as cmod

    def boom(*a, **k):
        raise ValueError("битый файл")
    monkeypatch.setattr(cmod, "load_workbook_file", boom)
    ctl.import_xlsx(order_xlsx)
    assert ctl.workbook is None and ctl.file_status == "✗ Ошибка: битый файл"


def test_generate_unexpected_error_is_shown(ctl, clip, order_xlsx, monkeypatch):
    import orthofill.controller as cmod
    ctl.import_xlsx(order_xlsx)

    def boom(*a, **k):
        raise RuntimeError("сбой")
    monkeypatch.setattr(cmod, "build_protocol", boom)
    r = ctl.generate("лигатурная")
    assert r.status == "✗ Ошибка: сбой" and not r.copied and clip == []


def test_cli_check_bad_file_is_friendly(tmp_path):
    import openpyxl
    import subprocess
    import sys
    p = tmp_path / "kons.xlsx"
    openpyxl.Workbook().save(p)
    r = subprocess.run([sys.executable, "-m", "orthofill", "--check", str(p)],
                       capture_output=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 2 and "Traceback" not in r.stderr
    assert "ID_CLASS" in r.stdout + r.stderr


# ---------- пресеты (0.2) ----------
def test_startup_migrates_last_file(ctl, order_xlsx):
    ctl.journal.set_setting("last_file", str(order_xlsx))
    ctl.startup()
    assert ctl.workbook.name == "order" and ctl.file_status.startswith("✓")


def test_startup_missing_last_file(ctl, tmp_path):
    ctl.journal.set_setting("last_file", str(tmp_path / "пропал.xlsx"))
    ctl.startup()
    assert ctl.workbook is None and ctl.file_status == "Пресетов нет — импортируйте xlsx"


def test_startup_restores_preset(ctl, order_xlsx, tmp_path, clip):
    ctl.import_xlsx(order_xlsx)
    ctl2 = Controller(Journal(tmp_path / "j.db"), clip.append)
    ctl2.startup()
    assert ctl2.preset_id == ctl.preset_id and ctl2.workbook.name == "order"


def test_startup_unknown_preset_falls_back(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.journal.set_setting("preset_id", "999")
    ctl.startup()
    assert ctl.workbook is not None and ctl.preset_id != 999


def test_import_bad_file_keeps_current(ctl, order_xlsx, tmp_path):
    import openpyxl
    ctl.import_xlsx(order_xlsx)
    pid = ctl.preset_id
    bad = tmp_path / "kons.xlsx"
    openpyxl.Workbook().save(bad)
    ctl.import_xlsx(bad, update_id=pid)
    assert ctl.preset_id == pid and ctl.file_status.startswith("✗")
    assert any("ID_CLASS" in d for d in ctl.details)
    assert len(ctl.presets.list()) == 1 and ctl.workbook is not None
    assert ctl.generate("лигатурная").copied           # прежний пресет работает


def test_import_update(ctl, order_xlsx, order_xlsx_with):
    ctl.import_xlsx(order_xlsx)
    pid = ctl.preset_id
    order_xlsx_with(("4f7", "Слон"))                    # тот же файл, новый пункт
    ctl.import_xlsx(order_xlsx, update_id=pid)
    assert ctl.preset_id == pid and "4f7" in ctl.workbook.by_id
    assert len(ctl.presets.list()) == 1


def test_export_then_reimport(ctl, order_xlsx, tmp_path):
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная, перепел").text
    ctl.save_reference("лигатурная, перепел", text)
    out = tmp_path / "выгрузка.xlsx"
    assert ctl.export_xlsx(out) == "Выгружено: выгрузка.xlsx"
    assert not ctl.needs_export_before_update(ctl.preset_id)
    ctl.import_xlsx(out)
    assert ctl.workbook.name == "выгрузка" and len(ctl.workbook.references) == 2
    assert ctl.file_status == "✓ пунктов: 124 · эталоны 2/2"


def test_export_locked(ctl, order_xlsx, tmp_path, monkeypatch):
    import orthofill.controller as cmod
    ctl.import_xlsx(order_xlsx)
    ctl.save_reference("лигатурная", ctl.generate("лигатурная").text)

    def locked(*a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(cmod, "export_workbook", locked)
    assert "закройте" in ctl.export_xlsx(tmp_path / "x.xlsx")
    assert ctl.needs_export_before_update(ctl.preset_id)


def test_switch_preset(ctl, order_xlsx, tmp_path):
    import shutil
    other = tmp_path / "консультация.xlsx"
    shutil.copy(order_xlsx, other)
    ctl.import_xlsx(order_xlsx)
    first = ctl.preset_id
    ctl.import_xlsx(other)
    assert ctl.workbook.name == "консультация"
    ctl.generate("лигатурная")
    ctl.switch_preset(first)
    assert ctl.workbook.name == "order" and ctl.last_protocol is None
    assert ctl.journal.get_setting("preset_id") == str(first)


def test_generate_without_copy(ctl, clip, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    r = ctl.generate("лигатурная", copy=False)
    assert r.text and not r.copied and clip == [] and ctl.last_entry_id is not None


# ---------- итоговое ревью 0.2 beta 1 ----------
def _dup_ref_file(order_xlsx):
    """Блок эталона скопирован ниже вместе с номером «1» — в 0.1 это работало."""
    import openpyxl
    from orthofill.workbook import load_workbook_file
    wb = load_workbook_file(order_xlsx)
    ref = wb.references[0]
    xl = openpyxl.load_workbook(order_xlsx)
    ws = xl.worksheets[0]
    r = ws.max_row + 2
    ws.cell(r, 3, 1)
    ws.cell(r, 4, ref.raw)
    for i, (code, text) in enumerate(ref.lines, start=1):
        ws.cell(r + i, 5, code or None)
        ws.cell(r + i, 6, text)
    xl.save(order_xlsx)


def test_duplicate_reference_number_is_file_problem(ctl, order_xlsx):
    _dup_ref_file(order_xlsx)
    ctl.import_xlsx(order_xlsx)
    assert ctl.file_status.startswith("✗") and ctl.presets.list() == []
    assert any("эталон" in d and "повторяется" in d for d in ctl.details)


def test_import_db_failure_is_shown(ctl, order_xlsx, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("база занята")
    monkeypatch.setattr(ctl.presets, "create", boom)
    ctl.import_xlsx(order_xlsx)                    # не падает
    assert ctl.file_status == "✗ Ошибка: база занята" and ctl.workbook is None


def test_startup_survives_bad_last_file(ctl, order_xlsx, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("сбой")
    monkeypatch.setattr(ctl.presets, "create", boom)
    ctl.journal.set_setting("last_file", str(order_xlsx))
    ctl.startup()                                  # окно должно открыться
    assert ctl.workbook is None and ctl.file_status.startswith("✗")


def test_majority_rule_recomputed_after_reference(ctl, order_xlsx_with, tmp_path):
    """Пресет без эталонов: все пункты «всегда»; после эталона без пункта —
    пункт снова только по упоминанию (угаданное не застывает в базе)."""
    import openpyxl
    wb = order_xlsx_with(("4o", "Подвязывание зуба короткой металлической лигатурой."))
    xl = openpyxl.load_workbook(wb.path)
    ws = xl.worksheets[0]
    for row in ws.iter_rows(min_col=3, max_col=6):
        for c in row:
            c.value = None
    xl.save(wb.path)
    ctl.import_xlsx(wb.path)
    assert "Подвязывание" in ctl.generate("лигатурная").text
    text = ctl.generate("лигатурная").text.replace(
        "Подвязывание зуба короткой металлической лигатурой.\n", "")
    ctl.save_reference("лигатурная", text)
    assert "Подвязывание" not in ctl.generate("лигатурная").text
    assert ctl.workbook.by_id["4o"].when is None       # в базе — не угаданное


def test_export_writes_only_explicit_settings(ctl, order_xlsx, tmp_path):
    import openpyxl
    ctl.import_xlsx(order_xlsx)
    out = tmp_path / "out.xlsx"
    ctl.export_xlsx(out)
    rows = list(openpyxl.load_workbook(out)["Настройки"].iter_rows(min_row=2, values_only=True))
    assert rows == []


def test_entry_links_to_preset_snapshot(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.generate("лигатурная, перепел")
    ctl.save_reference("лигатурная, перепел", ctl.last_protocol.text)
    ctl.generate("лигатурная")
    db = ctl.journal._db
    for (sha,) in db.execute("SELECT sha256 FROM entries"):
        assert db.execute("SELECT 1 FROM classifier_snapshots WHERE sha256=?", (sha,)).fetchone()
