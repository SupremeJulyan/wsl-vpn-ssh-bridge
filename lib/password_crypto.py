#!/usr/bin/env python3
"""Encrypt and decrypt passwords stored in bridge JSON configuration."""

import argparse
import base64
import binascii
import getpass
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile


PREFIX = "enc:v1:"
ENV_NAME = "WSL_VPN_MASTER_PASSWORD"


def master_password(confirm=False):
    value = os.environ.get(ENV_NAME)
    if value is not None:
        if not value:
            raise SystemExit(f"{ENV_NAME} 不能为空")
        return value
    if not sys.stdin.isatty() and not os.path.exists("/dev/tty"):
        raise SystemExit(f"无法交互读取加密口令；请设置 {ENV_NAME}")
    prompt = "请设置配置加密口令: " if confirm else "请输入配置加密口令: "
    value = getpass.getpass(prompt)
    if not value:
        raise SystemExit("加密口令不能为空")
    if confirm and value != getpass.getpass("请再次输入加密口令: "):
        raise SystemExit("两次输入的加密口令不一致")
    return value


def mac_key(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", b"wsl-vpn-hmac\0" + password.encode(), salt, 600_000, 32
    )


def crypt(data, password, decrypting=False):
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, password.encode() + b"\n")
        os.close(write_fd)
        write_fd = -1
        command = ["openssl", "enc"]
        if decrypting:
            command.append("-d")
        command.extend(["-aes-256-cbc", "-pbkdf2", "-iter", "600000",
                        "-pass", f"fd:{read_fd}"])
        result = subprocess.run(
            command, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, pass_fds=(read_fd,),
        )
    except FileNotFoundError:
        raise SystemExit("缺少命令 'openssl'，无法处理加密密码") from None
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)
    if result.returncode:
        raise ValueError("OpenSSL 加解密失败")
    return result.stdout


def encrypt(value, password):
    # OpenSSL output starts with "Salted__" followed by an eight-byte random salt.
    ciphertext = crypt(value.encode(), password)
    key = mac_key(password, ciphertext[8:16])
    tag = hmac.new(key, ciphertext, hashlib.sha256).digest()
    return PREFIX + base64.urlsafe_b64encode(ciphertext + tag).decode()


def decrypt(value, password):
    try:
        raw = base64.urlsafe_b64decode(value[len(PREFIX):].encode())
        ciphertext, tag = raw[:-32], raw[-32:]
        if len(ciphertext) < 32 or not ciphertext.startswith(b"Salted__"):
            raise ValueError
        key = mac_key(password, ciphertext[8:16])
        expected = hmac.new(key, ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError
        return crypt(ciphertext, password, decrypting=True).decode()
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise SystemExit("配置密码解密失败：加密口令错误或密文已损坏") from None


def atomic_write(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    mode = os.stat(path).st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix=".password-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("collection", choices=("hosts", "mounts"))
    parser.add_argument("name")
    args = parser.parse_args()
    try:
        with open(args.config, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"配置读取失败: {error}")

    enabled = isinstance(data, dict) and data.get("encrypt_passwords") is True
    entries = data.get(args.collection, []) if isinstance(data, dict) else data
    if args.collection == "mounts" and isinstance(data, dict) and "mounts" not in data:
        entries = [data]
    if not isinstance(entries, list):
        raise SystemExit(f"{args.collection} 必须是数组")
    entry = next((item for item in entries if isinstance(item, dict)
                  and str(item.get("name", "")) == args.name), None)
    if entry is None:
        raise SystemExit(f"未找到名为 '{args.name}' 的配置")
    value = str(entry.get("password") or "")
    if not value:
        return
    if value.startswith(PREFIX):
        sys.stdout.write(decrypt(value, master_password()))
    elif enabled:
        password = master_password(confirm=True)
        entry["password"] = encrypt(value, password)
        atomic_write(args.config, data)
        print(f"配置 '{args.name}' 的明文密码已加密并回写", file=sys.stderr)
        sys.stdout.write(value)
    else:
        sys.stdout.write(value)


if __name__ == "__main__":
    main()
