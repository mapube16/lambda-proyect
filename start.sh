#!/bin/bash

# Isomorph Office - Quick Start Script
# This script starts both backend and frontend servers

echo "🏢 Starting Isomorph Office..."
echo ""

# Check if tmux is available for split terminal
if command -v tmux &> /dev/null; then
    tmux new-session -d -s hive
    
    # Backend pane
    tmux send-keys -t hive "cd backend && source venv/bin/activate 2>/dev/null || python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python main.py" Enter
    
    # Split and run frontend
    tmux split-window -h -t hive
    tmux send-keys -t hive "cd frontend && npm install && npm run dev" Enter
    
    tmux attach-session -t hive
else
    echo "Starting servers (without tmux)..."
    echo ""
    
    # Start backend in background
    echo "📦 Starting backend..."
    cd backend
    if [ ! -d "venv" ]; then
        python -m venv venv
    fi
    source venv/bin/activate 2>/dev/null || source venv/Scripts/activate
    pip install -r requirements.txt -q
    python main.py &
    BACKEND_PID=$!
    cd ..
    
    # Wait for backend
    sleep 2
    
    # Start frontend
    echo "🎨 Starting frontend..."
    cd frontend
    npm install -q
    npm run dev &
    FRONTEND_PID=$!
    cd ..
    
    echo ""
    echo "✅ Servers started!"
    echo "   Backend:  http://localhost:8000"
    echo "   Frontend: http://localhost:5173"
    echo ""
    echo "Press Ctrl+C to stop all servers"
    
    # Wait and cleanup on exit
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
    wait
fi
