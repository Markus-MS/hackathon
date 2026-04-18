# Docker Solver Module

This module builds the local container image used by https://ctfarena.live/ solver runs.

```sh
./modules/docker-solver/build_image.sh
```

The image tag defaults to `ctfarena-solver:local`. Override it with:

```sh
CTF_ARENA_SOLVER_IMAGE=registry.example.com/ctfarena-solver:dev ./modules/docker-solver/build_image.sh
```

## Authentication

Do not bake credentials into the image. Inject them at `docker run` time with read-only mounts or environment variables.

### Codex

Codex supports both ChatGPT-account auth and API-key auth.

- For ChatGPT auth, log in on the host and mount `~/.codex/auth.json` into the container.
- For API auth in this image, passing `OPENAI_API_KEY` alone is not enough for the interactive CLI. Import it into Codex's auth store with `codex login --with-api-key`.
- If `OPENAI_API_KEY` is set, it can take precedence over the saved ChatGPT session. If you want ChatGPT-plan auth, do not set `OPENAI_API_KEY`.

Example:

```sh
docker run --rm -it \
  -v "$HOME/.codex:/root/.codex:ro" \
  ctfarena-solver:local codex
```

Or with API auth:

```sh
docker run --rm -it \
  -e OPENAI_API_KEY \
  ctfarena-solver:local \
  bash -lc 'printenv OPENAI_API_KEY | codex login --with-api-key && exec codex'
```

To persist the Codex login across runs and avoid repeating the import step every time:

```sh
docker run --rm -it \
  -e OPENAI_API_KEY \
  -v "$HOME/.codex:/root/.codex" \
  ctfarena-solver:local \
  bash -lc 'if ! codex login status >/dev/null 2>&1; then printenv OPENAI_API_KEY | codex login --with-api-key >/dev/null; fi; exec codex'
```

For a non-interactive Codex run, use `codex exec`:

```sh
docker run --rm -it \
  -e OPENAI_API_KEY \
  -v "$HOME/.codex:/root/.codex" \
  ctfarena-solver:local \
  bash -lc 'if ! codex login status >/dev/null 2>&1; then printenv OPENAI_API_KEY | codex login --with-api-key >/dev/null; fi; exec codex exec "say hello"'
```

### Claude Code

Claude Code supports both Claude subscription OAuth credentials and API-key auth.

- For Claude subscription auth, log in on the host and mount `~/.claude/.credentials.json` into the container.
- For API auth, pass `ANTHROPIC_API_KEY`.
- If `ANTHROPIC_API_KEY` is set, Claude Code uses that instead of the saved Claude subscription credentials.

Example:

```sh
docker run --rm -it \
  -v "$HOME/.claude:/root/.claude:ro" \
  ctfarena-solver:local claude
```

Or with API auth:

```sh
docker run --rm -it \
  -e ANTHROPIC_API_KEY \
  ctfarena-solver:local claude
```

### OpenCode

OpenCode can use stored provider credentials or provider API keys.

- To reuse saved OpenCode credentials, mount `~/.local/share/opencode/auth.json` into the container.
- To use provider API keys, pass env vars such as `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

Example:

```sh
docker run --rm -it \
  -v "$HOME/.local/share/opencode:/root/.local/share/opencode:ro" \
  ctfarena-solver:local opencode
```

### Combined Example

This mounts all three credential stores and also forwards OpenAI and Anthropic API keys if they are set on the host:

```sh
docker run --rm -it \
  -v "$HOME/.codex:/root/.codex:ro" \
  -v "$HOME/.claude:/root/.claude:ro" \
  -v "$HOME/.local/share/opencode:/root/.local/share/opencode:ro" \
  -e OPENAI_API_KEY \
  -e ANTHROPIC_API_KEY \
  ctfarena-solver:local
```

### Notes

- Keep credential mounts read-only.
- Prefer mounts for ChatGPT and Claude subscription logins.
- Prefer environment variables for API-key-based automation.
- If this container is used as a backend or service, API keys are the safer choice than browser login state.
