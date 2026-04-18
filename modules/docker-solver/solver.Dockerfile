FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        binutils \
        ca-certificates \
        curl \
        file \
        gcc \
        gdb \
        git \
        iputils-ping \
        jq \
        libcap2-bin \
        make \
        netcat-openbsd \
        openssl \
        procps \
        python3-pip \
        socat \
        strace \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    [ "${arch}" = "amd64" ] || { echo "Unsupported architecture: ${arch}" >&2; exit 1; }; \
    codex_asset="codex-x86_64-unknown-linux-musl.tar.gz"; \
    claude_platform="linux-x64"; \
    opencode_asset="opencode-linux-x64-baseline.tar.gz"; \
    tmpdir="$(mktemp -d)"; \
    trap 'rm -rf "${tmpdir}"' EXIT; \
    \
    curl -fsSL "https://github.com/openai/codex/releases/latest/download/${codex_asset}" -o "${tmpdir}/codex.tar.gz"; \
    tar -xzf "${tmpdir}/codex.tar.gz" -C "${tmpdir}"; \
    install -m 0755 "${tmpdir}/$(tar -tzf "${tmpdir}/codex.tar.gz" | head -n1)" /usr/local/bin/codex; \
    \
    claude_version="$(curl -fsSL https://downloads.claude.ai/claude-code-releases/latest)"; \
    claude_manifest="$(curl -fsSL "https://downloads.claude.ai/claude-code-releases/${claude_version}/manifest.json")"; \
    claude_checksum="$(printf '%s' "${claude_manifest}" | jq -r ".platforms[\"${claude_platform}\"].checksum // empty")"; \
    [ -n "${claude_checksum}" ]; \
    curl -fsSL "https://downloads.claude.ai/claude-code-releases/${claude_version}/${claude_platform}/claude" -o "${tmpdir}/claude"; \
    printf '%s  %s\n' "${claude_checksum}" "${tmpdir}/claude" | sha256sum -c -; \
    install -m 0755 "${tmpdir}/claude" /usr/local/bin/claude; \
    \
    curl -fsSL "https://github.com/anomalyco/opencode/releases/latest/download/${opencode_asset}" -o "${tmpdir}/opencode.tar.gz"; \
    tar -xzf "${tmpdir}/opencode.tar.gz" -C "${tmpdir}"; \
    install -m 0755 "${tmpdir}/$(tar -tzf "${tmpdir}/opencode.tar.gz" | head -n1)" /usr/local/bin/opencode; \
    \
    codex --version; \
    claude --version; \
    opencode --version

WORKDIR /workspace
