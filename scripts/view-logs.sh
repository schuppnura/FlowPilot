#!/bin/bash
# Simple script to view API logs

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

cd "$(dirname "$0")"

# Check if jq is available for pretty printing
if command -v jq &> /dev/null; then
    USE_JQ=true
else
    USE_JQ=false
fi

# Parse arguments
SERVICE=""
FOLLOW=false
TAIL=50

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--tail)
            TAIL="$2"
            shift 2
            ;;
        authz|authz-api)
            SERVICE="flowpilot-authz-api"
            shift
            ;;
        domain|domain-services|domain-api)
            SERVICE="flowpilot-domain-services-api"
            shift
            ;;
        *)
            echo "Usage: $0 [authz|domain] [-f|--follow] [-n|--tail N]"
            echo ""
            echo "Examples:"
            echo "  $0                    # View all API logs (last 50 lines)"
            echo "  $0 -f                 # Follow all API logs in real-time"
            echo "  $0 authz              # View authz-api logs"
            echo "  $0 domain -f          # Follow domain-services-api logs"
            echo "  $0 -n 100              # View last 100 lines"
            exit 1
            ;;
    esac
done

# Build docker compose command
CMD="docker compose logs"
if [ "$FOLLOW" = true ]; then
    CMD="$CMD -f"
else
    CMD="$CMD --tail $TAIL"
fi

if [ -n "$SERVICE" ]; then
    CMD="$CMD $SERVICE"
fi

# Filter and display
if [ "$USE_JQ" = true ]; then
    echo -e "${BLUE}Viewing API logs (pretty-printed with jq)${NC}"
    if [ "$FOLLOW" = true ]; then
        echo -e "${GREEN}Following logs in real-time... (Press Ctrl+C to stop)${NC}"
        echo -e "${GREEN}Waiting for API calls... Make a request from the app to see logs.${NC}"
        echo ""
    fi
    # Strip service name prefix and show separators + JSON logs
    # For follow mode, use unbuffered processing to ensure real-time output
    if [ "$FOLLOW" = true ]; then
        $CMD 2>&1 | while IFS= read -r line || [ -n "$line" ]; do
            # Check if line contains API log or separator
            if echo "$line" | grep -qE '(─{10,}|"type":\s*"(api_request|api_response)")'; then
                # Strip service name prefix
                cleaned_line=$(echo "$line" | sed 's/^[^|]*| //')
                # If it's a separator line, print it directly; otherwise try to parse as JSON
                if [[ "$cleaned_line" =~ ^─+$ ]]; then
                    echo "$cleaned_line"
                else
                    echo "$cleaned_line" | jq . 2>/dev/null || echo "$cleaned_line"
                fi
            fi
        done
    else
        $CMD 2>&1 | grep -E '(─{10,}|"type":\s*"(api_request|api_response)")' | sed 's/^[^|]*| //' | while IFS= read -r line || [ -n "$line" ]; do
            # If it's a separator line, print it directly; otherwise try to parse as JSON
            if [[ "$line" =~ ^─+$ ]]; then
                echo "$line"
            else
                echo "$line" | jq . 2>/dev/null || echo "$line"
            fi
        done
    fi
else
    echo -e "${BLUE}Viewing API logs${NC}"
    if [ "$FOLLOW" = true ]; then
        echo -e "${GREEN}Following logs in real-time... (Press Ctrl+C to stop)${NC}"
        echo -e "${GREEN}Waiting for API calls... Make a request from the app to see logs.${NC}"
        echo ""
    else
        echo -e "${GREEN}Tip: Install 'jq' (brew install jq) for pretty-printed JSON${NC}"
        echo ""
    fi
    if [ "$FOLLOW" = true ]; then
        $CMD 2>&1 | while IFS= read -r line || [ -n "$line" ]; do
            if echo "$line" | grep -qE '"type":\s*"(api_request|api_response)"'; then
                echo "$line"
            fi
        done
    else
        $CMD 2>&1 | grep -E '"type":\s*"(api_request|api_response)"'
    fi
fi

# If no logs found and not following, show a helpful message
if [ "$FOLLOW" = false ]; then
    LOG_COUNT=$($CMD 2>&1 | grep -c -E '"type":\s*"(api_request|api_response)"' || echo "0")
    if [ "$LOG_COUNT" = "0" ]; then
        echo ""
        echo -e "${GREEN}No API logs found in recent history.${NC}"
        echo -e "${GREEN}Try:${NC}"
        echo -e "  - Make an API call from the Nura Travel app"
        echo -e "  - Use: $0 -n 500  (to see more history)"
        echo -e "  - Use: $0 -f     (to follow in real-time)"
    fi
fi

