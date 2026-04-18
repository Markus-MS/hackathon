#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "flask",
#   "flask-sock",
# ]
# ///

import argparse
import errno
import fcntl
import html
import json
import os
import pty
import re
import select
import shlex
import signal
import struct
import termios
import subprocess
import threading
from pathlib import Path

from flask import Flask, Response, send_file
from flask_sock import Sock


app = Flask(__name__)
sock = Sock(app)
MODULE_DIR = Path(__file__).resolve().parent

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

DEFAULT_MODEL_INSTRUCTIONS = (
    "Solve the task with minimal prose. Do not narrate your plan or explain what you are about to do. "
    "Keep assistant text extremely brief. Prefer doing the work and running commands over describing it. "
    "Only write short user-facing text when necessary to clarify a result or blocker."
)
MAX_OUTPUT_LINES = 80
TRUNCATED_HEAD_LINES = 32
TRUNCATED_TAIL_LINES = 20

HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Live Terminal</title>
    <style>
      :root {
        color-scheme: dark;
        --panel: rgba(0, 0, 0, 0.94);
        --border: rgba(255, 255, 255, 0.12);
        --text: #f5f5f5;
        --muted: #a3a3a3;
        --accent: #ffffff;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        color: var(--text);
        background: #ffffff;
      }

      .shell {
        width: min(1320px, calc(100vw - 32px));
        margin: 24px auto;
        padding: 0;
      }

      .compare {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
      }

      .terminal {
        height: min(75vh, 760px);
        padding: 14px;
        border-radius: 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: #000000;
        overflow: hidden;
        font-family: "IBM Plex Mono", "Fira Code", monospace;
        font-size: 15px;
        line-height: 1.45;
        scrollbar-width: none;
        -ms-overflow-style: none;
        box-shadow: 0 22px 80px rgba(0, 0, 0, 0.32);
      }

      .terminal::-webkit-scrollbar {
        display: none;
      }

      .line {
        display: block;
        white-space: pre-wrap;
        word-break: break-word;
      }

      .dim {
        opacity: 0.72;
      }

      .bold {
        font-weight: 700;
      }

      .note {
        color: var(--muted);
      }

      .command {
        color: #7dd3fc;
        background: rgba(59, 130, 246, 0.10);
        border-left: 2px solid rgba(125, 211, 252, 0.65);
        padding-left: 10px;
      }

      .reveal {
        opacity: 0;
        transform: translateY(3px);
        animation: reveal 140ms ease-out forwards;
      }

      @keyframes reveal {
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      .typing-cursor::after {
        content: none;
      }

      .typing-cursor {
        position: relative;
        display: inline;
      }

      .cursor-model-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.5em;
        height: 2.05em;
        margin-left: 0.55em;
        padding: 0 0.78em;
        font-size: 0.68em;
        line-height: 1;
        font-weight: 700;
        letter-spacing: 0.01em;
        color: #0f172a;
        background: rgba(255, 255, 255, 0.96);
        border: 1px solid rgba(255, 255, 255, 0.9);
        border-radius: 999px;
        white-space: nowrap;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.22);
        pointer-events: none;
        vertical-align: middle;
      }

      .cursor-model-pill.claude {
        color: #fff7f4;
        background: #DE7356;
        border-color: #DE7356;
        box-shadow: 0 8px 24px rgba(222, 115, 86, 0.32);
      }

      .cursor-model-pill img {
        width: 1.05em;
        height: 1.05em;
        display: block;
      }

      @media (max-width: 960px) {
        .compare {
          grid-template-columns: 1fr;
        }
      }

    </style>
  </head>
  <body>
    <main class="shell">
      <div class="compare">
        <div class="terminal" id="terminal-codex" aria-live="polite"></div>
        <div class="terminal" id="terminal-claude" aria-live="polite"></div>
      </div>
    </main>

    <script>
      const terminals = {
        codex: createTerminalController(document.getElementById("terminal-codex")),
        claude: createTerminalController(document.getElementById("terminal-claude")),
      };
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${proto}://${location.host}/ws`);
      function createTerminalController(terminalEl) {
        const renderQueue = [];
        let renderActive = false;
        let parkedPill = null;

        function scrollToBottom() {
          terminalEl.scrollTop = terminalEl.scrollHeight;
        }

        function appendHtml(html, animate) {
          terminalEl.insertAdjacentHTML("beforeend", html);
          if (animate) {
            const last = terminalEl.lastElementChild;
            if (last) {
              last.classList.add("reveal");
            }
          }
          scrollToBottom();
        }

        function stripWrapper(html) {
          const match = html.match(/^<span class="([^"]*)">(.*)<\\/span>$/s);
          if (!match) {
            return null;
          }
          return { className: match[1], innerHtml: match[2] };
        }

        function enqueueRender(item) {
          renderQueue.push(item);
          if (!renderActive) {
            drainRenderQueue();
          }
        }

        function drainRenderQueue() {
          if (renderQueue.length === 0) {
            renderActive = false;
            return;
          }
          renderActive = true;
          const { html, mode, animate, delayMs, badge, modelLabel } = renderQueue.shift();

          if (mode !== "type") {
            appendHtml(html, !!animate);
            drainRenderQueue();
            return;
          }

          const wrapped = stripWrapper(html);
          if (!wrapped) {
            appendHtml(html, false);
            drainRenderQueue();
            return;
          }

          const line = document.createElement("span");
          line.className = wrapped.className;
          const container = document.createElement("span");
          container.className = "typing-cursor";
          const textNode = document.createElement("span");
          container.appendChild(textNode);
          line.appendChild(container);

          if (parkedPill) {
            parkedPill.remove();
            parkedPill = null;
          }

          let pill = null;
          if (badge && modelLabel) {
            pill = document.createElement("span");
            pill.className = "cursor-model-pill";
            if (modelLabel === "sonnet4.6") {
              pill.classList.add("claude");
            }
          const icon = document.createElement("img");
          icon.src = badge;
            icon.alt = "";
            icon.setAttribute("aria-hidden", "true");
            const label = document.createElement("span");
            label.textContent = modelLabel;
            pill.appendChild(icon);
            pill.appendChild(label);
            container.appendChild(pill);
          }

          terminalEl.appendChild(line);

          const source = document.createElement("div");
          source.innerHTML = wrapped.innerHtml;
          const text = source.textContent || "";
          let index = 0;

          function tick() {
            if (index >= text.length) {
              container.classList.remove("typing-cursor");
              textNode.textContent = text;
              if (pill) {
                parkedPill = pill;
              }
              scrollToBottom();
              drainRenderQueue();
              return;
            }
            index += 1;
            textNode.textContent = text.slice(0, index);
            scrollToBottom();
            window.setTimeout(tick, delayMs);
          }

          tick();
        }

        return { enqueueRender, scrollToBottom };
      }

      socket.addEventListener("open", () => {});

      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(event.data);
        const terminal = terminals[payload.target];
        if (!terminal) {
          return;
        }
        if (payload.type === "append") {
          if (payload.animate_mode === "type") {
            terminal.enqueueRender({
              html: payload.html,
              mode: "type",
              delayMs: payload.delay_ms || 28,
              badge: payload.badge || "",
              modelLabel: payload.model_label || "",
            });
          } else {
            terminal.enqueueRender({
              html: payload.html,
              mode: "append",
              animate: !!payload.animate,
            });
          }
        }
        terminal.scrollToBottom();
      });

      socket.addEventListener("close", () => {
        terminals.codex.scrollToBottom();
        terminals.claude.scrollToBottom();
      });

      socket.addEventListener("error", () => {});
    </script>
  </body>
