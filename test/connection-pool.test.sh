#!/usr/bin/env bash

set -Eeuo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

mkdir -p "$test_root/home/.wsl-vpn-ssh" "$test_root/bin" "$test_root/runtime"
chmod 700 "$test_root/runtime"
cat >"$test_root/home/.wsl-vpn-ssh/config.json" <<EOF
{
  "hosts": [{
    "name": "dev",
    "ip": "10.0.0.2",
    "user": "alice",
    "port": 22,
    "vpn": false
  }],
  "mounts": [{
    "name": "project",
    "host": "dev",
    "remote_path": "/srv/project",
    "local_path": "$test_root/mount",
    "remote_terminal": "open"
  }]
}
EOF

cat >"$test_root/bin/mountpoint" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
cat >"$test_root/bin/sshfs" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${TEST_SSHFS_LOG:?}"
touch "${TEST_MASTER_STATE:?}"
EOF
cat >"$test_root/bin/ssh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${TEST_SSH_LOG:?}"
if [[ " $* " == *" -O check "* ]]; then
  [[ -e "${TEST_MASTER_STATE:?}" ]]
  exit
fi
EOF
chmod +x "$test_root/bin/mountpoint" "$test_root/bin/sshfs" "$test_root/bin/ssh"

export HOME="$test_root/home"
export XDG_RUNTIME_DIR="$test_root/runtime"
export PATH="$test_root/bin:$PATH"
export TEST_MASTER_STATE="$test_root/master-ready"
export TEST_SSHFS_LOG="$test_root/sshfs.log"
export TEST_SSH_LOG="$test_root/ssh.log"

"$project_root/bin/sshfs-bridge" mount project 2>"$test_root/mount.stderr"
"$project_root/bin/ssh-bridge" dev true 2>"$test_root/ssh.stderr"

grep -Fq 'ControlMaster=auto' "$TEST_SSHFS_LOG"
grep -Fq 'ControlPersist=10m' "$TEST_SSHFS_LOG"
grep -Fq "ControlPath=$XDG_RUNTIME_DIR/wsl-vpn-ssh-control-$UID/%C" "$TEST_SSHFS_LOG"
grep -Fxq 'SSH 连接池: 复用已有连接' "$test_root/ssh.stderr"
if grep -Fq '复用已有连接已禁用' "$test_root/ssh.stderr"; then
  printf 'reused connection status included the disabled label\n' >&2
  exit 1
fi
grep -Fq '[性能]' "$test_root/mount.stderr"
grep -Fq '[性能]' "$test_root/ssh.stderr"

rm -f "$TEST_SSHFS_LOG" "$TEST_MASTER_STATE"
WSL_VPN_SSH_CONNECTION_REUSE=0 \
  "$project_root/bin/sshfs-bridge" mount project 2>"$test_root/disabled.stderr"
if grep -Fq 'ControlMaster=auto' "$TEST_SSHFS_LOG"; then
  printf 'disabled connection reuse still passed ControlMaster\n' >&2
  exit 1
fi
grep -Fxq 'SSH 连接池: 已禁用' "$test_root/disabled.stderr"

printf 'connection pool integration test passed\n'
