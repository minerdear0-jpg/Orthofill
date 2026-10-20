"""Запуск: без аргументов — окно; --check / --test / --raw — консоль (для отладки)."""
import argparse
import sys

if __package__ in (None, ''):          # запуск как скрипта (точка входа PyInstaller)
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = 'orthofill'

from orthofill import VERSION_LABEL  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='orthofill', description=f'Orthofill {VERSION_LABEL}')
    ap.add_argument('--check', metavar='XLSX', help='проверить файл классификатора')
    ap.add_argument('--test', metavar='XLSX', help='сверить программу с эталонами (C–F)')
    ap.add_argument('--xlsx', help='файл классификатора для --raw')
    ap.add_argument('--raw', help='краткая запись врача → протокол в stdout')
    args = ap.parse_args(argv)

    if not (args.check or args.test or args.raw):
        from orthofill.ui import run
        run()
        return 0

    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')

    from orthofill.engine import build_protocol, check_references, rule_warnings
    from orthofill.workbook import load_workbook_file

    if args.check:
        wb = load_workbook_file(args.check)
        print(f"[{'OK' if not wb.problems else 'ОШИБКИ'}] пунктов: {len(wb.items)}")
        for p in wb.problems:
            print(f'  ! {p}')
        for w in wb.warnings + rule_warnings(wb):
            print(f'  ? {w}')
        return 1 if wb.problems else 0

    if args.test:
        wb = load_workbook_file(args.test)
        failed = 0
        for r in check_references(wb):
            failed += not r.ok
            print(f"[{'OK' if r.ok else 'FAIL'}] эталон {r.case_id}")
            for code, text in r.missing:
                print(f'    нет в результате: {code} {text[:80]}')
            for code, text in r.extra:
                print(f'    лишнее:           {code} {text[:80]}')
        return 1 if failed else 0

    if not args.xlsx:
        ap.error('--raw требует --xlsx')
    p = build_protocol(load_workbook_file(args.xlsx), args.raw)
    print(p.text)
    for w in p.warnings:
        print(f'⚠ {w}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
