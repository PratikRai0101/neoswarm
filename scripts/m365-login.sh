#!/bin/bash
# One-time Microsoft 365 authentication for OpenSwarm.
# Run this once to cache your M365 token. After that, M365 works in OpenSwarm automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

CACHE_DIR="$HOME/.openswarm"
mkdir -p "$CACHE_DIR"

export MS365_MCP_TOKEN_CACHE_PATH="$CACHE_DIR/ms365-token-cache.json"
export MS365_MCP_SELECTED_ACCOUNT_PATH="$CACHE_DIR/ms365-selected-account.json"

SERVER_SCRIPT="$PROJECT_ROOT/backend/npm-servers/softeria-ms-365-mcp-server/node_modules/@softeria/ms-365-mcp-server/dist/index.js"

if [ ! -f "$SERVER_SCRIPT" ]; then
    echo "M365 MCP server not found. Run 'cd backend/npm-servers/softeria-ms-365-mcp-server && npm install' first."
    exit 1
fi

echo ""
echo "  Microsoft 365 Login for OpenSwarm"
echo "  ─────────────────────────────────"
echo "  A browser window will open for you to sign in."
echo "  After login, the token is cached and M365 works in OpenSwarm automatically."
echo ""

node "$SERVER_SCRIPT" --login

if [ -f "$MS365_MCP_TOKEN_CACHE_PATH" ]; then
    echo ""
    echo "  ✓ Token cached at $MS365_MCP_TOKEN_CACHE_PATH"
    echo "  ✓ M365 is ready to use in OpenSwarm!"
    echo ""
else
    echo ""
    echo "  ✗ Login may have failed — no token cache found."
    echo ""
fi
