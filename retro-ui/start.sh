#!/bin/bash

# LinkedIn Easy Apply - Retro UI Startup Script

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║         LINKEDIN EASY APPLY - RETRO TERMINAL UI                     ║"
echo "║                    Starting Services...                              ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if action server is running (try both ports)
echo -n "Checking Action Server... "
if curl -s http://localhost:8082/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running on port 8082${NC}"
elif curl -s http://localhost:8080/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running on port 8080${NC}"
    echo -e "${YELLOW}Note: Detected on port 8080, but retro-ui expects 8082${NC}"
    echo "You may need to update app.js CONFIG.ACTION_SERVER_URL"
else
    echo -e "${RED}✗ Not Running${NC}"
    echo ""
    echo -e "${YELLOW}Action server not detected on port 8080 or 8082${NC}"
    echo "Please start it first with: action-server start --port 8082"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if database exists
echo -n "Checking Database... "
if [ -f "../src/linkedin_jobs.sqlite" ]; then
    echo -e "${GREEN}✓ Found${NC}"
else
    echo -e "${RED}✗ Not Found${NC}"
    echo -e "${YELLOW}Database not found at ../src/linkedin_jobs.sqlite${NC}"
    echo "Creating empty database..."
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    npm install --silent
fi

# Kill any existing server on port 3001
echo -n "Checking port 3001... "
if lsof -Pi :3001 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}Port in use, stopping existing process${NC}"
    kill $(lsof -t -i:3001) 2>/dev/null
    sleep 1
else
    echo -e "${GREEN}✓ Available${NC}"
fi

# Start the server
echo ""
echo -e "${GREEN}Starting Retro UI Backend Server...${NC}"
echo ""

cd "$(dirname "$0")"
node server.js

# The server runs in foreground, so this only executes on Ctrl+C
echo ""
echo -e "${GREEN}Server stopped${NC}"
