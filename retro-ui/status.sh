#!/bin/bash

# LinkedIn Easy Apply - Retro UI Status Check
# Quick script to verify all services are running

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║         LINKEDIN EASY APPLY - SYSTEM STATUS CHECK                   ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check Retro UI Backend (Port 3001)
echo -n "🔍 Checking Retro UI Backend (port 3001)... "
if curl -s http://localhost:3001/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ RUNNING${NC}"
    BACKEND_STATUS="ONLINE"
else
    echo -e "${RED}✗ OFFLINE${NC}"
    BACKEND_STATUS="OFFLINE"
fi

# Check Action Server (Port 8082)
echo -n "🔍 Checking Action Server (port 8082)... "
if curl -s http://localhost:8082/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ RUNNING${NC}"
    ACTION_STATUS="ONLINE"
else
    echo -e "${RED}✗ OFFLINE${NC}"
    ACTION_STATUS="OFFLINE"
    # Try port 8080 as fallback
    echo -n "🔍 Checking alternate port 8080... "
    if curl -s http://localhost:8080/ > /dev/null 2>&1; then
        echo -e "${YELLOW}✓ RUNNING (but on 8080 instead of 8082)${NC}"
        echo -e "   ${YELLOW}Update app.js to use port 8080${NC}"
        ACTION_STATUS="WRONG_PORT"
    else
        echo -e "${RED}✗ OFFLINE${NC}"
    fi
fi

# Check Database
echo -n "🔍 Checking Database... "
if [ -f "../src/linkedin_jobs.sqlite" ]; then
    echo -e "${GREEN}✓ FOUND${NC}"
    DB_STATUS="FOUND"
    # Get database stats
    DB_SIZE=$(du -h ../src/linkedin_jobs.sqlite | cut -f1)
    echo "   📊 Database size: $DB_SIZE"
else
    echo -e "${RED}✗ NOT FOUND${NC}"
    DB_STATUS="MISSING"
fi

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Get stats if backend is running
if [ "$BACKEND_STATUS" == "ONLINE" ]; then
    echo "📊 CURRENT STATISTICS:"
    echo ""
    STATS=$(curl -s http://localhost:3001/api/stats)
    
    TOTAL_JOBS=$(echo $STATS | python3 -c "import sys, json; print(json.load(sys.stdin).get('totalJobs', 0))" 2>/dev/null || echo "N/A")
    GOOD_FIT=$(echo $STATS | python3 -c "import sys, json; print(json.load(sys.stdin).get('goodFitJobs', 0))" 2>/dev/null || echo "N/A")
    APPLIED=$(echo $STATS | python3 -c "import sys, json; print(json.load(sys.stdin).get('appliedJobs', 0))" 2>/dev/null || echo "N/A")
    PROFILE=$(echo $STATS | python3 -c "import sys, json; print(json.load(sys.stdin).get('activeProfile', 'N/A'))" 2>/dev/null || echo "N/A")
    
    echo "   Total Jobs: $TOTAL_JOBS"
    echo "   Good Fit Jobs: $GOOD_FIT"
    echo "   Applied Jobs: $APPLIED"
    echo "   Active Profile: $PROFILE"
    echo ""
fi

echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Summary
echo "📋 SUMMARY:"
echo ""

if [ "$BACKEND_STATUS" == "ONLINE" ] && [ "$ACTION_STATUS" == "ONLINE" ] && [ "$DB_STATUS" == "FOUND" ]; then
    echo -e "   ${GREEN}✓ ALL SYSTEMS OPERATIONAL${NC}"
    echo ""
    echo "   🌐 Access the UI at:"
    echo -e "      ${GREEN}http://localhost:3001/index.html${NC}"
    echo ""
    echo "   ⌨️  Keyboard Shortcuts:"
    echo "      F1 - Help"
    echo "      F2 - Search Jobs"
    echo "      F3 - AI Enrichment"
    echo "      F4 - Apply to Jobs"
    echo "      ESC - Close Modal"
else
    echo -e "   ${YELLOW}⚠️  SOME SERVICES ARE DOWN${NC}"
    echo ""
    
    if [ "$BACKEND_STATUS" == "OFFLINE" ]; then
        echo -e "   ${RED}✗ Retro UI Backend is offline${NC}"
        echo "      Start with: cd retro-ui && ./start.sh"
    fi
    
    if [ "$ACTION_STATUS" == "OFFLINE" ]; then
        echo -e "   ${RED}✗ Action Server is offline${NC}"
        echo "      Start with: action-server start --port 8082"
    fi
    
    if [ "$DB_STATUS" == "MISSING" ]; then
        echo -e "   ${RED}✗ Database not found${NC}"
        echo "      Check path: ../src/linkedin_jobs.sqlite"
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Process information
if [ "$BACKEND_STATUS" == "ONLINE" ]; then
    BACKEND_PID=$(lsof -t -i:3001 2>/dev/null)
    if [ ! -z "$BACKEND_PID" ]; then
        echo "🔧 Process Info:"
        echo "   Backend PID: $BACKEND_PID"
        ps -p $BACKEND_PID -o pid,cmd,etime,%cpu,%mem 2>/dev/null | tail -1
    fi
fi

echo ""
