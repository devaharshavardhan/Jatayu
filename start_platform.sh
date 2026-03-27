#!/usr/bin/env bash
# ============================================================
#  JATAYU - Agentic IT Orchestrator
#  Start the full platform: Kafka + FastAPI + All 6 Agents
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

echo -e "${BOLD}${CYAN}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   JATAYU — Agentic IT Orchestrator           ║"
echo "  ║   Autonomous AIOps Control Plane             ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Check venv ──────────────────────────────────────────────
if [ -d ".venv" ]; then
  PYTHON=".venv/bin/python"
  PIP=".venv/bin/pip"
  [ ! -f "$PYTHON" ] && PYTHON=".venv/Scripts/python" && PIP=".venv/Scripts/pip"
else
  PYTHON="python3"
  PIP="pip"
fi

echo -e "${YELLOW}▸ Using Python:${NC} $($PYTHON --version 2>&1)"

# ── Step 1: Start Kafka ──────────────────────────────────────
echo -e "\n${CYAN}[1/3] Starting Kafka...${NC}"
if docker compose ps --services --filter status=running 2>/dev/null | grep -q kafka; then
  echo -e "${GREEN}  ✓ Kafka already running${NC}"
else
  docker compose up -d
  echo -e "${GREEN}  ✓ Kafka started${NC}"
  echo "  Waiting for Kafka to be ready..."
  sleep 6
fi

# ── Step 2: Start FastAPI ────────────────────────────────────
echo -e "\n${CYAN}[2/3] Starting FastAPI Control Plane on :8000...${NC}"
UVICORN_LOG_LEVEL=warning $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
FASTAPI_PID=$!
echo -e "${GREEN}  ✓ FastAPI started (PID $FASTAPI_PID)${NC}"
sleep 2

# ── Step 3: Start All Agents ─────────────────────────────────
echo -e "\n${CYAN}[3/3] Starting Agent Pipeline...${NC}"

AGENT_PIDS=()

start_agent() {
  local name=$1
  local module=$2
  $PYTHON -m "$module" > "logs/agent_${name}.log" 2>&1 &
  local pid=$!
  AGENT_PIDS+=($pid)
  echo -e "${GREEN}  ✓ ${name} agent started (PID $pid)${NC}"
}

mkdir -p logs

start_agent "monitoring"  "agents.monitoring_agent"
sleep 0.5
start_agent "prediction"  "agents.prediction_agent"
sleep 0.5
start_agent "rca"         "agents.rca_agent"
sleep 0.5
start_agent "decision"    "agents.decision_agent"
sleep 0.5
start_agent "remediation" "agents.remediation_agent"
sleep 0.5
start_agent "reporting"   "agents.reporting_agent"

# ── Ready ────────────────────────────────────────────────────
echo -e "\n${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  JATAYU Platform is running!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${CYAN}Dashboard:${NC}   http://localhost:8000"
echo -e "  ${CYAN}API Docs:${NC}    http://localhost:8000/docs"
echo -e "  ${CYAN}Kafka:${NC}       localhost:9092"
echo ""
echo -e "  ${YELLOW}Agent Pipeline:${NC}"
echo -e "  Publisher → Monitoring → Prediction → RCA → Decision → Remediation → Reporting"
echo ""
echo -e "  ${YELLOW}To test:${NC} Open dashboard, select a scenario, click Play or Pub All"
echo ""
echo -e "  Press Ctrl+C to stop all processes"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Trap: cleanup on exit ────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}Stopping FastAPI and agents (Kafka container kept running)...${NC}"
  kill $FASTAPI_PID 2>/dev/null || true
  for pid in "${AGENT_PIDS[@]}"; do kill $pid 2>/dev/null || true; done
  echo -e "${GREEN}All stopped. Run 'docker compose down' manually to stop Kafka.${NC}"
}
trap cleanup EXIT INT TERM

# Wait for FastAPI to stay alive
wait $FASTAPI_PID
