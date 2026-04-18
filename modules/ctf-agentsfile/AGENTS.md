# AGENTS.md

Rules for AI agents solving CTF challenges in this environment.

## 1. Global Rules

- Solve the challenge as fast as possible.
- Do not emit output about the agent's thinking process while solving.
- Do not stop to describe internal reasoning; continue solving.

## 2. Python Script Rules

All generated Python scripts must:

- start with `#!/usr/bin/env -S uv run --script`
- include a `/// script` header
- declare all non-stdlib imports in `dependencies`
- be directly executable as `./script` after `chmod +x`

Prefer UV-managed dependencies instead of assuming global Python packages.

Example:

```python
#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "pwntools",
# ]
# ///

def main():
    print("Code")

if __name__ == "__main__":
    main()
```

## 3. Networking

- For remote TCP/UDP services, prefer `pwntools` over manual `socket` code.
- Remote exploit scripts should accept target parameters as arguments, preferably `--host/--port`, and ideally also `HOST=... PORT=...`.
- For HTTP(S), use Python `requests`.

## 4. Flag and Archive Handling

- Main goal: obtain the flag.
- Also search broadly for `name{...}`-style flag strings.
- Common flag locations include files like `flag.txt` or `/flag.txt`, stdout, binaries, memory, or encoded artifacts.
- Automatically extract archives such as `.tar`, `.tar.gz`, `.tgz`, `.zip`, and `.7z` without asking.
