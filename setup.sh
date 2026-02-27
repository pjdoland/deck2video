#!/usr/bin/env bash
#
# Usage: source setup.sh
#
# Must be sourced (not executed) so it can activate the venv in your shell.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: This script must be sourced, not executed."
    echo "  Run:  source setup.sh"
    exit 1
fi

set -euo pipefail

VENV_DIR=".venv"
PYTHON="python3.11"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()  { printf '  ✓ %s\n' "$*"; }
warn()  { printf '  ⚠ %s\n' "$*" >&2; }
fail()  { printf '  ✗ %s\n' "$*" >&2; exit 1; }

check_cmd() {
    command -v "$1" &>/dev/null
}

# ── System dependencies ─────────────────────────────────────────────────────

echo "Checking system dependencies…"

check_cmd "$PYTHON" || fail "$PYTHON not found. Install it with: brew install python@3.11"
info "$PYTHON ($($PYTHON --version 2>&1))"

check_cmd ffmpeg   || fail "ffmpeg not found. Install it with: brew install ffmpeg"
info "ffmpeg"

check_cmd ffprobe  || fail "ffprobe not found (should come with ffmpeg)"
info "ffprobe"

if check_cmd marp; then
    info "marp-cli (global)"
elif check_cmd npx; then
    info "npx (will use npx @marp-team/marp-cli)"
else
    fail "Neither marp nor npx found. Install Node.js or run: npm install -g @marp-team/marp-cli"
fi

# ── Slidev support (optional) ──────────────────────────────────────────────

INSTALL_SLIDEV=false
INSTALL_PLAYWRIGHT=false

if check_cmd slidev; then
    info "slidev (global)"
    # Slidev requires two separate Playwright pieces for PNG export:
    #   1. playwright-chromium npm package (globally importable by Slidev)
    #   2. The Chromium browser binary (downloaded by `playwright install`)
    # Check for both and offer to fix if missing.
    if npm list -g playwright-chromium 2>/dev/null | grep -q "playwright-chromium"; then
        info "playwright-chromium (global)"
    else
        warn "playwright-chromium is not installed globally — Slidev PNG export will fail"
        echo ""
        printf "  Install playwright-chromium now? [y/N] "
        read -r answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            INSTALL_PLAYWRIGHT=true
        else
            warn "Skipping. Install later with:"
            warn "  npm install -g playwright-chromium"
            warn "  npx playwright install chromium"
        fi
    fi
else
    echo ""
    printf "  Install Slidev support? (only needed for Slidev presentations) [y/N] "
    read -r answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        INSTALL_SLIDEV=true
        INSTALL_PLAYWRIGHT=true
    else
        info "Skipping Slidev (you can install later with: npm install -g @slidev/cli)"
    fi
fi

# ── Virtual environment ─────────────────────────────────────────────────────

echo ""
echo "Setting up Python virtual environment…"

if [ -d "$VENV_DIR" ] && ! "$VENV_DIR/bin/pip" --version &>/dev/null; then
    echo "  Existing venv is broken — removing…"
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    info "Created $VENV_DIR"
else
    info "$VENV_DIR already exists"
fi

PIP="$VENV_DIR/bin/pip"

# ── Python dependencies ─────────────────────────────────────────────────────

echo ""
echo "Installing Python dependencies (this may take a while on first run)…"

"$PIP" install --upgrade pip --quiet
"$PIP" install -r requirements.txt --quiet
info "All packages installed"

# ── Slidev installation ───────────────────────────────────────────────────────

if $INSTALL_SLIDEV; then
    echo ""
    echo "Installing Slidev CLI…"
    npm install -g @slidev/cli
    info "@slidev/cli installed"
fi

if $INSTALL_PLAYWRIGHT; then
    echo ""
    # Two steps are both required for Slidev PNG export:
    #   Step 1: the playwright-chromium npm package (Slidev imports it at runtime)
    #   Step 2: the Chromium browser binary (Playwright downloads separately)
    echo "Installing playwright-chromium npm package (required by Slidev for PNG export)…"
    npm install -g playwright-chromium
    info "playwright-chromium installed"

    echo "Downloading Chromium browser binary (used by Playwright)…"
    npx playwright install chromium
    info "Chromium browser installed"
fi

# ── Activate ─────────────────────────────────────────────────────────────────

echo ""
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Activated $VENV_DIR"

echo ""
echo "Setup complete. You're ready to go:"
echo "  python -m deck2video presentation.md --voice path/to/voice.wav"
echo ""

set +euo pipefail
