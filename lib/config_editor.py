#!/usr/bin/env python3
"""Terminal editor for SSH and SSHFS configuration files."""

import argparse
import curses
import os

from config_wizard import load_config, save_config
from password_crypto import PREFIX, encrypt


KEY_UP = (curses.KEY_UP, curses.KEY_LEFT, ord("k"), ord("h"))
KEY_DOWN = (curses.KEY_DOWN, curses.KEY_RIGHT, ord("j"), ord("l"))


def text_input(screen, prompt, initial="", secret=False):
    height, width = screen.getmaxyx()
    value = list(str(initial))
    while True:
        shown = "*" * len(value) if secret else "".join(value)
        screen.move(height - 2, 0)
        screen.clrtoeol()
        screen.addnstr(height - 2, 0, f"{prompt}{shown}", width - 1)
        screen.refresh()
        key = screen.get_wch()
        if key in ("\n", "\r"):
            return "".join(value)
        if key == "\x1b":
            return None
        if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
            if value:
                value.pop()
        elif isinstance(key, str) and key.isprintable():
            value.append(key)


def confirm(screen, prompt):
    answer = text_input(screen, f"{prompt} [y/N]: ")
    return answer is not None and answer.lower() in ("y", "yes")


def draw_menu(screen, title, rows, selected, footer):
    screen.erase()
    height, width = screen.getmaxyx()
    screen.addnstr(0, 0, title, width - 1, curses.A_BOLD)
    for index, row in enumerate(rows[:max(0, height - 4)]):
        attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
        screen.addnstr(index + 2, 2, row, width - 4, attr)
    screen.addnstr(height - 1, 0, footer, width - 1, curses.A_DIM)
    screen.refresh()


def master_secret(screen):
    first = text_input(screen, "设置配置加密口令: ", secret=True)
    if not first:
        return None
    second = text_input(screen, "再次输入加密口令: ", secret=True)
    if first != second:
        text_input(screen, "两次口令不一致，按回车继续")
        return None
    return first


def edit_entry(screen, kind, original):
    entry = dict(original)
    pending_password = None
    fields = ["name", "ip", "user", "password", "private_key_path"]
    if kind == "sshfs":
        fields += ["remote_path", "local_path"]
    fields += ["port", "vpn"]
    labels = {
        "name": "配置名称", "ip": "服务器 IP/主机名", "user": "用户名",
        "password": "密码", "private_key_path": "私钥路径",
        "remote_path": "远程目录", "local_path": "本地挂载目录",
        "port": "SSH 端口", "vpn": "VPN 中继",
    }
    selected = 0
    while True:
        rows = []
        for field in fields:
            if field == "password":
                current = pending_password if pending_password is not None else entry.get(field, "")
                value = "已设置" if current else "未设置"
            elif field == "vpn":
                value = "开启" if entry.get(field, True) else "关闭"
            else:
                value = str(entry.get(field, ""))
            rows.append(f"{labels[field]:<16} {value}")
        rows += ["保存", "删除配置", "取消"]
        draw_menu(screen, f"编辑配置: {entry.get('name') or '新配置'}", rows, selected,
                  "↑↓选择  ←→调整  Enter编辑/确认  Esc取消")
        key = screen.getch()
        if key in KEY_UP:
            selected = (selected - 1) % len(rows)
        elif key in KEY_DOWN:
            selected = (selected + 1) % len(rows)
        elif key == 27:
            return "cancel", None
        elif selected < len(fields) and key in (curses.KEY_LEFT, curses.KEY_RIGHT):
            field = fields[selected]
            if field == "vpn":
                entry[field] = not entry.get(field, True)
            elif field == "port":
                step = -1 if key == curses.KEY_LEFT else 1
                entry[field] = min(65535, max(1, int(entry.get(field, 22)) + step))
        elif key in (10, 13, curses.KEY_ENTER):
            if selected < len(fields):
                field = fields[selected]
                if field == "vpn":
                    entry[field] = not entry.get(field, True)
                elif field == "password":
                    value = text_input(screen, "输入新密码（留空保留，输入 - 清除）: ", secret=True)
                    if value == "-":
                        pending_password = ""
                    elif value:
                        pending_password = value
                else:
                    value = text_input(screen, f"{labels[field]}: ", str(entry.get(field, "")))
                    if value is not None:
                        if field == "port":
                            if not value.isdigit() or not 1 <= int(value) <= 65535:
                                text_input(screen, "端口必须是 1-65535，按回车继续")
                                continue
                            entry[field] = int(value)
                        else:
                            entry[field] = value.strip()
            elif selected == len(fields):
                required = ["name", "ip", "user"] + (["remote_path"] if kind == "sshfs" else [])
                missing = [labels[field] for field in required if not entry.get(field)]
                if missing:
                    text_input(screen, f"必填项为空: {', '.join(missing)}；按回车继续")
                    continue
                if pending_password:
                    secret = master_secret(screen)
                    if secret is None:
                        continue
                    entry["password"] = encrypt(pending_password, secret)
                elif pending_password == "":
                    entry.pop("password", None)
                elif entry.get("password") and not str(entry["password"]).startswith(PREFIX):
                    secret = master_secret(screen)
                    if secret is None:
                        continue
                    entry["password"] = encrypt(str(entry["password"]), secret)
                entry.setdefault("port", 22)
                entry.setdefault("vpn", True)
                return "save", entry
            elif selected == len(fields) + 1:
                if original and confirm(screen, f"确认删除 '{original.get('name', '')}'"):
                    return "delete", None
            else:
                return "cancel", None


def run(screen, kind, path):
    curses.curs_set(0)
    screen.keypad(True)
    collection = "hosts" if kind == "ssh" else "mounts"
    while True:
        data = load_config(path, collection)
        entries = data[collection]
        rows = [str(item.get("name") or "<未命名>") for item in entries]
        rows += ["＋ 新增配置", "退出"]
        selected = 0
        while True:
            draw_menu(screen, "选择要编辑的配置", rows, selected,
                      "↑↓←→选择  Enter确认  q/Esc退出")
            key = screen.getch()
            if key in KEY_UP:
                selected = (selected - 1) % len(rows)
            elif key in KEY_DOWN:
                selected = (selected + 1) % len(rows)
            elif key in (ord("q"), 27) or selected == len(rows) - 1 and key in (10, 13, curses.KEY_ENTER):
                return
            elif key in (10, 13, curses.KEY_ENTER):
                is_new = selected == len(entries)
                original = {} if is_new else entries[selected]
                action, result = edit_entry(screen, kind, original)
                if action == "save":
                    duplicate = next((i for i, item in enumerate(entries)
                                      if i != selected and item.get("name") == result["name"]), None)
                    if duplicate is not None:
                        text_input(screen, "该配置名称已存在，按回车继续")
                        continue
                    if is_new:
                        entries.append(result)
                    else:
                        entries[selected] = result
                    save_config(path, data)
                    break
                if action == "delete":
                    entries.pop(selected)
                    save_config(path, data)
                    break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("ssh", "sshfs"))
    parser.add_argument("config")
    args = parser.parse_args()
    if not os.isatty(0) or not os.isatty(1):
        raise SystemExit("config 编辑器需要在交互式终端中运行")
    curses.wrapper(run, args.kind, args.config)


if __name__ == "__main__":
    main()
