#!/bin/bash
# Deploy FlowPilot documentation to GitHub Pages

# Add Python bin to PATH if needed
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

echo "Building and deploying documentation to GitHub Pages..."
echo ""

# Build and deploy
mkdocs gh-deploy --clean --force --message "Update documentation [ci skip]"

echo ""
echo "Documentation deployed successfully!"
echo "It will be available at your GitHub Pages URL shortly."
