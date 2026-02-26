#!/bin/bash
# Install Node.js dependencies locally for IDE support
# This is optional - the app runs in Docker and doesn't need local node_modules

echo "Installing local dependencies for IDE support..."
echo ""
echo "Note: You need Node.js 18+ and npm installed locally."
echo "If you don't have Node.js, install it from https://nodejs.org/"
echo ""

if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install Node.js first."
    echo ""
    echo "On macOS, you can use:"
    echo "  brew install node"
    echo ""
    exit 1
fi

npm install

echo ""
echo "✅ Dependencies installed! TypeScript errors in VS Code should now be resolved."
