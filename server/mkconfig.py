"""Ключи и настройки приёмника: сертификат на IP, ключ установки, пароль страницы.

    python3 mkconfig.py --ip 203.0.113.5 --port 8443 --out /etc/orthofill-receiver

Пишет в --out: cert.pem, key.pem (600), config.json (600, для службы) и
telemetry.json — его кладут рядом с Orthofill.exe на каждом компьютере
(или в папку проекта перед build.ps1 — тогда он встроится в exe).
Повторный запуск не перезаписывает ключи (иначе программы перестанут
доверять серверу) — только с --force."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


def _write_private(p: Path, text: str) -> None:
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    os.chmod(p, 0o600)


def make_cert(ip: str, out: Path, days: int = 3650) -> None:
    """Самоподписанный EC P-256 с SAN=IP — подходит и для строгой проверки
    (VERIFY_X509_STRICT в Python 3.13+)."""
    key, cert = out / 'key.pem', out / 'cert.pem'
    with tempfile.TemporaryDirectory() as tmp:
        tmp_key = Path(tmp) / 'key.pem'
        subprocess.run(
            ['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
             '-nodes', '-keyout', str(tmp_key), '-out', str(cert), '-days', str(days),
             '-subj', f'/CN={ip}', '-addext', f'subjectAltName=IP:{ip}',
             '-addext', 'basicConstraints=critical,CA:TRUE',
             '-addext', 'keyUsage=critical,digitalSignature,keyCertSign',
             '-addext', 'extendedKeyUsage=serverAuth'],
            check=True, capture_output=True)
        _write_private(key, tmp_key.read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--ip', required=True, help='IP сервера, как его видят компьютеры клиники')
    ap.add_argument('--port', type=int, default=8443)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--db', type=Path, help='база событий (по умолчанию — в --out)')
    ap.add_argument('--doctor', default='', help='прозвище врача в telemetry.json (необязательно)')
    ap.add_argument('--force', action='store_true', help='перезаписать ключи и сертификат')
    a = ap.parse_args(argv)
    ipaddress.ip_address(a.ip)                    # только IP: домена нет
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'config.json').exists() and not a.force:
        print(f'{out / "config.json"} уже есть — ключи не трогаю (--force — заменить).',
              file=sys.stderr)
        raise SystemExit(1)
    make_cert(a.ip, out)
    key = secrets.token_urlsafe(32)
    password = secrets.token_urlsafe(24)
    cfg = {'db': str(a.db or out / 'events.db'), 'keys': [key], 'admin_password': password,
           'retention_days': 180, 'host': '0.0.0.0', 'port': a.port,
           'cert': str(out / 'cert.pem'), 'key': str(out / 'key.pem')}
    _write_private(out / 'config.json', json.dumps(cfg, ensure_ascii=False, indent=2))
    tel = {'url': f'https://{a.ip}:{a.port}', 'key': key,
           'cert': (out / 'cert.pem').read_text(), 'doctor': a.doctor}
    (out / 'telemetry.json').write_text(json.dumps(tel, ensure_ascii=False, indent=2),
                                        encoding='utf-8')
    print(f'Пароль страницы: {password}')
    print(f'Файл для программы: {out / "telemetry.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
