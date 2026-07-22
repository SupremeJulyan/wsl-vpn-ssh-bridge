#!/usr/bin/env python3
"""Terminal editor for SSH and SSHFS configuration files."""

import argparse
import curses
import os

from config_wizard import load_config, save_config
from password_crypto import PREFIX, cache_password, encrypt


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
    cache_password(first)
    return first


def edit_entry(screen, kind, original):
    entry = dict(original)
    if kind == "sshfs":
        entry.setdefault("remote_terminal", "open")
    pending_password = None
    labels = {
        "name": "配置名称", "host": "SSH 配置名称",
        "ip": "服务器 IP/主机名", "user": "用户名",
        "password": "密码", "private_key_path": "私钥路径",
        "remote_path": "远程目录", "local_path": "本地挂载目录",
        "remote_terminal": "远程终端方式",
        "port": "SSH 端口", "vpn": "VPN 中继",
    }
    selected = 0
    while True:
        if kind == "ssh":
            fields = ["name", "ip", "user", "password", "private_key_path"]
        else:
            fields = ["name", "host"]
        if kind == "sshfs":
            fields += ["remote_path", "remote_terminal"]
            if entry.get("remote_terminal") != "now":
                fields.append("local_path")
        if kind == "ssh":
            fields += ["port", "vpn"]
        selected = min(selected, len(fields) + 2)
        rows = []
        for field in fields:
            if field == "password":
                current = pending_password if pending_password is not None else entry.get(field, "")
                value = "已设置" if current else "未设置"
            elif field == "vpn":
                value = "开启" if entry.get(field, True) else "关闭"
            elif field == "remote_terminal" and entry.get(field) == "now":
                value = "now（挂载到命令执行目录，不保存挂载目录）"
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
            elif field == "remote_terminal":
                choices = ("now", "open", "never")
                step = -1 if key == curses.KEY_LEFT else 1
                current = entry.get(field, "open")
                entry[field] = choices[(choices.index(current) + step) % len(choices)]
                if entry[field] == "now":
                    entry.pop("local_path", None)
            elif field == "port":
                step = -1 if key == curses.KEY_LEFT else 1
                entry[field] = min(65535, max(1, int(entry.get(field, 22)) + step))
        elif key in (10, 13, curses.KEY_ENTER):
            if selected < len(fields):
                field = fields[selected]
                if field == "vpn":
                    entry[field] = not entry.get(field, True)
                elif field == "remote_terminal":
                    choices = ("now", "open", "never")
                    current = entry.get(field, "open")
                    entry[field] = choices[(choices.index(current) + 1) % len(choices)]
                    if entry[field] == "now":
                        entry.pop("local_path", None)
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
                required = (["name", "ip", "user"] if kind == "ssh"
                            else ["name", "host", "remote_path"])
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
                if kind == "ssh":
                    entry.setdefault("port", 22)
                    entry.setdefault("vpn", True)
                if kind == "sshfs" and entry.get("remote_terminal") != "now" and not entry.get("local_path"):
                    entry["local_path"] = os.path.join(os.getcwd(), entry["name"])
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
                    if kind == "sshfs" and not any(
                            isinstance(item, dict) and item.get("name") == result.get("host")
                            for item in data["hosts"]):
                        text_input(screen, "引用的 SSH 配置不存在，按回车继续")
                        continue
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
                    if kind == "sshfs" and result.get("remote_terminal") != "now":
                        os.makedirs(os.path.expanduser(result["local_path"]), exist_ok=True)
                    break
                if action == "delete":
                    if kind == "ssh":
                        host_name = str(entries[selected].get("name", ""))
                        referenced = [item for item in data["mounts"]
                                      if isinstance(item, dict)
                                      and str(item.get("host", "")) == host_name]
                        if referenced:
                            mount_names = ", ".join(
                                str(item.get("name") or "<未命名>") for item in referenced)
                            if not confirm(
                                    screen,
                                    f"被挂载配置引用: {mount_names}；是否同时删除"):
                                text_input(screen, "已取消删除，按回车继续")
                                continue
                            data["mounts"] = [item for item in data["mounts"]
                                              if not (isinstance(item, dict)
                                                      and str(item.get("host", "")) == host_name)]
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
