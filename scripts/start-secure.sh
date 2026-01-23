#!/bin/bash
# Quick start script for MinIO and Keycloak integration

set -e

echo "=================================================="
echo "  Workspace MinIO + Keycloak Setup"
echo "=================================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and set secure passwords!"
    echo "    Press Enter to continue after editing .env..."
    read -r
fi

echo "Building workspace image..."
docker compose -f compose.yml build

echo ""
echo "Starting all services..."
docker compose -f compose.minio.keycloak.yml up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 10

# Wait for Keycloak
echo "Waiting for Keycloak to be ready..."
until curl -sf http://localhost:8180/health/ready > /dev/null 2>&1; do
    echo -n "."
    sleep 5
done
echo " ✓"

# Wait for MinIO
echo "Waiting for MinIO to be ready..."
until curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; do
    echo -n "."
    sleep 5
done
echo " ✓"

# Wait for Authorization Proxy
echo "Waiting for Authorization Proxy to be ready..."
until curl -sf http://localhost:8300/health > /dev/null 2>&1; do
    echo -n "."
    sleep 5
done
echo " ✓"

echo ""
echo "=================================================="
echo "  🎉 Setup Complete!"
echo "=================================================="
echo ""
echo "Services are now available:"
echo ""
echo "  Keycloak Admin Console:"
echo "    → http://localhost:8180"
echo "    Username: admin"
echo "    Password: (from .env KEYCLOAK_ADMIN_PASSWORD)"
echo ""
echo "  MinIO Console:"
echo "    → http://localhost:9001"
echo "    Username: minioadmin"
echo "    Password: (from .env MINIO_ROOT_PASSWORD)"
echo ""
echo "  User1 Workspace:"
echo "    → http://localhost:8100"
echo "    Username: user1"
echo "    Password: user1password"
echo ""
echo "  User2 Workspace:"
echo "    → http://localhost:8200"
echo "    Username: user2"
echo "    Password: user2password"
echo ""
echo "  Authorization Proxy API:"
echo "    → http://localhost:8300/docs"
echo ""
echo "=================================================="
echo ""
echo "User Permissions:"
echo "  • user1: Read-only access to common space"
echo "  • user2: Read-write access to common space"
echo "  • admin: Full access to all resources"
echo ""
echo "View logs:"
echo "  docker compose -f compose.minio.keycloak.yml logs -f"
echo ""
echo "Stop services:"
echo "  docker compose -f compose.minio.keycloak.yml down"
echo ""
echo "For full documentation, see MINIO_KEYCLOAK.md"
echo "=================================================="
