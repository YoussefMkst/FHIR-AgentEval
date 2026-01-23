#!/usr/bin/env bash
# start_servers.sh
# Starts all MCP servers needed for run_experiment_fhir.py
#
# Services started:
#   - FHIR MCP Server (port 8000)
#   - FHIR Specs/Ref MCP Server (port 8010)
#   - Memory MCP Server - no spec training (port 8011)
#   - Memory MCP Server - with spec training (port 8012)
#
# Usage:
#   ./start_servers.sh   # Start all servers (foreground with logs)
#   Ctrl+C to stop all servers

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Paths to MCP servers
FHIR_MCP="$ROOT_DIR/environment/mcp/baseline_server/fhir_mcp_server.py"
FHIR_REF_MCP="$ROOT_DIR/environment/mcp/memory_servers/fhir_ref_mcp_server.py"
MEMORY_MCP="$ROOT_DIR/environment/mcp/memory_servers/fhir_memory_mcp_server.py"

# Memory index directories
MEMORY_NO_SPEC_DIR="exp_fig_3_no_spec"
MEMORY_WITH_SPEC_DIR="exp_fig_3_with_spec"

# Track PIDs for cleanup
PIDS=()

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

# ─────────────────────────────────────────────────────────────────────
# Cleanup on exit
# ─────────────────────────────────────────────────────────────────────
cleanup() {
    echo ""
    info "Stopping all servers..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
        fi
    done
    wait 2>/dev/null
    log "All servers stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ─────────────────────────────────────────────────────────────────────
# Check prerequisites
# ─────────────────────────────────────────────────────────────────────
check_prereqs() {
    info "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        err "Python3 is not installed"
        exit 1
    fi
    
    # Check .env file
    if [[ ! -f "$ROOT_DIR/environment/.env" ]]; then
        warn "Missing environment/.env file"
        echo "   Create it with your OPENAI_API_KEY:"
        echo "   echo 'OPENAI_API_KEY=sk-...' > $ROOT_DIR/environment/.env"
    fi
    
    # Check MCP server files exist
    for f in "$FHIR_MCP" "$FHIR_REF_MCP" "$MEMORY_MCP"; do
        if [[ ! -f "$f" ]]; then
            err "Missing: $f"
            exit 1
        fi
    done
    
    # Check FHIR server is running
    if ! curl -sf http://localhost:7070/fhir/metadata > /dev/null 2>&1; then
        warn "FHIR server not responding at http://localhost:7070/fhir"
        echo ""
        echo "   Start it with:"
        echo "   cd $ROOT_DIR/environment/hapi-fhir && docker-compose up -d"
        echo ""
        read -p "   Continue anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log "FHIR server is running"
    fi
    
    log "Prerequisites OK"
}

# ─────────────────────────────────────────────────────────────────────
# Prefix output with colored server name
# ─────────────────────────────────────────────────────────────────────
prefix_output() {
    local name=$1
    local color=$2
    while IFS= read -r line; do
        echo -e "${color}[${name}]${NC} $line"
    done
}

# ─────────────────────────────────────────────────────────────────────
# Start a server with logging
# ─────────────────────────────────────────────────────────────────────
start_server() {
    local name=$1
    local color=$2
    local port=$3
    shift 3
    local cmd=("$@")
    
    # Check if port is already in use
    if lsof -i :"$port" > /dev/null 2>&1; then
        warn "$name: port $port already in use, skipping"
        return 0
    fi
    
    # Start server with prefixed output
    "${cmd[@]}" 2>&1 | prefix_output "$name" "$color" &
    PIDS+=($!)
    
    sleep 1
    log "$name started on port $port"
}

# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                   Starting MCP Servers                     ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    check_prereqs
    
    echo ""
    info "Starting MCP servers (Ctrl+C to stop all)..."
    echo ""
    
    # 1. FHIR MCP Server (port 8000)
    start_server "FHIR-MCP" "$GREEN" 8000 \
        python3 "$FHIR_MCP" --port 8000 --path /fhir_mcp
    
    # 2. FHIR Specs/Ref MCP Server (port 8010)
    start_server "FHIR-SPECS" "$CYAN" 8010 \
        python3 "$FHIR_REF_MCP" --port 8010 --path /fhir_specs
    
    # 3. Memory MCP Server - no spec training (port 8011)
    start_server "MEM-NOSPEC" "$YELLOW" 8011 \
        python3 "$MEMORY_MCP" --port 8011 \
        --ltm-dir "$MEMORY_NO_SPEC_DIR" \
        --path /memory_fig_3_no_spec
    
    # 4. Memory MCP Server - with spec training (port 8012)
    start_server "MEM-SPEC" "$MAGENTA" 8012 \
        python3 "$MEMORY_MCP" --port 8012 \
        --ltm-dir "$MEMORY_WITH_SPEC_DIR" \
        --path /memory_fig_3_with_spec
    
    echo ""
    echo "─────────────────────────────────────────────────────────────"
    log "All servers running!"
    echo ""
    echo "   Endpoints:"
    echo -e "   • ${GREEN}FHIR MCP${NC}:        http://localhost:8000/fhir_mcp"
    echo -e "   • ${CYAN}FHIR Specs${NC}:      http://localhost:8010/fhir_specs"
    echo -e "   • ${YELLOW}Memory (no-spec)${NC}:   http://localhost:8011/memory_fig_3_no_spec"
    echo -e "   • ${MAGENTA}Memory (with-spec)${NC}: http://localhost:8012/memory_fig_3_with_spec"
    echo ""
    echo "   Press Ctrl+C to stop all servers"
    echo "─────────────────────────────────────────────────────────────"
    echo ""
    
    # Wait for all background processes
    wait
}

main "$@"
