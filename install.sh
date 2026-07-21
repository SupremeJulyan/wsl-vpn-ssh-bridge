#!/usr/bin/env bash

set -Eeuo pipefail

die() {
  printf '错误: %s\n' "$*" >&2
  exit 1
}

source_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
source_dir="$(cd -- "$(dirname -- "$source_path")" && pwd)"
install_dir="${XDG_DATA_HOME:-${HOME:?}/.local/share}/wsl-vpn-ssh-bridge"
bin_dir="${HOME:?}/.local/bin"
config_dir="${HOME:?}/.wsl-vpn-ssh"
bashrc="${HOME:?}/.bashrc"

for command in install ln readlink python3; do
  command -v "$command" >/dev/null 2>&1 || die "缺少命令 '$command'"
done

mkdir -p -- \
  "$install_dir/bin" "$install_dir/lib" "$install_dir/libexec" \
  "$install_dir/shell" "$install_dir/systemd" "$bin_dir" "$config_dir"
chmod 700 "$config_dir"

scripts=(
  bin/ssh-vpn bin/sshfs-vpn systemd/install-user-service.sh
)
helpers=(
  lib/config_wizard.py lib/config_editor.py lib/password_crypto.py
  libexec/vpn-relay-pool.sh libexec/start-vpn-relay.ps1
  libexec/windows_tcp_relay.py shell/ssh-vpn-reminder.sh
  systemd/sshfs-vpn-cleanup.service.in
)
for file in "${scripts[@]}"; do
  [[ -r "$source_dir/$file" ]] || die "安装文件缺失: $file"
  install -m 755 -- "$source_dir/$file" "$install_dir/$file"
done
for file in "${helpers[@]}"; do
  [[ -r "$source_dir/$file" ]] || die "安装文件缺失: $file"
  install -m 644 -- "$source_dir/$file" "$install_dir/$file"
done

for name in ssh-vpn sshfs-vpn; do
  target="$bin_dir/$name"
  if [[ -e "$target" && ! -L "$target" ]]; then
    die "不会覆盖已有文件: $target"
  fi
done
ln -sfn -- "$install_dir/bin/ssh-vpn" "$bin_dir/ssh-vpn"
ln -sfn -- "$install_dir/bin/sshfs-vpn" "$bin_dir/sshfs-vpn"

# Migrate legacy project-local configs without deleting the originals.
for file in ssh-conf.json sshfs-conf.json; do
  if [[ -r "$source_dir/$file" && ! -e "$config_dir/$file" ]]; then
    install -m 600 -- "$source_dir/$file" "$config_dir/$file"
    printf '已迁移配置: %s\n' "$config_dir/$file"
  fi
done

path_line='export PATH="$HOME/.local/bin:$PATH"'
if [[ ":$PATH:" != *":$bin_dir:"* ]] && ! grep -Fqx "$path_line" "$bashrc" 2>/dev/null; then
  printf '\n# wsl-vpn-ssh-bridge\n%s\n' "$path_line" >>"$bashrc"
fi
reminder_line="source \"$install_dir/shell/ssh-vpn-reminder.sh\""
if ! grep -Fqx "$reminder_line" "$bashrc" 2>/dev/null; then
  printf '%s\n' "$reminder_line" >>"$bashrc"
fi

if [[ "${WSL_VPN_SKIP_SERVICE:-0}" == 1 ]]; then
  printf '已按 WSL_VPN_SKIP_SERVICE=1 跳过 SSHFS 清理服务安装\n'
elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  "$install_dir/systemd/install-user-service.sh"
else
  printf '警告: 当前用户级 systemd 不可用，已跳过 SSHFS 清理服务安装\n' >&2
fi

printf '\n安装完成。配置目录: %s\n' "$config_dir"
printf '重新打开终端后可直接使用: ssh-vpn / sshfs-vpn\n'
if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
  printf '当前终端立即生效: export PATH="%s:$PATH"\n' "$bin_dir"
fi
