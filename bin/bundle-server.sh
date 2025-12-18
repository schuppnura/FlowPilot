#!/usr/bin/env bash
set -euo pipefail

# Purpose: Manage the HTTPS bundle server for ***REMOVED*** OCI policy bundles
# Usage: ./bin/bundle-server.sh [start|stop|status|restart|rebuild]

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SERVER_SCRIPT="infra/***REMOVED***/cfg/https_bundle_server.py"
LOG_FILE="/tmp/https-bundle-server.log"
PID_FILE="/tmp/https-bundle-server.pid"

start_server() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "HTTPS bundle server is already running (PID: $(cat "$PID_FILE"))"
        return 0
    fi
    
    echo ">>> Starting HTTPS bundle server..."
    nohup python3 "$SERVER_SCRIPT" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "✓ HTTPS bundle server started (PID: $(cat "$PID_FILE"))"
        echo "  Log: $LOG_FILE"
        echo "  URL: https://localhost:8888/bundle/flowpilot-policy.tar.gz"
    else
        echo "✗ Failed to start HTTPS bundle server"
        echo "  Check logs: cat $LOG_FILE"
        return 1
    fi
}

stop_server() {
    if [ ! -f "$PID_FILE" ]; then
        echo "HTTPS bundle server is not running (no PID file)"
        return 0
    fi
    
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo ">>> Stopping HTTPS bundle server (PID: $PID)..."
        kill "$PID"
        rm -f "$PID_FILE"
        echo "✓ HTTPS bundle server stopped"
    else
        echo "HTTPS bundle server is not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
}

status_server() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        PID=$(cat "$PID_FILE")
        echo "✓ HTTPS bundle server is running (PID: $PID)"
        echo "  URL: https://localhost:8888/bundle/flowpilot-policy.tar.gz"
        echo "  Log: $LOG_FILE"
        
        # Test connectivity
        if curl -k -s -o /dev/null -w "%{http_code}" https://localhost:8888/bundle/flowpilot-policy.tar.gz | grep -q "200"; then
            echo "  Status: Healthy (bundle accessible)"
        else
            echo "  Status: Unhealthy (bundle not accessible)"
        fi
    else
        echo "✗ HTTPS bundle server is not running"
        if [ -f "$PID_FILE" ]; then
            rm -f "$PID_FILE"
        fi
    fi
}

rebuild_bundle() {
    echo ">>> Rebuilding OCI policy bundle..."
    
    if ! command -v policy &> /dev/null; then
        echo "✗ Error: policy CLI not found"
        echo "  Install with: brew tap opcr-io/tap && brew install opcr-io/tap/policy"
        return 1
    fi
    
    policy build infra/***REMOVED***/cfg/bundle -t localhost/flowpilot-policy:latest
    policy save localhost/flowpilot-policy:latest -f infra/***REMOVED***/cfg/bundle/flowpilot-policy.tar.gz
    
    echo "✓ Policy bundle rebuilt successfully"
    echo "  ***REMOVED*** will fetch the updated bundle on next poll or restart"
}

case "${1:-}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    status)
        status_server
        ;;
    restart)
        stop_server
        start_server
        ;;
    rebuild)
        rebuild_bundle
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|rebuild}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the HTTPS bundle server"
        echo "  stop     - Stop the HTTPS bundle server"
        echo "  status   - Check server status and connectivity"
        echo "  restart  - Stop and start the server"
        echo "  rebuild  - Rebuild the OCI policy bundle"
        exit 1
        ;;
esac
