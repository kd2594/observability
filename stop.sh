#!/bin/bash

echo "🛑 Stopping FlexAI Visibility Platform..."

docker-compose down

echo "✅ All services stopped"
echo ""
echo "To remove all data volumes, run: docker-compose down -v"
