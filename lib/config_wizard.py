#!/usr/bin/env python3
"""Interactive first-run configuration wizard for SSH and SSHFS."""

import argparse
import getpass
import json
import os
import tempfile

from password_crypto import encrypt, master_password


def required(prompt):
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("此项不能为空")


def port_value():
    while True:
        value = input("SSH 端口 [22]: ").strip() or "22"
        if value.isdigit() and 1 <= int(value) <= 65535:
            return int(value)
        print("端口必须是 1-65535 的整数")


def boolean_value():
    while True:
        value = input("是否使用 VPN 中继 [Y/n]: ").strip().lower()
        if value in ("", "y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("请输入 y 或 n")


def load_config(path, collection):
    if not os.path.exists(path):
        return {"encrypt_passwords": True, collection: []}
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"配置读取失败: {error}")
    if isinstance(data, list):
        data = {collection: data}
    elif isinstance(data, dict) and collection == "mounts" and "mounts" not in data:
        old_entry = {key: value for key, value in data.items()
                     if key != "encrypt_passwords"}
        data = {"encrypt_passwords": data.get("encrypt_passwords", True),
                "mounts": [old_entry]}
    if not isinstance(data, dict) or not isinstance(data.get(collection, []), list):
        raise SystemExit(f"配置文件中的 {collection} 必须是数组")
    data.setdefault(collection, [])
    data["encrypt_passwords"] = True
    return data


def save_config(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("ssh", "sshfs"))
    parser.add_argument("config_dir")
    args = parser.parse_args()
    collection = "hosts" if args.kind == "ssh" else "mounts"
    default_file = "ssh-conf.json" if args.kind == "ssh" else "sshfs-conf.json"

    print(f"创建 {'SSHFS' if args.kind == 'sshfs' else 'SSH'} 配置（Ctrl+C 取消）")
    entry = {
        "name": required("配置名称: "),
        "ip": required("服务器 IP 或主机名: "),
        "user": required("用户名: "),
    }
    plain_password = getpass.getpass("密码（留空则不保存）: ")
    key = input("私钥路径（留空则不设置）: ").strip()
    if args.kind == "sshfs":
        entry["remote_path"] = required("远程目录: ")
        local_default = os.path.join(os.getcwd(), entry["name"])
        entry["local_path"] = input(f"本地挂载目录 [{local_default}]: ").strip() or local_default
    entry["port"] = port_value()
    entry["vpn"] = boolean_value()
    if key:
        entry["private_key_path"] = key
    path = os.path.join(args.config_dir, default_file)

    if plain_password:
        entry["password"] = encrypt(plain_password, master_password(confirm=True))
    data = load_config(path, collection)
    entries = data[collection]
    existing = next((i for i, item in enumerate(entries)
                     if isinstance(item, dict) and item.get("name") == entry["name"]), None)
    if existing is None:
        entries.append(entry)
        action = "新增"
    else:
        answer = input(f"配置 '{entry['name']}' 已存在，是否覆盖 [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            raise SystemExit("已取消，配置文件未修改")
        entries[existing] = entry
        action = "更新"
    save_config(path, data)
    if args.kind == "sshfs":
        os.makedirs(os.path.expanduser(entry["local_path"]), exist_ok=True)
    print(f"已{action}配置 '{entry['name']}': {path}")


if __name__ == "__main__":
    main()
