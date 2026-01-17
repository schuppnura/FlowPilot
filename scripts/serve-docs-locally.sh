#!/bin/bash
# Serve FlowPilot documentation locally

# Add Python bin to PATH if needed
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

echo "Starting MkDocs development server..."
echo "Documentation will be available at: http://127.0.0.1:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

mkdocs serve
