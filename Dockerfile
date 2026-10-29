# Measurement and experiment environment: quality tools, tests, resource benchmarks,
# the LMS application stack and Claude Code. Setup and usage: docs/environment.md
#
# Python: 3.14 (decision of 29 October), pinned to the patch version of the first
# successful build (check-tools, 29 October 2026).
ARG PYTHON_VERSION=3.14.10
ARG NODE_VERSION=22

# --- Stage 1: Node.js + jscpd (duplication detector) ---
FROM node:${NODE_VERSION}-bookworm-slim AS node
ARG JSCPD_VERSION=5.4.2
RUN npm install -g "jscpd${JSCPD_VERSION:+@$JSCPD_VERSION}" && npm cache clean --force

# --- Stage 2: Python tools, LMS stack, Claude Code ---
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git: repository access; procps: ps/top; curl + ca-certificates: Claude Code installer
RUN apt-get update \
 && apt-get install -y --no-install-recommends git procps curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Node.js runtime and jscpd from stage 1
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN BIN=$(node -p "const p=require('/usr/local/lib/node_modules/jscpd/package.json'); typeof p.bin==='string' ? p.bin : (p.bin.jscpd || Object.values(p.bin)[0])") \
 && ln -s "/usr/local/lib/node_modules/jscpd/$BIN" /usr/local/bin/jscpd \
 && jscpd --version

# Claude Code (native installer), pinned to the version of the first successful build
# (`claude --version`, 29 October 2026) so every run uses the same version.
# Updates are switched off only AFTER the install: the installer skips its final setup
# step (the `claude` launcher) when updates are disabled.
ARG CLAUDE_CODE_VERSION=2.1.308
RUN curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_CODE_VERSION" \
 && BIN=/root/.local/bin/claude \
 && if [ ! -x "$BIN" ]; then BIN=$(ls -1d /root/.local/share/claude/versions/* | sort -V | tail -n 1); fi \
 && ln -sf "$BIN" /usr/local/bin/claude \
 && claude --version \
 && rm -rf /root/.claude /root/.claude.json
# Claude Code must not change version during the project
ENV DISABLE_AUTOUPDATER=1 \
    DISABLE_UPDATES=1

# Python packages. If docker/requirements.lock contains pinned versions it is used;
# otherwise docker/requirements.in (first build). See docs/environment.md, "Pinning versions".
COPY docker/requirements.in docker/requirements.lock /tmp/req/
RUN if grep -qE '^[A-Za-z0-9]' /tmp/req/requirements.lock; then \
        pip install -r /tmp/req/requirements.lock; \
    else \
        pip install -r /tmp/req/requirements.in; \
    fi \
 && rm -rf /tmp/req

COPY docker/check-tools.sh /usr/local/bin/check-tools
COPY docker/check-claude.sh /usr/local/bin/check-claude
RUN chmod +x /usr/local/bin/check-tools /usr/local/bin/check-claude

# The repository is mounted here at run time (docker run -v ...:/work)
WORKDIR /work
CMD ["bash"]