</html>
"""


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only browser command output streamer.")
    parser.add_argument("--host", default=os.environ.get("LIVE_TERMINAL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LIVE_TERMINAL_PORT", "10000")))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def resolve_command(args: argparse.Namespace) -> list[str]:
    default = os.environ.get("LIVE_TERMINAL_COMMAND", "ls --color=always")
    command = list(args.command) if args.command else shlex.split(default)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("No command configured.")
    return command


def resolve_prompt(command: list[str]) -> str:
    if not command:
        raise SystemExit("No prompt configured.")
    if command[0] == "codex" and len(command) > 1:
        return " ".join(command[1:])
    if command[0] == "claude" and len(command) > 1:
        return " ".join(command[1:])
    return " ".join(command)


def get_model_instructions() -> str:
    return os.environ.get("LIVE_TERMINAL_MODEL_INSTRUCTIONS", DEFAULT_MODEL_INSTRUCTIONS).strip()


def augment_prompt(prompt: str) -> str:
    instructions = get_model_instructions()
    if not instructions:
        return prompt
    return f"{prompt}\n\nAdditional instructions:\n{instructions}"


def build_compare_commands(prompt: str) -> list[dict[str, object]]:
    augmented = augment_prompt(prompt)
    return [
        {
            "target": "codex",
            "command": [
                "codex",
                "exec",
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                augmented,
            ],
            "mode": "codex_json",
            "badge": "/assets/openai.png",
            "model_label": "gpt5.4",
        },
        {
            "target": "claude",
            "command": [
                "claude",
                "-p",
                "--verbose",
                "--output-format",
                "stream-json",
                "--dangerously-skip-permissions",
                augmented,
            ],
            "mode": "claude_json",
            "badge": "/assets/claude.png",
            "model_label": "sonnet4.6",
        },
    ]


def set_winsize(fd: int, rows: int, cols: int) -> None:
    payload = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, payload)


def spawn_pty_process(command: list[str]) -> tuple[int, int]:
    env = os.environ.copy()
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("COLORTERM", "truecolor")
    env.setdefault("CLICOLOR_FORCE", "1")
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(command[0], command, env)
    set_winsize(fd, 32, 120)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    return pid, fd


def spawn_pipe_process(command: list[str]) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.setdefault("TERM", "xterm-256color")
    env.setdefault("COLORTERM", "truecolor")
    env.setdefault("CLICOLOR_FORCE", "1")
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        shell=False,
        env=env,
    )


def render_line(text: str, extra_class: str = "") -> str:
    class_name = "line"
    if extra_class:
        class_name += f" {extra_class}"
    return f'<span class="{class_name}">{html.escape(text)}</span>'


def render_text_block(text: str, extra_class: str = "") -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    return [render_line(line, extra_class) for line in lines]


def truncate_output_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if len(lines) <= MAX_OUTPUT_LINES:
        return normalized

    omitted = len(lines) - TRUNCATED_HEAD_LINES - TRUNCATED_TAIL_LINES
    middle = f"... [{omitted} lines omitted] ..."
    kept = lines[:TRUNCATED_HEAD_LINES] + [middle] + lines[-TRUNCATED_TAIL_LINES:]
    return "\n".join(kept)


def send_append(
    ws,
    target: str,
    html_content: str,
    *,
    animate: bool = False,
    animate_mode: str | None = None,
    delay_ms: int | None = None,
    badge: str | None = None,
    model_label: str | None = None,
) -> None:
    payload: dict[str, object] = {"type": "append", "target": target, "html": html_content, "animate": animate}
    if animate_mode is not None:
        payload["animate_mode"] = animate_mode
    if delay_ms is not None:
        payload["delay_ms"] = delay_ms
    if badge is not None:
        payload["badge"] = badge
    if model_label is not None:
        payload["model_label"] = model_label
    lock = getattr(ws, "_send_lock", None)
    if lock is not None:
        with lock:
            ws.send(json.dumps(payload))
    else:
        ws.send(json.dumps(payload))


def send_status(
    ws,
    target: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    commands: int | None = None,
    messages: int | None = None,
) -> None:
    payload: dict[str, object] = {"type": "status", "target": target}
    if status is not None:
        payload["status"] = status
    if phase is not None:
        payload["phase"] = phase
    metrics = {}
    if commands is not None:
        metrics["commands"] = commands
    if messages is not None:
        metrics["messages"] = messages
    if metrics:
        payload["metrics"] = metrics
    lock = getattr(ws, "_send_lock", None)
    if lock is not None:
        with lock:
            ws.send(json.dumps(payload))
    else:
        ws.send(json.dumps(payload))


def codex_event_to_html(payload: dict) -> list[tuple[str, bool]]:
    chunks: list[tuple[str, bool]] = []
    event_type = payload.get("type")
    item = payload.get("item", {})

    if event_type == "item.completed" and item.get("type") == "agent_message":
        text = item.get("text", "")
        if text:
            chunks.extend((line, True) for line in render_text_block(text))
    elif event_type == "item.started" and item.get("type") == "command_execution":
        command = item.get("command", "").strip()
        if command:
            chunks.append((render_line(f"$ {command}", "command"), True))
    elif event_type == "item.completed" and item.get("type") == "command_execution":
        output = item.get("aggregated_output", "")
        if output:
            chunks.append((ansi_to_html_lines(truncate_output_text(output)), False))

    return chunks


def claude_event_to_html(payload: dict) -> list[tuple[str, bool]]:
    chunks: list[tuple[str, bool]] = []
    event_type = payload.get("type")

    if event_type == "assistant":
        message = payload.get("message", {})
        for block in message.get("content", []):
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    chunks.extend((line, True) for line in render_text_block(text))
            elif block.get("type") == "tool_use":
                tool_name = block.get("name", "")
                tool_input = block.get("input", {})
                command = tool_input.get("command", "").strip()
                if tool_name == "Bash" and command:
                    chunks.append((render_line(f"$ {command}", "command"), True))
    elif event_type == "result":
        result = payload.get("result", "")
        if result:
            chunks.extend((line, True) for line in render_text_block(result))
    elif event_type == "user":
        message = payload.get("message", {})
        for block in message.get("content", []):
            if block.get("type") == "tool_result":
                content = block.get("content", "")
                if content:
                    chunks.append((ansi_to_html_lines(truncate_output_text(content)), False))

    return chunks


def stream_json_command(
    ws,
    target: str,
    command: list[str],
    mode: str,
    badge: str | None,
    model_label: str | None,
) -> int:
    process = spawn_pipe_process(command)
    assert process.stdout is not None
    parser = codex_event_to_html if mode == "codex_json" else claude_event_to_html
    command_count = 0
    message_count = 0
    send_status(ws, target, status="Streaming", phase="starting", commands=0, messages=0)
    try:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                cleaned = sanitize_ansi(line)
                if cleaned and cleaned != "Reading additional input from stdin...":
                    send_append(ws, target, render_line(cleaned, "note"))
                continue
            if mode == "codex_json":
                event_type = payload.get("type")
                item = payload.get("item", {})
                if event_type == "turn.started":
                    send_status(ws, target, status="Thinking", phase="thinking", commands=command_count, messages=message_count)
                elif event_type == "item.started" and item.get("type") == "command_execution":
                    command_count += 1
                    send_status(ws, target, status="Running command", phase="tool call", commands=command_count, messages=message_count)
                elif event_type == "item.completed" and item.get("type") == "agent_message":
                    message_count += 1
                    send_status(ws, target, status="Reasoning", phase="assistant", commands=command_count, messages=message_count)
                elif event_type == "turn.completed":
                    send_status(ws, target, status="Turn complete", phase="done", commands=command_count, messages=message_count)
            elif mode == "claude_json":
                event_type = payload.get("type")
                if event_type == "assistant":
                    message_count += 1
                    send_status(ws, target, status="Reasoning", phase="assistant", commands=command_count, messages=message_count)
                elif event_type == "result":
                    send_status(ws, target, status="Turn complete", phase="done", commands=command_count, messages=message_count)
            for chunk, should_type in parser(payload):
                if should_type:
                    send_append(
                        ws,
                        target,
                        chunk,
                        animate_mode="type",
                        delay_ms=32,
                        badge=badge,
                        model_label=model_label,
                    )
                else:
                    send_append(ws, target, chunk)
    finally:
        process.stdout.close()
    return process.wait()


@app.get("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.get("/assets/codex-color.png")
def codex_badge():
    return send_file(MODULE_DIR / "codex-color.png", mimetype="image/png")


@app.get("/assets/openai.png")
def openai_badge():
    return send_file(MODULE_DIR / "openai.png", mimetype="image/png")


@app.get("/assets/claude.png")
def claude_badge():
    return send_file(MODULE_DIR / "claude.png", mimetype="image/png")


@sock.route("/ws")
def terminal_socket(ws):
    ws._send_lock = threading.Lock()
    prompt = app.config["LIVE_TERMINAL_PROMPT"]
    compare_runs = build_compare_commands(prompt)
    threads: list[threading.Thread] = []

    for run in compare_runs:
        def runner(run_config=run):
            stream_json_command(
                ws,
                run_config["target"],
                run_config["command"],
                run_config["mode"],
                run_config["badge"],
                run_config["model_label"],
            )
            send_status(ws, run_config["target"], status="Finished", phase="done")

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


def main():
    args = parse_args()
    app.config["LIVE_TERMINAL_HOST"] = args.host
    app.config["LIVE_TERMINAL_PORT"] = args.port
    app.config["LIVE_TERMINAL_PROMPT"] = resolve_prompt(resolve_command(args))
    app.run(
        host=app.config["LIVE_TERMINAL_HOST"],
        port=app.config["LIVE_TERMINAL_PORT"],
        threaded=True,
    )


if __name__ == "__main__":
    main()
