#!/bin/bash

set -e

echo "🚀 Starting FlexAI Visibility Platform..."
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

echo -e "${BLUE}✓${NC} Docker is running"

# Create necessary directories
echo ""
echo "📁 Creating directories..."
mkdir -p config/alerts

# Check if directories exist
if [ -d "backend" ] && [ -d "frontend" ] && [ -d "config" ]; then
    echo -e "${GREEN}✓${NC} All directories exist"
else
    echo "❌ Missing required directories. Make sure you're in the visibility-platform folder."
    exit 1
fi

# ── LLM / HolmesGPT bootstrap ────────────────────────────────────────────────
echo ""
echo "🤖 Checking HolmesGPT / LLM configuration..."

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠${NC}  No .env found — running LLM setup (first-time only)..."
    bash "$(dirname "$0")/setup-llm.sh"
else
    # .env exists — source it quietly to read LLM_PROVIDER
    set +e
    # shellcheck disable=SC1091
    source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')
    set -e

    PROVIDER="${LLM_PROVIDER:-ollama}"

    if [ "$PROVIDER" = "ollama" ]; then
        if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Ollama is running (provider: ollama, model: ${HOLMES_MODEL:-llama3.2})"
        else
            echo -e "${YELLOW}⚠${NC}  Ollama not running — starting it..."
            nohup ollama serve > /tmp/ollama.log 2>&1 &
            for i in $(seq 1 15); do
                if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
                    echo -e "${GREEN}✓${NC} Ollama started"
                    break
                fi
                sleep 1
                if [ "$i" -eq 15 ]; then
                    echo -e "${YELLOW}⚠${NC}  Ollama did not start — will use RuleBasedDetector fallback"
                fi
            done
        fi
    else
        echo -e "${GREEN}✓${NC} LLM provider: $PROVIDER (model: ${HOLMES_MODEL:-default})"
    fi
fi
# ─────────────────────────────────────────────────────────────────────────────

# Stop any existing containers
echo ""
echo "🛑 Stopping any existing containers..."
docker-compose down 2>/dev/null || true

# Start the observability stack
echo ""
echo "🎯 Starting observability stack..."
echo ""
docker-compose up -d victoria-metrics vmagent alertmanager vmalert grafana node-exporter redis

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to start (30 seconds)..."
sleep 30

# Check if services are running
echo ""
echo "🔍 Checking service status..."
if docker ps | grep -q victoria-metrics; then
    echo -e "${GREEN}✓${NC} Victoria Metrics is running"
else
    echo -e "${YELLOW}⚠${NC} Victoria Metrics may not be ready yet"
fi

if docker ps | grep -q vmagent; then
    echo -e "${GREEN}✓${NC} VMAgent is running"
else
    echo -e "${YELLOW}⚠${NC} VMAgent may not be ready yet"
fi

if docker ps | grep -q grafana; then
    echo -e "${GREEN}✓${NC} Grafana is running"
else
    echo -e "${YELLOW}⚠${NC} Grafana may not be ready yet"
fi

if docker ps | grep -q redis; then
    echo -e "${GREEN}✓${NC} Redis is running"
else
    echo -e "${YELLOW}⚠${NC} Redis may not be ready yet"
fi

# Start backend and frontend
echo ""
echo "🔧 Starting backend API..."
docker-compose up -d backend

echo "⏳ Waiting for backend to be ready..."
sleep 10

echo ""
echo "🎨 Starting frontend UI..."
docker-compose up -d frontend

echo "⏳ Waiting for frontend to be ready..."
sleep 10

# Show status
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ FlexAI Visibility Platform is running!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Access the following services:"
echo ""
echo -e "${BLUE}Frontend Dashboard:${NC}      http://localhost:3000"
echo -e "${BLUE}Backend API:${NC}             http://localhost:8001"
echo -e "${BLUE}API Documentation:${NC}       http://localhost:8001/docs"
echo -e "${BLUE}Victoria Metrics:${NC}        http://localhost:8428"
echo -e "${BLUE}Grafana:${NC}                 http://localhost:3001 (admin/admin)"
echo -e "${BLUE}Alertmanager:${NC}            http://localhost:9093"
echo -e "${BLUE}VMAlert:${NC}                 http://localhost:8880"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Useful commands:"
echo "  • View logs:        docker-compose logs -f [service-name]"
echo "  • Stop everything:  docker-compose down"
echo "  • Restart service:  docker-compose restart [service-name]"
echo ""
echo "🔍 Quick health checks:"
echo "  curl http://localhost:8001/health"
echo "  curl http://localhost:8428/api/v1/status/tsdb"
echo "  curl http://localhost:8001/api/clusters"
echo ""
echo "🎉 Happy monitoring!"
echo ""
