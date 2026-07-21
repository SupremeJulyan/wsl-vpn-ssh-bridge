#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<'EOF'
用法:
  ./ssh-vpn.sh user@host [远程命令...]

示例:
  ./ssh-vpn.sh alice@10.0.0.10
  ./ssh-vpn.sh alice@10.0.0.10 uname -a

环境变量:
  VPN_TARGET_PORT=22   目标 SSH 端口
EOF
}

die() {
  printf '错误: %s\n' "$*" >&2
  exit 1
}

[[ $# -ge 1 ]] || { usage >&2; exit 2; }
case "$1" in
  -h|--help|help) usage; exit 0 ;;
esac

for command in ssh python3 powershell.exe wslpath flock; do
  command -v "$command" >/dev/null 2>&1 || die "缺少命令 '$command'"
done

destination="$1"
shift
if [[ "$destination" == *@* ]]; then
  ssh_user="${destination%@*}"
  target_host="${destination##*@}"
  local_destination="$ssh_user@127.0.0.1"
else
  target_host="$destination"
  local_destination="127.0.0.1"
fi
[[ -n "$target_host" ]] || die "目标主机不能为空"

target_port="${VPN_TARGET_PORT:-22}"
[[ "$target_port" =~ ^[0-9]+$ ]] \
  && ((target_port >= 1 && target_port <= 65535)) \
  || die "VPN_TARGET_PORT 必须是 1-65535 的整数"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/vpn-relay-pool.sh"
relay_holder="ssh-$$"
read -r relay_pid local_port relay_status < <(
  vpn_relay_acquire "$target_host" "$target_port" "$relay_holder"
) || die "Windows TCP 中继启动失败"

cleanup() {
  vpn_relay_release "$target_host" "$target_port" "$relay_holder" || true
}
trap cleanup EXIT INT TERM

printf 'VPN 中继(%s): 127.0.0.1:%s -> %s:%s (Windows PID %s)\n' \
  "$relay_status" "$local_port" "$target_host" "$target_port" "$relay_pid" >&2

host_key_alias="$target_host"
if [[ "$target_port" != 22 ]]; then
  host_key_alias="[$target_host]:$target_port"
fi

ssh \
  -p "$local_port" \
  -o "HostKeyAlias=$host_key_alias" \
  -o CheckHostIP=no \
  "$local_destination" "$@"
