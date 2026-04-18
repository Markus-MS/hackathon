from __future__ import annotations

import html
import json
import re
import threading
from dataclasses import dataclass, field

from flask import current_app
from flask_sock import Sock


sock = Sock()

OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
CSI_NON_SGR_RE = re.compile(r"\x1b\[(?![0-9;]*m)[0-?]*[ -/]*[@-~]")
ANSI_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

FG_COLORS = {
    30: "#1f2937",
    31: "#ef4444",
    32: "#22c55e",
    33: "#eab308",
    34: "#60a5fa",
    35: "#f472b6",
    36: "#22d3ee",
    37: "#e5e7eb",
    90: "#6b7280",
    91: "#f87171",
    92: "#4ade80",
    93: "#facc15",
    94: "#93c5fd",
    95: "#f9a8d4",
    96: "#67e8f9",
    97: "#f9fafb",
}

BG_COLORS = {
    40: "#111827",
    41: "#7f1d1d",
    42: "#14532d",
    43: "#713f12",
    44: "#1e3a8a",
    45: "#701a75",
    46: "#155e75",
    47: "#d1d5db",
    100: "#374151",
    101: "#991b1b",
    102: "#166534",
    103: "#854d0e",
    104: "#1d4ed8",
    105: "#86198f",
    106: "#0e7490",
    107: "#f9fafb",
}

MAX_OUTPUT_LINES = 80
TRUNCATED_HEAD_LINES = 32
TRUNCATED_TAIL_LINES = 20
MAX_HISTORY_ITEMS = 400


def init_app(app) -> None:
    sock.init_app(app)

    @sock.route("/ws/challenge-runs/<int:challenge_run_id>")
    def challenge_run_socket(ws, challenge_run_id: int):
        ws._send_lock = threading.Lock()
        manager: LiveTerminalManager = current_app.extensions["live_terminal_manager"]
        manager.attach(challenge_run_id, ws)
        try:
            while True:
                message = ws.receive()
                if message is None:
                    break
        finally:
            manager.detach(challenge_run_id, ws)


def sanitize_ansi(data: str) -> str:
    data = data.replace("\r\n", "\n").replace("\r", "\n")
    data = OSC_RE.sub("", data)
    return CSI_NON_SGR_RE.sub("", data)


def style_to_span(text: str, styles: dict[str, str], classes: set[str]) -> str:
    if not text:
        return ""
    escaped = html.escape(text)
    attrs = []
    if classes:
        attrs.append(f'class="{" ".join(sorted(classes))}"')
    if styles:
        style = "; ".join(f"{key}: {value}" for key, value in styles.items())
        attrs.append(f'style="{style}"')
    if attrs:
        return f"<span {' '.join(attrs)}>{escaped}</span>"
    return escaped


def ansi_to_html_lines(data: str) -> str:
    data = sanitize_ansi(data)
    styles: dict[str, str] = {}
    classes: set[str] = set()
    chunks: list[str] = []
    pos = 0

    for match in ANSI_SGR_RE.finditer(data):
        chunks.append(style_to_span(data[pos:match.start()], styles, classes))
        codes = [int(part) for part in match.group(1).split(";") if part] or [0]
        for code in codes:
            if code == 0:
                styles.clear()
                classes.clear()
            elif code == 1:
                classes.add("bold")
            elif code == 2:
                classes.add("dim")
            elif code == 22:
                classes.discard("bold")
                classes.discard("dim")
            elif code == 39:
                styles.pop("color", None)
            elif code == 49:
                styles.pop("background-color", None)
            elif code in FG_COLORS:
                styles["color"] = FG_COLORS[code]
            elif code in BG_COLORS:
                styles["background-color"] = BG_COLORS[code]
        pos = match.end()

    chunks.append(style_to_span(data[pos:], styles, classes))
    rendered = "".join(chunks)
    lines = rendered.split("\n")
    return "".join(f'<span class="line">{line}</span>' for line in lines if line or len(lines) == 1)


def render_line(text: str, extra_class: str = "") -> str:
    class_name = "line"
    if extra_class:
        class_name += f" {extra_class}"
    return f'<span class="{class_name}">{html.escape(text)}</span>'


def render_text_block(text: str, extra_class: str = "") -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    return [render_line(line, extra_class) for line in lines]


def _error_text(payload: dict) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if message:
            return str(message)
    if isinstance(error, str) and error:
        return error
    message = payload.get("message")
    if message:
        return str(message)
    return ""


def _is_ignorable_text(text: str) -> bool:
    normalized = sanitize_ansi(str(text or "")).strip().lower()
    return "reading additional input from stdin" in normalized


def truncate_output_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if len(lines) <= MAX_OUTPUT_LINES:
        return normalized

    omitted = len(lines) - TRUNCATED_HEAD_LINES - TRUNCATED_TAIL_LINES
    middle = f"... [{omitted} lines omitted] ..."
    kept = lines[:TRUNCATED_HEAD_LINES] + [middle] + lines[-TRUNCATED_TAIL_LINES:]
    return "\n".join(kept)


def _extract_text_from_event(event: object) -> str:
    if isinstance(event, str):
        return event
    if isinstance(event, list):
        return " ".join(_extract_text_from_event(v) for v in event)
    if isinstance(event, dict):
        return " ".join(_extract_text_from_event(v) for v in event.values())
    return ""


