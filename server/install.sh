#!/usr/bin/env bash
# Установка приёмника телеметрии Orthofill на Debian (12/13).
#   sudo bash install.sh <IP сервера> [порт] [--no-firewall]
# Повторный запуск обновляет программу, ключи и сертификат не трогает.
set -euo pipefail

IP="${1:-}"
PORT="8443"
FIREWALL=1
shift || true
for a in "$@"; do
    case "$a" in
        --no-firewall) FIREWALL=0 ;;
        [0-9]*) PORT="$a" ;;
        *) echo "Неизвестный параметр: $a" >&2; exit 2 ;;
    esac
done
if [[ -z "$IP" ]]; then
    echo "Использование: sudo bash install.sh <IP сервера> [порт] [--no-firewall]" >&2
    exit 2
fi
if [[ $EUID -ne 0 ]]; then
    echo "Нужны права root (sudo)." >&2
    exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP=/opt/orthofill-receiver
ETC=/etc/orthofill-receiver
DATA=/var/lib/orthofill-receiver
USER_=orthofill-rx

echo "== Пакеты"
apt-get update -qq
apt-get install -y -qq python3 python3-venv openssl nftables >/dev/null

echo "== Пользователь службы"
id "$USER_" >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin "$USER_"

echo "== Программа"
install -d -m 755 "$APP"
rm -rf "$APP/receiver"
cp -r "$HERE/receiver" "$APP/receiver"
install -m 644 "$HERE/mkconfig.py" "$APP/mkconfig.py"
[[ -x "$APP/venv/bin/python" ]] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade 'aiohttp>=3.9'
install -d -m 750 -o "$USER_" -g "$USER_" "$DATA"

echo "== Ключи и сертификат"
if [[ -f "$ETC/config.json" ]]; then
    echo "   $ETC/config.json уже есть — ключи не меняю"
else
    install -d -m 750 "$ETC"
    python3 "$APP/mkconfig.py" --ip "$IP" --port "$PORT" --out "$ETC" --db "$DATA/events.db"
fi
chgrp "$USER_" "$ETC" "$ETC/config.json" "$ETC/key.pem"
chmod 750 "$ETC"
chmod 640 "$ETC/config.json" "$ETC/key.pem"

if [[ $FIREWALL -eq 1 ]]; then
    echo "== Файрвол: открыты только SSH и порт $PORT"
    SSH_PORTS="$( (sshd -T 2>/dev/null | awk '/^port /{print $2}'; \
                  [[ -n "${SSH_CONNECTION:-}" ]] && echo "${SSH_CONNECTION##* }"; echo 22) | sort -un | paste -sd, -)"
    cat > "$ETC/nftables.nft" <<NFT
table inet orthofill_rx {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        ct state invalid drop
        iif lo accept
        meta l4proto { icmp, ipv6-icmp } accept
        tcp dport { $SSH_PORTS } accept
        tcp dport $PORT ct state new limit rate over 50/second burst 100 packets drop
        tcp dport $PORT accept
    }
}
NFT
    nft -c -f "$ETC/nftables.nft"          # проверка до применения
    nft list table inet orthofill_rx >/dev/null 2>&1 && nft delete table inet orthofill_rx
    nft -f "$ETC/nftables.nft"
    grep -q "$ETC/nftables.nft" /etc/nftables.conf 2>/dev/null || \
        echo "include \"$ETC/nftables.nft\"" >> /etc/nftables.conf
    systemctl enable -q nftables
    echo "   SSH: $SSH_PORTS"
fi

echo "== Служба"
install -m 644 "$HERE/orthofill-receiver.service" /etc/systemd/system/orthofill-receiver.service
systemctl daemon-reload
systemctl enable -q orthofill-receiver
systemctl restart orthofill-receiver
sleep 2
systemctl --no-pager --lines=5 status orthofill-receiver || true

echo
echo "Готово."
echo "  Страница:  https://$IP:$PORT/   (браузер предупредит о самоподписанном сертификате;"
echo "             отпечаток: $(openssl x509 -in "$ETC/cert.pem" -noout -fingerprint -sha256 | cut -d= -f2))"
echo "  Пароль страницы — в $ETC/config.json (admin_password); имя пользователя любое."
echo "  Файл для программы: $ETC/telemetry.json — рядом с Orthofill.exe на каждом компьютере"
echo "  (или в папку проекта перед build.ps1 — встроится в exe)."
