#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup-llm.sh  —  One-shot LLM setup for HolmesGPT anomaly detection
#
# What this does (automatically, in order):
#   1. Detect OS (macOS / Linux)
#   2. Install Ollama if not already installed
#   3. Start the Ollama server if not already running
#   4. Pull the configured model (default: llama3.2)
#   5. Create .env with Ollama as the LLM provider (if .env doesn't exist)
#   6. Rebuild & restart the backend Docker container
#   7. Verify HolmesGPT connected successfully
#
# Usage:
#   chmod +x setup-llm.sh
#   ./setup-llm.sh                  # Ollama (default, free, local)
#   ./setup-llm.sh --provider groq  # Groq free cloud  (needs GROQ_API_KEY)
#   ./setup-llm.sh --model mistral  # Different Ollama model
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Resolve the directory this script lives in.
# Captures $PWD at invocation time so relative paths work correctly even when
# the caller's working directory differs from the script's location.
_INVOKE_DIR="$PWD"
_SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
if [[ "$_SCRIPT_PATH" != /* ]]; then
  _SCRIPT_PATH="$_INVOKE_DIR/$_SCRIPT_PATH"
fi
SCRIPT_DIR="$(cd "$(dirname "$_SCRIPT_PATH")" && pwd)"
unset _INVOKE_DIR _SCRIPT_PATH

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'
RED='\033[0;31m';   BOLD='\033[1m';    NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC}  $*"; }
info() { echo -e "${BLUE}ℹ${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC}  $*"; }
step() { echo -e "\n${BOLD}$*${NC}"; }

# ── Defaults (overridable via flags) ─────────────────────────────────────────
PROVIDER="${LLM_PROVIDER:-ollama}"
MODEL=""          # empty = use per-provider default in .env
GROQ_KEY="${GROQ_API_KEY:-}"
OPENAI_KEY="${OPENAI_API_KEY:-}"

# ── Parse CLI flags ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --provider) PROVIDER="$2";   shift 2 ;;
    --model)    MODEL="$2";      shift 2 ;;
    --groq-key) GROQ_KEY="$2";   shift 2 ;;
    --openai-key) OPENAI_KEY="$2"; shift 2 ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ── Per-provider defaults ─────────────────────────────────────────────────────
case "$PROVIDER" in
  ollama) [[ -z "$MODEL" ]] && MODEL="llama3.2"              ;;
  groq)   [[ -z "$MODEL" ]] && MODEL="llama-3.3-70b-versatile" ;;
  openai) [[ -z "$MODEL" ]] && MODEL="gpt-4o-mini"           ;;
  *) err "Unknown provider: $PROVIDER (choose: ollama | groq | openai)"; exit 1 ;;
esac

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   HolmesGPT LLM Setup — provider: $PROVIDER      ${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Docker check
# ═══════════════════════════════════════════════════════════════════════════════
step "Step 1/5 — Checking Docker"
if ! docker info > /dev/null 2>&1; then
  err "Docker is not running. Start Docker Desktop and re-run this script."
  exit 1
fi
ok "Docker is running"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Provider-specific setup
# ═══════════════════════════════════════════════════════════════════════════════
step "Step 2/5 — Setting up provider: $PROVIDER"

if [[ "$PROVIDER" == "ollama" ]]; then

  # ── Install Ollama ──────────────────────────────────────────────────────────
  if command -v ollama &> /dev/null; then
    ok "Ollama already installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
  else
    info "Installing Ollama..."
    OS="$(uname -s)"
    case "$OS" in
      Darwin)
        if command -v brew &> /dev/null; then
          brew install ollama
        else
          # Direct install (no Homebrew)
          curl -fsSL https://ollama.com/install.sh | sh
        fi
        ;;
      Linux)
        curl -fsSL https://ollama.com/install.sh | sh
        ;;
      *)
        err "Unsupported OS: $OS. Install Ollama manually from https://ollama.com/download"
        exit 1
        ;;
    esac
    ok "Ollama installed"
  fi

  # ── Start Ollama server ─────────────────────────────────────────────────────
  if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    ok "Ollama server already running"
  else
    info "Starting Ollama server in background..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    # Wait up to 15 s for it to become ready
    for i in $(seq 1 15); do
      if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        ok "Ollama server started (pid $!)"
        break
      fi
      sleep 1
      if [[ $i -eq 15 ]]; then
        err "Ollama server did not start in time. Check /tmp/ollama.log"
        exit 1
      fi
    done
  fi

  # ── Pull model ──────────────────────────────────────────────────────────────
  EXISTING=$(curl -sf http://localhost:11434/api/tags | grep -o "\"name\":\"[^\"]*\"" | grep -o "\"[^\"]*\"$" | tr -d '"' 2>/dev/null || echo "")
  if echo "$EXISTING" | grep -q "^${MODEL}"; then
    ok "Model '$MODEL' already pulled"
  else
    info "Pulling model '$MODEL' (this may take a few minutes on first run)..."
    ollama pull "$MODEL"
    ok "Model '$MODEL' ready"
  fi

elif [[ "$PROVIDER" == "groq" ]]; then

  if [[ -z "$GROQ_KEY" ]]; then
    echo ""
    warn "GROQ_API_KEY not set."
    echo "  Get a free key (no credit card): https://console.groq.com"
    echo -n "  Paste your Groq API key now (or press Enter to skip): "
    read -r GROQ_KEY
    if [[ -z "$GROQ_KEY" ]]; then
      warn "Skipping Groq — will use RuleBasedDetector fallback"
      PROVIDER="rule-based"
    fi
  fi
  ok "Groq API key set"

elif [[ "$PROVIDER" == "openai" ]]; then

  if [[ -z "$OPENAI_KEY" ]]; then
    echo ""
    warn "OPENAI_API_KEY not set."
    echo "  Add billing credits: https://platform.openai.com/settings/organization/billing"
    echo -n "  Paste your OpenAI API key now (or press Enter to skip): "
    read -r OPENAI_KEY
    if [[ -z "$OPENAI_KEY" ]]; then
      warn "Skipping OpenAI — will use RuleBasedDetector fallback"
      PROVIDER="rule-based"
    fi
  fi
  ok "OpenAI API key set"

fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Write .env
# ═══════════════════════════════════════════════════════════════════════════════
step "Step 3/5 — Writing .env"

ENV_FILE="$SCRIPT_DIR/.env"

cat > "$ENV_FILE" <<EOF
# ──────────────────────────────────────────────────────────────────────────────
# HolmesGPT LLM Provider — auto-generated by setup-llm.sh
# Re-run ./setup-llm.sh to change provider/model
# ──────────────────────────────────────────────────────────────────────────────

LLM_PROVIDER=${PROVIDER}
HOLMES_MODEL=${MODEL}

# Ollama
OLLAMA_HOST=http://host.docker.internal:11434

# Groq (free tier — https://console.groq.com)
GROQ_API_KEY=${GROQ_KEY}

# OpenAI (requires billing credits — https://platform.openai.com)
OPENAI_API_KEY=${OPENAI_KEY}
EOF

ok ".env written → $ENV_FILE"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Rebuild & restart backend
# ═══════════════════════════════════════════════════════════════════════════════
step "Step 4/5 — Rebuilding & restarting backend"

cd "$SCRIPT_DIR"
docker compose build backend
docker compose up -d backend

info "Waiting for backend to be ready..."
for i in $(seq 1 20); do
  if curl -sf http://localhost:8001/ > /dev/null 2>&1; then
    ok "Backend is up"
    break
  fi
  sleep 2
  if [[ $i -eq 20 ]]; then
    warn "Backend health check timed out — check: docker logs visibility-api"
  fi
done

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Verify HolmesGPT connected
# ═══════════════════════════════════════════════════════════════════════════════
step "Step 5/5 — Verifying HolmesGPT"

sleep 3   # let Redis cache warm up

RESULT=$(curl -sf http://localhost:8001/api/ai/analyze 2>/dev/null || echo "{}")
ENGINE=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('engine','unknown'))" 2>/dev/null || echo "unknown")
HEALTH=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('overall_health_score','?'))" 2>/dev/null || echo "?")

echo ""
if echo "$ENGINE" | grep -q "HolmesGPT"; then
  ok "HolmesGPT ACTIVE  →  engine: $ENGINE  |  health: ${HEALTH}%"
  echo ""
  echo -e "${GREEN}${BOLD}  ✅  LLM anomaly detection is live!${NC}"
else
  warn "Engine: $ENGINE  |  health: ${HEALTH}%"
  echo ""
  echo "  HolmesGPT fell back to rule-based detection."
  echo "  Check backend logs for details:"
  echo "    docker logs visibility-api 2>&1 | grep -i holmesgpt"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Dashboard   →  http://localhost:3000"
echo -e "  Backend API →  http://localhost:8001"
echo -e "  Provider    →  ${PROVIDER}  (model: ${MODEL})"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""
