#!/bin/bash
# Automated installer for cxasgemmaclaw CLI
set -e

# Dynamically resolve the active repository root path relative to the script location
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🚀 Automating cxasgemmaclaw installation..."
cd "${REPO_DIR}/gemmaclaw"

echo "📦 Installing dependencies..."
npm install

echo "🛠️ Compiling TypeScript..."
npm run build

echo "🔗 Registering global binary link..."
npm link --force

echo "✅ Installation successful! You can now run 'cxasgemmaclaw' or 'cgem' globally from anywhere!"
