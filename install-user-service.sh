#!/usr/bin/env bash

set -Eeuo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(cd -- "$(dirname -- "$script_path")" && pwd)"
template="$script_dir/sshfs-vpn-cleanup.service.in"
user_unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit="$user_unit_dir/sshfs-vpn-cleanup.service"

command -v systemctl >/dev/null 2>&1 || {
  printf '错误: 缺少 systemctl\n' >&2
  exit 1
}
[[ -r "$template" ]] || {
  printf '错误: 无法读取模板 %s\n' "$template" >&2
  exit 1
}

mkdir -p -- "$user_unit_dir"
escaped_dir="${script_dir//\\/\\\\}"
escaped_dir="${escaped_dir//&/\\&}"
escaped_dir="${escaped_dir//|/\\|}"
sed "s|@TOOLKIT_DIR@|$escaped_dir|g" "$template" >"$unit"
systemctl --user daemon-reload
systemctl --user enable --now sshfs-vpn-cleanup.service
printf '已安装并启用: %s\n' "$unit"
