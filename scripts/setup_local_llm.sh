#!/usr/bin/env bash
# Newton 3 — run an open-source LLM locally via Ollama (MIT/Apache models from https://ollama.com/library).
#
# Usage:
#   ./scripts/setup_local_llm.sh                 # native if `ollama` on PATH; else see help
#   ./scripts/setup_local_llm.sh install-ollama  # install Ollama without Docker (brew / curl)
#   ./scripts/setup_local_llm.sh docker          # Ollama in Docker Compose + pull model
#   ./scripts/setup_local_llm.sh native          # use host `ollama` CLI + pull
#   NEWTON3_OLLAMA_MODEL=phi3 ./scripts/setup_local_llm.sh native
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${NEWTON3_OLLAMA_MODEL:-llama3.2}"
COMPOSE_FILE="$ROOT/docker-compose.llm.yml"

print_env() {
  echo ""
  echo "Add these for Newton (same shell or your process manager):"
  echo "  export NEWTON3_LLM_URL=http://127.0.0.1:11434/v1/chat/completions"
  echo "  export NEWTON3_LLM_MODEL=$MODEL"
  echo ""
}

docker_missing_help() {
  echo "Docker is not installed or not on your PATH (run \`docker version\` to verify)."
  echo ""
  OS="$(uname -s 2>/dev/null || echo unknown)"
  if [[ "$OS" == "Darwin" ]]; then
    echo "On macOS you do not need Docker for Newton’s LLM — use native Ollama instead:"
    echo ""
    echo "  1) Install Ollama (pick one):"
    echo "       ./scripts/setup_local_llm.sh install-ollama"
    echo "     Or download the app: https://ollama.com/download"
    echo ""
    echo "  2) Then pull a model:"
    echo "       ./scripts/setup_local_llm.sh native"
    echo ""
    echo "Optional — if you prefer Docker later:"
    echo "  • Docker Desktop: https://docs.docker.com/desktop/install/mac-install/"
    echo "  • Homebrew: brew install --cask docker   (then open Docker.app once)"
  else
    echo "Install Docker Engine for your distro, then retry:"
    echo "  https://docs.docker.com/engine/install/"
    echo ""
    echo "Or skip Docker and install Ollama natively:"
    echo "  ./scripts/setup_local_llm.sh install-ollama"
    echo "  ./scripts/setup_local_llm.sh native"
  fi
}

cmd_install_ollama() {
  OS="$(uname -s 2>/dev/null || echo unknown)"
  if [[ "$OS" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      echo "Installing Ollama via Homebrew..."
      brew install ollama
      echo ""
      echo "Start the Ollama server if needed:  ollama serve"
      echo "(Or install the desktop app from https://ollama.com/download — it starts the service for you.)"
    else
      echo "Homebrew not found. Install Ollama for macOS:"
      echo ""
      echo "  • Download: https://ollama.com/download"
      echo "  • Or install Homebrew from https://brew.sh then run:"
      echo "      brew install ollama"
      exit 1
    fi
  else
    echo "Running Ollama’s Linux installer (may prompt for sudo)..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  echo ""
  echo "Next: ./scripts/setup_local_llm.sh native"
}

cmd_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    docker_missing_help
    exit 1
  fi
  echo "Starting Ollama container..."
  docker compose -f "$COMPOSE_FILE" up -d
  echo "Pulling model '$MODEL' (may take several minutes the first time)..."
  docker compose -f "$COMPOSE_FILE" exec -T ollama ollama pull "$MODEL"
  echo "Done."
  print_env
}

_ollama_reachable() {
  ollama list >/dev/null 2>&1
}

_wait_for_ollama() {
  local max="${1:-60}"
  local i=0
  while [[ "$i" -lt "$max" ]]; do
    if _ollama_reachable; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

_try_start_ollama_macos() {
  [[ "$(uname -s 2>/dev/null)" == "Darwin" ]] || return 1
  if [[ -d "/Applications/Ollama.app" ]]; then
    echo "Ollama server not responding — opening Ollama.app (starts the daemon on macOS)…"
    open -a Ollama 2>/dev/null || true
    echo "Waiting for API at 127.0.0.1:11434 (up to 60s)…"
    if _wait_for_ollama 60; then
      return 0
    fi
  fi
  return 1
}

_ollama_server_help() {
  echo "Ollama is on your PATH, but nothing is listening (or the daemon is still starting)."
  echo ""
  echo "Do one of the following, then re-run:"
  echo "  • macOS (recommended): open **Ollama** from Applications and wait until its menu bar icon is ready."
  echo "  • Any OS: in a **separate terminal**, run:"
  echo "      ollama serve"
  echo "    Leave it running; then in this project directory run:"
  echo "      ./scripts/setup_local_llm.sh native"
  echo "  • Or use Docker instead:"
  echo "      ./scripts/setup_local_llm.sh docker"
  echo ""
}

cmd_native() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama CLI not found."
    echo ""
    echo "Install it, then re-run this script:"
    echo "  ./scripts/setup_local_llm.sh install-ollama"
    echo "Or: https://ollama.com/download"
    echo ""
    echo "If you use Docker instead:"
    echo "  ./scripts/setup_local_llm.sh docker"
    exit 1
  fi
  if ! _ollama_reachable; then
    if ! _try_start_ollama_macos; then
      echo "Error: could not connect to Ollama (nothing on 127.0.0.1:11434)."
      echo ""
      _ollama_server_help
      exit 1
    fi
  fi
  echo "Pulling model '$MODEL'..."
  ollama pull "$MODEL"
  echo "Done. Ollama is running; keep the app (or \`ollama serve\`) open while you use Newton."
  print_env
}

usage() {
  echo "Newton 3 local LLM helper (Ollama)"
  echo ""
  echo "  $0 install-ollama — install Ollama without Docker (macOS: brew; Linux: curl | sh)"
  echo "  $0 native         — pull model using installed \`ollama\` CLI"
  echo "  $0 docker         — run Ollama via Docker Compose + pull model"
  echo "  $0                — same as native if \`ollama\` is on PATH"
  echo "  $0 help           — show this text"
  echo ""
  echo "Default model: $MODEL  (override with NEWTON3_OLLAMA_MODEL=...)"
}

case "${1:-}" in
  docker) cmd_docker ;;
  native) cmd_native ;;
  install-ollama) cmd_install_ollama ;;
  help | -h | --help) usage; exit 0 ;;
  "")
    if command -v ollama >/dev/null 2>&1; then
      echo "Using native Ollama (no argument — same as: $0 native)"
      cmd_native
    else
      usage
      echo ""
      echo "No \`ollama\` on PATH. Easiest on Mac (no Docker):"
      echo "  ./scripts/setup_local_llm.sh install-ollama && ./scripts/setup_local_llm.sh native"
      exit 1
    fi
    ;;
  *)
    echo "Unknown option: $1"
    echo ""
    usage
    exit 1
    ;;
esac
