# WSL VPN SSH Bridge

让 WSL 中的 SSH 和 SSHFS 复用 Windows 主机的 VPN 网络。当 Windows 可以访问 VPN 内服务器、但 WSL 无法直接访问时，本工具在 Windows 上启动临时 TCP 中继，并通过 WSL 的本地回环地址连接它。

中继只处理 TCP，不依赖特定 VPN 产品，可用于 aTrust、Cisco Secure Client、FortiClient、GlobalProtect、Ivanti、OpenVPN、WireGuard 等。

## 工作方式

```text
WSL SSH/SSHFS -> Windows 127.0.0.1 随机端口 -> Windows VPN -> 目标服务器
```

相同的目标主机和端口共用一个中继。SSH 与多个 SSHFS 挂载通过租约共享它；最后一个使用者退出后，中继自动停止。

## 安装

```bash
./install.sh
```

程序安装到 `~/.local/share/wsl-vpn-ssh-bridge`，命令链接到 `~/.local/bin`，并自动安装和启动
用户级 SSHFS 清理服务。重新打开终端后可直接使用 `ssh-vpn` 和 `sshfs-vpn`。

配置固定保存在 `~/.wsl-vpn-ssh/ssh-conf.json` 和
`~/.wsl-vpn-ssh/sshfs-conf.json`。配置目录权限为 `0700`，文件权限为 `0600`。若项目目录存在
旧配置且目标文件尚不存在，安装程序会复制迁移并保留原文件。

源码按用途组织：`bin/` 存放命令入口，`lib/` 存放配置与加密模块，`libexec/` 存放 VPN 中继，
`shell/` 存放终端集成，`systemd/` 存放服务，`examples/` 存放示例。项目根目录只保留安装脚本和
仓库说明文件。

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

`~/.wsl-vpn-ssh/ssh-conf.json` 可按名称保存 SSH 连接信息：

```bash
ssh-vpn config
ssh-vpn list
ssh-vpn gkn_zy
ssh-vpn user@10.0.0.10
ssh-vpn user@10.0.0.10 hostname
VPN_TARGET_PORT=22022 ssh-vpn user@10.0.0.10
```

配置可包含 `name`、`ip`、`user`、`port`、`vpn`、`private_key_path` 和 `password`。
推荐使用私钥；配置密码时需安装 `sshpass`。

首次运行 `ssh-vpn config` 可在终端中交互创建 `ssh-conf.json`。`port` 默认 `22`，`vpn`
默认 `true`，`encrypt_passwords` 始终自动设为 `true`。密码输入不会回显，保存前即加密，不会先把
明文写入 JSON。配置文件已经存在时，`config` 会打开终端菜单：先用方向键和回车选择配置名，
再编辑、保存或删除具体字段；菜单中也可以新增配置。

若必须使用密码，可在配置顶层加入 `"encrypt_passwords": true`。当 `password` 还是明文时，
第一次执行 `ssh-vpn name` 会要求设置加密口令，并把密码原子替换为 `enc:v1:...` 密文；
以后连接时输入该口令即可。也可通过 `WSL_VPN_MASTER_PASSWORD` 提供口令（注意环境变量可能被
同一用户的其他进程读取，不如交互输入安全）。加密依赖 `openssl`，忘记口令后无法恢复密码。

安装程序会在 Bash 中启用挂载目录登录提醒；进入 SSHFS 挂载目录时会提示对应的
`ssh-vpn name` 命令。

## SSHFS

推荐使用 `private_key_path`，不要把密码写入配置或提交到 Git。

`sshfs-conf.json` 同样支持顶层的 `"encrypt_passwords": true`。首次 `mount` 会加密并回写仍为
明文的密码；`list`、`status` 和 `unmount` 不会读取或要求输入加密口令。

首次运行 `sshfs-vpn config` 可交互填写连接字段、远程目录和本地挂载目录，并创建固定的
`sshfs-conf.json`；端口、VPN 和加密默认值与 SSH 向导相同。文件存在时，`config` 会打开相同的
终端配置编辑菜单。

```bash
sshfs-vpn config

# 挂载第一项
sshfs-vpn mount

# 挂载全部
sshfs-vpn mount -all

# 挂载或卸载指定项
sshfs-vpn mount example
sshfs-vpn unmount example

# 查看状态或卸载全部
sshfs-vpn status
sshfs-vpn unmount
```

配置字段 `vpn: true` 表示通过 Windows VPN 中继连接；设为 `false` 时直接连接目标。旧字段 `atrust: true` 仍兼容。

## WSL 关闭时自动清理

WSL 正常关闭时，用户级 systemd 服务会卸载全部 SSHFS；意外关闭时 FUSE 由内核清理，Windows 中继会在连接消失并空闲 30 秒后退出。

```bash
~/.local/share/wsl-vpn-ssh-bridge/systemd/install-user-service.sh
systemctl --user status sshfs-vpn-cleanup.service
```

## 安全说明

- 中继仅监听 Windows/WSL 共享的 `127.0.0.1`。
- 首次 SSHFS 连接使用 `StrictHostKeyChecking=accept-new`；之后主机密钥变化会被拒绝。
- 私钥、密码和真实 `sshfs-conf.json` 不应提交到版本库。
- 当前实现仅支持 TCP，不支持 UDP。
