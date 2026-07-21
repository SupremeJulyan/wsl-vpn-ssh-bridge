#!/usr/bin/env bash

# Installed into the user's shell startup. It reminds the user how to open an SSH
# session when entering a local directory configured as an SSHFS mount.

_ssh_vpn_reminder_dir="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
_ssh_vpn_config_dir="${HOME:?}/.wsl-vpn-ssh"
_ssh_vpn_reminder_last_pwd=""
_ssh_vpn_reminder_last_name=""

_ssh_vpn_reminder() {
  local config_file="$_ssh_vpn_config_dir/sshfs-conf.json"
  local match=""

  [[ "$PWD" != "$_ssh_vpn_reminder_last_pwd" ]] || return 0
  _ssh_vpn_reminder_last_pwd="$PWD"
  [[ -r "$config_file" ]] || return 0

  match="$(python3 - "$config_file" "$PWD" "$_ssh_vpn_config_dir" <<'PY' 2>/dev/null
import json, os, sys

config_path, current_dir, script_dir = sys.argv[1:]
with open(config_path, encoding="utf-8") as f:
    data = json.load(f)
entries = data.get("mounts", []) if isinstance(data, dict) else data
if not isinstance(entries, list):
    raise SystemExit(0)

current_dir = os.path.realpath(current_dir)
for item in entries:
    if not isinstance(item, dict) or not item.get("name"):
        continue
    local_path = item.get("local_path")
    if not local_path:
        continue
    if not os.path.isabs(local_path):
        local_path = os.path.join(script_dir, local_path)
    local_path = os.path.realpath(os.path.expanduser(local_path))
    try:
        inside = os.path.commonpath((current_dir, local_path)) == local_path
    except ValueError:
        inside = False
    if inside:
        print(item["name"])
        break
PY
  )"

  if [[ -n "$match" && "$match" != "$_ssh_vpn_reminder_last_name" ]]; then
    printf '\033[33m提示：这是 SSHFS 挂载目录；登录服务器请使用 ssh-vpn %s\033[0m\n' \
      "$match"
  fi
  _ssh_vpn_reminder_last_name="$match"
}

case ";${PROMPT_COMMAND:-};" in
  *';_ssh_vpn_reminder;'*) ;;
  *) PROMPT_COMMAND="_ssh_vpn_reminder${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
esac
