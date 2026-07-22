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
`shell/` 存放终端集成，`systemd/` 存放服务，`examples/` 存放示例。项目根目录只保留安装、
卸载脚本和仓库说明文件。

卸载时运行：

```bash
./uninstall.sh
```

交互运行时会询问是否同时删除 `~/.wsl-vpn-ssh/`。使用 `--purge` 可删除程序、配置和挂载目录，
使用 `--keep-config` 可明确保留配置。卸载时会先解除配置中的全部挂载；如果仍检测到挂载点，
则拒绝删除配置目录。

## 要求

- Windows 11 与 WSL 2
- WSL mirrored 网络模式
- Windows Python 3，可通过 `py.exe -3` 启动
- WSL 中安装 `openssh-client`、`python3`、`util-linux`、`openssl`
- 使用密码登录 SSH 时安装 `sshpass`
- 使用 SSHFS 挂载时安装 `sshfs`
- 若需自动清理挂载，WSL 中启用 systemd
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

首次连接新主机时，`ssh-vpn` 会自动接受主机密钥并写入 `~/.ssh/known_hosts`，无需手动输入
`yes`。如果已保存主机的密钥发生变化，SSH 仍会拒绝连接并显示安全警告。

首次运行 `ssh-vpn config` 可在终端中交互创建 `ssh-conf.json`。`port` 默认 `22`，`vpn`
默认 `true`，`encrypt_passwords` 始终自动设为 `true`。密码输入不会回显，保存前即加密，不会先把
明文写入 JSON。配置文件已经存在时，`config` 会打开终端菜单：先用方向键和回车选择配置名，
再编辑、保存或删除具体字段；菜单中也可以新增配置。

菜单中使用 `↑`、`↓`、`←`、`→` 选择配置或字段，按 `Enter` 编辑和确认，按 `Esc` 取消。
编辑 `vpn` 时左右键用于开关，编辑 `port` 时左右键用于增减端口。密码只显示是否已设置；输入
新密码可替换，输入 `-` 可清除，留空则保留原密码。

向导会自动写入 `"encrypt_passwords": true`。当旧配置中的 `password` 还是明文时，第一次执行
`ssh-vpn name` 会要求设置加密口令，并把密码原子替换为 `enc:v1:...` 密文；
以后连接时输入该口令即可。也可通过 `WSL_VPN_MASTER_PASSWORD` 提供口令（注意环境变量可能被
同一用户的其他进程读取，不如交互输入安全）。加密依赖 `openssl`，忘记口令后无法恢复密码。

安装程序会在 Bash 中启用挂载目录登录提醒；进入 SSHFS 挂载目录时会提示对应的
`ssh-vpn name` 命令。

如果 SSH 与 SSHFS 配置使用相同的 `name`，在挂载目录或其子目录中执行不带远程命令的
`ssh-vpn name`，登录后会自动进入映射的远程目录。例如本地挂载点是
`/home/julyan/project/node37`、远程目录是 `/home/zhuyuan`，从本地 `node37/test` 执行
`ssh-vpn node37` 后会进入远程 `/home/zhuyuan/test`。显式传入远程命令时不会自动切换目录。

## SSHFS

推荐使用 `private_key_path`，不要把密码写入配置或提交到 Git。

`sshfs-conf.json` 同样支持顶层的 `"encrypt_passwords": true`。首次 `mount` 会加密并回写仍为
明文的密码；`list`、`status` 和 `unmount` 不会读取或要求输入加密口令。

首次运行 `sshfs-vpn config` 可交互填写连接字段、远程目录和本地挂载目录，并创建固定的
`sshfs-conf.json`；端口、VPN 和加密默认值与 SSH 向导相同。文件存在时，`config` 会打开相同的
终端配置编辑菜单。本地挂载目录默认是运行 `sshfs-vpn config` 时所在的当前目录下与配置名称
同名的子目录；例如在 `~/work` 创建名称 `server-a`，会立即创建并保存绝对路径
`~/work/server-a`。手动填写相对路径时，则以执行 `sshfs-vpn` 时的当前目录为基准。

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

连接失败时可启用详细日志（不会输出密码）：

```bash
SSHFS_VPN_DEBUG=1 sshfs-vpn mount example
```

配置字段 `vpn: true` 表示通过 Windows VPN 中继连接；设为 `false` 时直接连接目标。旧字段 `atrust: true` 仍兼容。

## WSL 关闭时自动清理

WSL 正常关闭时，用户级 systemd 服务会解除全部 SSHFS 挂载；意外关闭时 FUSE 由内核清理，Windows 中继会在连接消失并空闲 30 秒后退出。

```bash
~/.local/share/wsl-vpn-ssh-bridge/systemd/install-user-service.sh
systemctl --user status sshfs-vpn-cleanup.service
```

## 安全说明

- 中继仅监听 Windows/WSL 共享的 `127.0.0.1`。
- 中继状态目录必须属于当前用户，拒绝符号链接，并强制使用 `0700`；状态、锁和租约文件使用
  `0600`，防止其他本地用户读取或篡改。
- Windows 启动器会确认随机端口的监听进程就是刚启动的中继，避免端口释放与重新绑定之间被
  其他进程抢占。
- 首次 SSHFS 连接使用 `StrictHostKeyChecking=accept-new`；之后主机密钥变化会被拒绝。
- SSHFS 对非 22 端口使用 `[ip]:port` 作为主机密钥别名，避免同一 IP 上不同 SSH 服务共用或
  冲突主机密钥。
- 私钥、密码和真实 `sshfs-conf.json` 不应提交到版本库。
- 当前实现仅支持 TCP，不支持 UDP。
