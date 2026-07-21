# WSL VPN SSH Bridge

让 WSL 中的 SSH 和 SSHFS 复用 Windows 主机的 VPN 网络。当 Windows 可以访问 VPN 内服务器、但 WSL 无法直接访问时，本工具在 Windows 上启动临时 TCP 中继，并通过 WSL 的本地回环地址连接它。

中继只处理 TCP，不依赖特定 VPN 产品，可用于 aTrust、Cisco Secure Client、FortiClient、GlobalProtect、Ivanti、OpenVPN、WireGuard 等。

## 工作方式

```text
WSL SSH/SSHFS -> Windows 127.0.0.1 随机端口 -> Windows VPN -> 目标服务器
```

相同的目标主机和端口共用一个中继。SSH 与多个 SSHFS 挂载通过租约共享它；最后一个使用者退出后，中继自动停止。

## 要求

- Windows 11 与 WSL 2
- WSL mirrored 网络模式
- Windows Python 3，可通过 `py.exe -3` 启动
- WSL 中安装 `openssh-client`、`python3`、`util-linux`
- 使用 SSHFS 时安装 `sshfs`
- Windows 主机已经连接 VPN，并能访问目标 TCP 端口

Windows 用户目录的 `%UserProfile%\.wslconfig`：

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
```

修改后在 PowerShell 执行 `wsl --shutdown`。

## SSH

`ssh-config.json` 可按名称保存 SSH 连接信息，字段与 `sshfs-conf.json` 中的连接字段一致：

```bash
./ssh-vpn.sh gkn_zy
./ssh-vpn.sh user@10.0.0.10
./ssh-vpn.sh user@10.0.0.10 hostname
VPN_TARGET_PORT=22022 ./ssh-vpn.sh user@10.0.0.10
```

配置可包含 `name`、`ip`、`user`、`port`、`vpn`、`private_key_path` 和 `password`。
推荐使用私钥；配置密码时需安装 `sshpass`。可通过 `SSH_CONFIG` 指定其他配置文件。

在 Bash 中启用挂载目录登录提醒：

```bash
source /path/to/wsl-vpn-ssh-bridge/ssh-vpn-reminder.sh
```

将上面一行加入 `~/.bashrc` 后，每次进入配置中的 SSHFS 挂载目录，终端都会提示对应的
`ssh-vpn.sh name` 命令。

## SSHFS

复制示例配置，并填写真实服务器信息：

```bash
cp sshfs-conf.example.json sshfs-conf.json
```

推荐使用 `private_key_path`，不要把密码写入配置或提交到 Git。

```bash
# 挂载第一项
./sshfs.sh mount

# 挂载全部
./sshfs.sh mount -all

# 挂载或卸载指定项
./sshfs.sh mount example
./sshfs.sh unmount example

# 查看状态或卸载全部
./sshfs.sh status
./sshfs.sh unmount
```

配置字段 `vpn: true` 表示通过 Windows VPN 中继连接；设为 `false` 时直接连接目标。旧字段 `atrust: true` 仍兼容。

## WSL 关闭时自动清理

WSL 正常关闭时，用户级 systemd 服务会卸载全部 SSHFS；意外关闭时 FUSE 由内核清理，Windows 中继会在连接消失并空闲 30 秒后退出。

```bash
./install-user-service.sh
systemctl --user status sshfs-vpn-cleanup.service
```

## 安全说明

- 中继仅监听 Windows/WSL 共享的 `127.0.0.1`。
- 首次 SSHFS 连接使用 `StrictHostKeyChecking=accept-new`；之后主机密钥变化会被拒绝。
- 私钥、密码和真实 `sshfs-conf.json` 不应提交到版本库。
- 当前实现仅支持 TCP，不支持 UDP。
