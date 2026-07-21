#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<'EOF'
用法:
  ./uninstall.sh               交互询问是否删除配置
  ./uninstall.sh --purge       同时删除配置和挂载目录
  ./uninstall.sh --keep-config 保留配置和挂载目录
EOF
}

purge="ask"
case "${1:-}" in
  "") ;;
  --purge) purge="yes" ;;
  --keep-config) purge="no" ;;
  -h|--help|help) usage; exit ;;
  *) usage >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { usage >&2; exit 2; }

install_dir="${XDG_DATA_HOME:-${HOME:?}/.local/share}/wsl-vpn-ssh-bridge"
bin_dir="${HOME:?}/.local/bin"
config_dir="${HOME:?}/.wsl-vpn-ssh"
bashrc="${HOME:?}/.bashrc"
user_unit_dir="${XDG_CONFIG_HOME:-${HOME:?}/.config}/systemd/user"
unit="$user_unit_dir/sshfs-vpn-cleanup.service"

if [[ "$purge" == ask ]]; then
  if [[ -t 0 ]]; then
    printf '是否同时删除配置和挂载目录 %s？此操作不可恢复 [y/N]: ' "$config_dir"
    read -r answer
    case "$answer" in
      y|Y|yes|YES|Yes) purge="yes" ;;
      *) purge="no" ;;
    esac
  else
    purge="no"
  fi
fi

# Resolve every target before deletion and refuse an unexpectedly broad path.
case "$install_dir" in
  "${HOME:?}/.local/share/wsl-vpn-ssh-bridge"|*/wsl-vpn-ssh-bridge) ;;
  *) printf '错误: 拒绝删除异常安装目录: %s\n' "$install_dir" >&2; exit 1 ;;
esac

if [[ -x "$install_dir/bin/sshfs-vpn" && -r "$config_dir/sshfs-conf.json" ]]; then
  "$install_dir/bin/sshfs-vpn" unmount \
    || { printf '错误: SSHFS 挂载目录解除失败，已取消卸载\n' >&2; exit 1; }
fi

if [[ "${WSL_VPN_SKIP_SERVICE:-0}" != 1 ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now sshfs-vpn-cleanup.service >/dev/null 2>&1 || true
fi
if [[ -f "$unit" ]]; then
  rm -f -- "$unit"
fi
if [[ "${WSL_VPN_SKIP_SERVICE:-0}" != 1 ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi

if [[ "$purge" == yes && -d "$config_dir" ]]; then
  if command -v findmnt >/dev/null 2>&1 \
      && findmnt -rn -o TARGET | awk -v base="$config_dir" \
        '$0 == base || index($0, base "/") == 1 { found=1 } END { exit !found }'; then
    printf '错误: 配置目录下仍有挂载点，拒绝删除: %s\n' "$config_dir" >&2
    exit 1
  fi
  rm -rf -- "$config_dir"
fi

for name in ssh-vpn sshfs-vpn; do
  link="$bin_dir/$name"
  if [[ -L "$link" ]]; then
    target="$(readlink -f -- "$link" 2>/dev/null || true)"
    case "$target" in
      "$install_dir"/*) rm -f -- "$link" ;;
      *) printf '保留非本工具链接: %s -> %s\n' "$link" "$target" ;;
    esac
  fi
done

if [[ -f "$bashrc" ]]; then
  sed -i '\|wsl-vpn-ssh-bridge.*/ssh-vpn-reminder\.sh|d' "$bashrc"
fi

if [[ -d "$install_dir" ]]; then
  rm -rf -- "$install_dir"
fi

printf '卸载完成：命令、程序、终端提醒和用户服务已移除。\n'
if [[ "$purge" == yes ]]; then
  printf '配置和挂载目录已删除: %s\n' "$config_dir"
elif [[ -d "$config_dir" ]]; then
  printf '配置和挂载目录已保留: %s\n' "$config_dir"
  printf '如需完整清理，请运行: ./uninstall.sh --purge\n'
fi