def codex_event_to_html(payload: dict) -> list[tuple[str, bool]]:
    chunks: list[tuple[str, bool]] = []
    event_type = payload.get("type")
    item = payload.get("item", {})

    if event_type == "item.completed" and item.get("type") == "agent_message":
        text = item.get("text", "")
        if text and not _is_ignorable_text(text):
            chunks.extend((line, True) for line in render_text_block(text))
    elif event_type == "item.started" and item.get("type") == "command_execution":
        command = item.get("command", "").strip()
        if command:
            chunks.append((render_line(f"$ {command}", "command"), True))
    elif event_type == "item.completed" and item.get("type") == "command_execution":
        output = item.get("aggregated_output", "")
        if output:
            chunks.append((ansi_to_html_lines(truncate_output_text(output)), False))
    elif event_type == "error":
        text = _error_text(payload)
        if text and not _is_ignorable_text(text):
            chunks.extend((line, False) for line in render_text_block(text, "error"))
    elif event_type == "turn.failed":
        text = _error_text(payload)
        if text and not _is_ignorable_text(text):
            chunks.extend((line, False) for line in render_text_block(text, "error"))
    elif event_type == "thread.started":
        thread_id = payload.get("thread_id")
        if thread_id:
            chunks.append((render_line(f"thread {thread_id}", "note"), False))

    return chunks


def claude_event_to_html(payload: dict) -> list[tuple[str, bool]]:
    chunks: list[tuple[str, bool]] = []
    event_type = payload.get("type")

    if event_type == "assistant":
        message = payload.get("message", {})
        for block in message.get("content", []):
            if block.get("type") == "text":
                text = block.get("text", "")
                if text and not _is_ignorable_text(text):
                    chunks.extend((line, True) for line in render_text_block(text))
            elif block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                tool_input = block.get("input", {})
                command = tool_input.get("command", "").strip()
                if tool_name == "Bash" and command:
                    chunks.append((render_line(f"$ {command}", "command"), True))
    elif event_type == "result":
        result = payload.get("result", "")
        if result and not _is_ignorable_text(result):
            chunks.extend((line, True) for line in render_text_block(result))
    elif event_type == "user":
        message = payload.get("message", {})
        for block in message.get("content", []):
            if block.get("type") == "tool_result":
                content = block.get("content", "")
                if content and not _is_ignorable_text(content):
                    chunks.append((ansi_to_html_lines(truncate_output_text(content)), False))
    elif event_type == "error":
        text = _error_text(payload)
        if text and not _is_ignorable_text(text):
            chunks.extend((line, False) for line in render_text_block(text, "error"))

    return chunks


@dataclass
class LiveStreamState:
    history: list[dict[str, object]] = field(default_factory=list)
    listeners: set[object] = field(default_factory=set)
    active: bool = False


class LiveTerminalManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: dict[int, LiveStreamState] = {}

    def attach(self, challenge_run_id: int, ws) -> None:
        with self._lock:
            state = self._streams.setdefault(challenge_run_id, LiveStreamState())
            snapshot = list(state.history)
            state.listeners.add(ws)
        for payload in snapshot:
            self._send(ws, payload)

    def detach(self, challenge_run_id: int, ws) -> None:
        with self._lock:
            state = self._streams.get(challenge_run_id)
            if state is None:
                return
            state.listeners.discard(ws)
            if not state.listeners and not state.active and not state.history:
                self._streams.pop(challenge_run_id, None)

    def start(self, challenge_run_id: int) -> None:
        with self._lock:
            state = self._streams.setdefault(challenge_run_id, LiveStreamState())
            state.active = True
            state.history.clear()

    def finish(self, challenge_run_id: int) -> None:
        with self._lock:
            state = self._streams.setdefault(challenge_run_id, LiveStreamState())
            state.active = False

    def append(
        self,
        challenge_run_id: int,
        html_content: str,
        *,
        animate_mode: str | None = None,
        delay_ms: int | None = None,
        model_label: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "type": "append",
            "html": html_content,
        }
        if animate_mode is not None:
            payload["animate_mode"] = animate_mode
        if delay_ms is not None:
            payload["delay_ms"] = delay_ms
        if model_label is not None:
            payload["model_label"] = model_label
        self._broadcast(challenge_run_id, payload)

    def status(self, challenge_run_id: int, *, status: str, phase: str, commands: int, messages: int) -> None:
        payload = {
            "type": "status",
            "status": status,
            "phase": phase,
            "metrics": {
                "commands": commands,
                "messages": messages,
            },
        }
        self._broadcast(challenge_run_id, payload)

    def _broadcast(self, challenge_run_id: int, payload: dict[str, object]) -> None:
        with self._lock:
            state = self._streams.setdefault(challenge_run_id, LiveStreamState())
            state.history.append(payload)
            if len(state.history) > MAX_HISTORY_ITEMS:
                state.history = state.history[-MAX_HISTORY_ITEMS:]
            listeners = list(state.listeners)
        for ws in listeners:
            self._send(ws, payload)

    @staticmethod
    def _send(ws, payload: dict[str, object]) -> None:
        lock = getattr(ws, "_send_lock", None)
        try:
            if lock is not None:
                with lock:
                    ws.send(json.dumps(payload))
            else:
                ws.send(json.dumps(payload))
        except Exception:
            return
