#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
STORAGE_STATE="$BACKEND_DIR/storage_state.json"
ENV_FILE="$PROJECT_ROOT/.env"
PID_FILE="$PROJECT_ROOT/.sard_pids"

# Configuration
FRONTEND_PORT=3000
BACKEND_PORT=8000
MONGODB_CHECK_TIMEOUT=5

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}Sard-AI System Startup${NC}"
echo -e "${BLUE}================================================================${NC}"

# Cleanup function
cleanup() {
    echo -e "${YELLOW}\nShutting down Sard-AI...${NC}"
    if [ -f "$PID_FILE" ]; then
        while IFS= read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}Terminating process $pid${NC}"
                kill "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi
    echo -e "${YELLOW}Shutdown complete.${NC}"
}

trap cleanup EXIT INT TERM

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    echo -e "${YELLOW}Please copy .env.example to .env and configure it.${NC}"
    exit 1
fi

# Load environment variables safely
while IFS='=' read -r key value; do
    if [[ ! -z "$key" ]] && [[ ! "$key" =~ ^# ]]; then
        export "$key=$value"
    fi
done < "$ENV_FILE"

# Step 1: Check Node.js and npm
echo -e "\n${BLUE}[1/7] Checking Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}Node.js is not installed. Please install Node.js 20+ first.${NC}"
    exit 1
fi
NODE_VERSION=$(node -v)
echo -e "${GREEN}✓ Node.js $NODE_VERSION found${NC}"

if ! command -v npm &> /dev/null; then
    echo -e "${RED}npm is not installed.${NC}"
    exit 1
fi
NPM_VERSION=$(npm -v)
echo -e "${GREEN}✓ npm $NPM_VERSION found${NC}"

# Step 2: Check Python and create venv
echo -e "\n${BLUE}[2/7] Setting up Python environment...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3.11+ first.${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓ $PYTHON_VERSION found${NC}"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
fi

# Step 3: Install Node dependencies
echo -e "\n${BLUE}[3/7] Installing Node.js dependencies...${NC}"
if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
    echo -e "${YELLOW}Running npm install...${NC}"
    cd "$PROJECT_ROOT"
    npm install --prefer-offline --no-audit
    echo -e "${GREEN}✓ Node modules installed${NC}"
else
    echo -e "${GREEN}✓ Node modules already installed${NC}"
fi

# Step 4: Install Python dependencies
echo -e "\n${BLUE}[4/7] Installing Python dependencies...${NC}"
if [ ! -f "$VENV_DIR/bin/pip" ]; then
    echo -e "${RED}Virtual environment pip not found.${NC}"
    exit 1
fi

if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    echo -e "${YELLOW}Running pip install...${NC}"
    "$VENV_DIR/bin/pip" install -q --upgrade pip setuptools wheel
    "$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
    echo -e "${GREEN}✓ Python packages installed${NC}"
else
    echo -e "${RED}requirements.txt not found at $BACKEND_DIR/requirements.txt${NC}"
    exit 1
fi

# Step 5: Ensure NotebookLM authentication
echo -e "\n${BLUE}[5/7] Setting up NotebookLM authentication...${NC}"
if [ ! -f "$STORAGE_STATE" ]; then
    echo -e "${YELLOW}NotebookLM session not found. Running authentication...${NC}"
    if [ -z "$NOTEBOOKLM_EMAIL" ] || [ -z "$NOTEBOOKLM_PASSWORD" ]; then
        echo -e "${RED}Error: NOTEBOOKLM_EMAIL and NOTEBOOKLM_PASSWORD must be set in .env${NC}"
        exit 1
    fi
    cd "$BACKEND_DIR"
    "$VENV_DIR/bin/python" save_auth.py
    if [ ! -f "$STORAGE_STATE" ]; then
        echo -e "${RED}NotebookLM authentication failed.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ NotebookLM session created${NC}"
else
    echo -e "${GREEN}✓ NotebookLM session exists${NC}"
fi

# Step 6: Check MongoDB
echo -e "\n${BLUE}[6/7] Checking MongoDB connection...${NC}"
if [ -z "$MONGODB_URI" ]; then
    echo -e "${RED}MONGODB_URI not set in .env${NC}"
    exit 1
fi

# Try to connect to MongoDB with timeout
MONGO_TEST=$("$VENV_DIR/bin/python" -c "
import sys
import pymongo
from urllib.parse import urlparse
try:
    client = pymongo.MongoClient('$MONGODB_URI', serverSelectionTimeoutMS=$((MONGODB_CHECK_TIMEOUT*1000)))
    client.server_info()
    print('OK')
    sys.exit(0)
except Exception as e:
    print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1)

if [ "$MONGO_TEST" != "OK" ]; then
    echo -e "${YELLOW}Warning: Could not connect to MongoDB at $MONGODB_URI${NC}"
    echo -e "${YELLOW}Make sure MongoDB is running and accessible.${NC}"
    echo -e "${YELLOW}Continuing anyway...${NC}"
else
    echo -e "${GREEN}✓ MongoDB connection verified${NC}"
fi

# Step 7: Start services
echo -e "\n${BLUE}[7/7] Starting services...${NC}"

# Start Python backend
echo -e "${YELLOW}Starting Python backend on port $BACKEND_PORT...${NC}"
cd "$BACKEND_DIR"
nohup "$VENV_DIR/bin/python" run.py > "$PROJECT_ROOT/.sard_backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" >> "$PID_FILE"
echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"

# Wait for backend to be ready
echo -e "${YELLOW}Waiting for backend to be ready...${NC}"
BACKEND_READY=0
for i in {1..30}; do
    if curl -s http://127.0.0.1:$BACKEND_PORT/ > /dev/null 2>&1; then
        BACKEND_READY=1
        break
    fi
    sleep 1
done

if [ $BACKEND_READY -eq 0 ]; then
    echo -e "${YELLOW}Warning: Backend did not respond within 30 seconds${NC}"
    echo -e "${YELLOW}Check log at .sard_backend.log${NC}"
else
    echo -e "${GREEN}✓ Backend is responding${NC}"
fi

# Start Next.js frontend
echo -e "${YELLOW}Starting Next.js frontend on port $FRONTEND_PORT...${NC}"
cd "$PROJECT_ROOT"
nohup npm run dev > "$PROJECT_ROOT/.sard_frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" >> "$PID_FILE"
echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"

# Wait for frontend to be ready
echo -e "${YELLOW}Waiting for frontend to be ready...${NC}"
FRONTEND_READY=0
for i in {1..60}; do
    if curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
        FRONTEND_READY=1
        break
    fi
    sleep 1
done

if [ $FRONTEND_READY -eq 0 ]; then
    echo -e "${YELLOW}Warning: Frontend did not respond within 60 seconds${NC}"
    echo -e "${YELLOW}Check log at .sard_frontend.log${NC}"
else
    echo -e "${GREEN}✓ Frontend is responding${NC}"
fi

# Summary
echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}✓ Sard-AI System Started Successfully!${NC}"
echo -e "${GREEN}================================================================${NC}"
echo ""
echo -e "${BLUE}Access the application:${NC}"
echo -e "  Frontend:     ${YELLOW}http://localhost:$FRONTEND_PORT${NC}"
echo -e "  Backend API:  ${YELLOW}http://127.0.0.1:$BACKEND_PORT${NC}"
echo -e "  API Docs:     ${YELLOW}http://127.0.0.1:$BACKEND_PORT/docs${NC}"
echo ""
echo -e "${BLUE}Service logs:${NC}"
echo -e "  Backend:  ${YELLOW}$PROJECT_ROOT/.sard_backend.log${NC}"
echo -e "  Frontend: ${YELLOW}$PROJECT_ROOT/.sard_frontend.log${NC}"
echo ""
echo -e "${BLUE}To stop the system, press Ctrl+C${NC}"
echo ""

# Keep script running
wait

