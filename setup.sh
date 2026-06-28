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

# Save the caller's shell options so we can restore them at the end.
# `set +o` emits a list of `set ±o NAME` commands suitable for `eval`.
DECK2VIDEO_PRIOR_SHOPTS=$(set +o)
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
    # npx is available but marp isn't installed globally.  A global install is
    # recommended: it's faster and avoids an interactive download prompt on
    # the first run (even though deck2video now passes --yes to npx).
    echo ""
    printf "  marp-cli not found globally. Install it now (recommended)? [y/N] "
    read -r answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        npm install -g @marp-team/marp-cli
        info "marp-cli installed"
    else
        info "Skipping — will use npx @marp-team/marp-cli at runtime"
    fi
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

# ── TTS engine selection (at least one required) ────────────────────────────
#
# Both engines are optional and heavy in different ways: Chatterbox pulls in
# torch (a large download) but runs locally; ElevenLabs is a tiny SDK but calls
# a paid hosted API. deck2video needs at least one, so loop until the user
# picks something rather than leaving them with a tool that can't synthesize.

INSTALL_CHATTERBOX=false
INSTALL_ELEVENLABS=false

while true; do
    INSTALL_CHATTERBOX=false
    INSTALL_ELEVENLABS=false

    echo ""
    echo "Choose at least one TTS engine:"

    printf "  Install Chatterbox? (local neural model, default engine, large download) [y/N] "
    read -r answer
    [[ "$answer" =~ ^[Yy]$ ]] && INSTALL_CHATTERBOX=true

    printf "  Install ElevenLabs? (hosted API, small SDK, needs ELEVENLABS_API_KEY) [y/N] "
    read -r answer
    [[ "$answer" =~ ^[Yy]$ ]] && INSTALL_ELEVENLABS=true

    if $INSTALL_CHATTERBOX || $INSTALL_ELEVENLABS; then
        break
    fi
    warn "deck2video needs a TTS engine. Pick Chatterbox, ElevenLabs, or both."
done

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
info "Core packages installed"

if $INSTALL_CHATTERBOX; then
    echo ""
    echo "Installing Chatterbox TTS (this downloads torch and may take a while)…"
    "$PIP" install -r requirements-chatterbox.txt --quiet
    info "Chatterbox TTS installed"
fi

if $INSTALL_ELEVENLABS; then
    echo ""
    echo "Installing ElevenLabs TTS support…"
    "$PIP" install -r requirements-elevenlabs.txt --quiet
    info "ElevenLabs SDK installed"
fi

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
if $INSTALL_CHATTERBOX; then
    echo "  python -m deck2video presentation.md --voice path/to/voice.wav"
fi
if $INSTALL_ELEVENLABS; then
    echo "  export ELEVENLABS_API_KEY=sk_..."
    echo "  python -m deck2video presentation.md --tts-engine elevenlabs --elevenlabs-voice-id <id>"
fi
echo ""

# Restore the caller's prior shell options so sourcing this script doesn't
# permanently mutate set -e/-u/pipefail in the user's interactive shell.
eval "$DECK2VIDEO_PRIOR_SHOPTS"
unset DECK2VIDEO_PRIOR_SHOPTS
