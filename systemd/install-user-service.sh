#!/usr/bin/env bash

set -Eeuo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -- "$(dirname -- "$script_path")" && pwd)"
install_root="$(cd -- "$script_dir/.." && pwd)"
template="$script_dir/sshfs-bridge-cleanup.service.in"
user_unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit="$user_unit_dir/sshfs-bridge-cleanup.service"

command -v systemctl >/dev/null 2>&1 || {
  printf '错误: 缺少 systemctl\n' >&2
  exit 1
}
[[ -r "$template" ]] || {
  printf '错误: 无法读取模板 %s\n' "$template" >&2
  exit 1
}

mkdir -p -- "$user_unit_dir"
systemctl --user disable --now sshfs-vpn-cleanup.service >/dev/null 2>&1 || true
rm -f -- "$user_unit_dir/sshfs-vpn-cleanup.service"
escaped_root="${install_root//\\/\\\\}"
escaped_root="${escaped_root//&/\\&}"
escaped_root="${escaped_root//|/\\|}"
sed "s|@INSTALL_ROOT@|$escaped_root|g" "$template" >"$unit"
systemctl --user daemon-reload
systemctl --user enable --now sshfs-bridge-cleanup.service
printf '已安装并启用: %s\n' "$unit"
