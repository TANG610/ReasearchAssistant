#!/usr/bin/env python3
"""Listen to Lark messages and trigger the local 3DGS knowledge workflow."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVENT_KEY = "im.message.receive_v1"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def config_value(config: dict[str, Any], key: str, default: Any) -> Any:
    listener = ((config.get("lark") or {}).get("listener") or {})
    return listener.get(key, default)


def normalize_content(content: str, prefix: str) -> str:
    text = re.sub(r"\s+", " ", content or "").strip()
    at_prefix = re.compile(r"^@\S+\s+")
    text = at_prefix.sub("", text).strip()
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix) :].strip()
    return ""


def latest_report(vault: Path) -> Path | None:
    reports = sorted((vault / "Reports").glob("*3DGS-reading-report.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def report_excerpt(vault: Path, max_chars: int = 3000) -> str:
    path = latest_report(vault)
    if not path:
        return "还没有报告。"
    text = path.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("# ") or line.startswith("### ") or line.startswith("- 年份/会议") or line.startswith("- 标签") or line.startswith("- 短评") or line.startswith("- 链接"):
            lines.append(line)
    message = "\n".join(lines) or text
    if len(message) > max_chars:
        message = message[: max_chars - 20] + "\n...(已截断)"
    return message


def lark_cli_command(args: list[str]) -> list[str]:
    executable = shutil.which("lark-cli") or "lark-cli"
    if os.name == "nt" and executable.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable] + args
    return [executable] + args


def run_python_kb(vault: Path, args: list[str], timeout: int) -> tuple[int, str]:
    cmd = [sys.executable, str(vault / "Scripts" / "kb.py"), "--vault", str(vault)] + args
    result = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout, check=False)
    output = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
    return result.returncode, output


def send_reply(chat_id: str, markdown: str, identity: str, dry_run: bool) -> int:
    cmd = lark_cli_command([
        "im",
        "+messages-send",
        "--as",
        identity,
        "--chat-id",
        chat_id,
        "--markdown",
        markdown,
    ])
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def help_text(prefix: str) -> str:
    return (
        f"可用命令：\n"
        f"- `{prefix} ping`：测试监听是否在线\n"
        f"- `{prefix} run [query]`：检索、入库、生成报告\n"
        f"- `{prefix} search [query]`：只检索候选论文\n"
        f"- `{prefix} ingest`：把候选论文写入 Obsidian\n"
        f"- `{prefix} report`：生成阅读报告\n"
        f"- `{prefix} help`：查看帮助\n"
    )


def handle_command(event: dict[str, Any], vault: Path, config: dict[str, Any], args: argparse.Namespace) -> None:
    lark = config.get("lark") or {}
    listener_identity = config_value(config, "identity", args.identity)
    prefix = config_value(config, "command_prefix", args.prefix)
    allowed_chat_ids = set(config_value(config, "allowed_chat_ids", []) or [])
    chat_id = event.get("chat_id", "")
    content = event.get("content", "")
    event_id = event.get("event_id", "")

    if allowed_chat_ids and chat_id not in allowed_chat_ids:
        print(f"skip event={event_id}: chat_id not allowed")
        return

    command_line = normalize_content(content, prefix)
    if not command_line:
        return

    parts = command_line.split()
    command = parts[0].lower() if parts else "help"
    query = " ".join(parts[1:]).strip() or "3d-scene-editing"
    print(f"command event={event_id} chat={chat_id} command={command} query={query}")

    if command in {"help", "?"}:
        reply = help_text(prefix)
    elif command == "ping":
        reply = "3DGS 知识库监听在线。"
    elif command == "search":
        code, output = run_python_kb(vault, ["search", "--query", query, "--limit", str(args.limit)], args.timeout)
        reply = f"检索完成，退出码：{code}\n\n```text\n{output[-2500:]}\n```"
    elif command == "ingest":
        code, output = run_python_kb(vault, ["ingest"], args.timeout)
        reply = f"入库完成，退出码：{code}\n\n```text\n{output[-2500:]}\n```"
    elif command == "report":
        code, output = run_python_kb(vault, ["report"], args.timeout)
        reply = f"报告生成完成，退出码：{code}\n\n{report_excerpt(vault)}\n\n```text\n{output[-1200:]}\n```"
    elif command == "run":
        code, output = run_python_kb(vault, ["run", "--query", query, "--limit", str(args.limit)], args.timeout)
        reply = f"完整流程执行完成，退出码：{code}\n\n{report_excerpt(vault)}\n\n```text\n{output[-1200:]}\n```"
    else:
        reply = f"不认识这个命令：`{command}`\n\n{help_text(prefix)}"

    if args.print_only:
        print(f"reply to {chat_id}:\n{reply}")
        return
    identity = config_value(config, "reply_identity", listener_identity)
    send_reply(chat_id, reply, identity=identity, dry_run=args.dry_run)


def forward_stderr(stream: Any, ready: threading.Event) -> None:
    for line in iter(stream.readline, ""):
        text = line.rstrip()
        if text:
            print(text, file=sys.stderr)
        if "[event] ready" in text:
            ready.set()


def listen(args: argparse.Namespace) -> int:
    vault = Path(args.vault).resolve()
    config = load_json(vault / "config.local.json", {})
    identity = config_value(config, "identity", args.identity)

    cmd = lark_cli_command([
        "event",
        "consume",
        EVENT_KEY,
        "--as",
        identity,
    ])
    if args.max_events:
        cmd.extend(["--max-events", str(args.max_events)])
    if args.event_timeout:
        cmd.extend(["--timeout", args.event_timeout])

    print("开始监听飞书消息：", " ".join(cmd))
    print(f"命令前缀：{config_value(config, 'command_prefix', args.prefix)}")
    process = subprocess.Popen(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    ready = threading.Event()
    stderr_thread = threading.Thread(target=forward_stderr, args=(process.stderr, ready), daemon=True)
    stderr_thread.start()

    if not ready.wait(timeout=30):
        print("监听器 30 秒内没有 ready，继续读取输出；如果一直没有事件，请检查飞书事件订阅和 bot 权限。", file=sys.stderr)

    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"无法解析事件：{line}", file=sys.stderr)
                continue
            handle_command(event, vault, config, args)
    except KeyboardInterrupt:
        print("收到 Ctrl+C，正在停止监听。")
    finally:
        if process.stdin:
            process.stdin.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return process.returncode or 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Lark command listener for the 3DGS knowledge base")
    parser.add_argument("--vault", default=str(ROOT), help="Obsidian vault path")
    parser.add_argument("--identity", default="bot", choices=["bot", "user", "auto"], help="identity for event consume")
    parser.add_argument("--prefix", default="/3dgs", help="command prefix")
    parser.add_argument("--limit", type=int, default=10, help="paper limit per source for run/search commands")
    parser.add_argument("--timeout", type=int, default=300, help="timeout for each kb command")
    parser.add_argument("--max-events", type=int, default=0, help="stop after N events; 0 means unlimited")
    parser.add_argument("--event-timeout", default="", help="event consumer timeout, such as 10m")
    parser.add_argument("--print-only", action="store_true", help="print replies locally instead of sending to Lark")
    parser.add_argument("--dry-run", action="store_true", help="call lark message send with --dry-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return listen(args)


if __name__ == "__main__":
    raise SystemExit(main())
