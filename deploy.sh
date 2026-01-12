#!/bin/bash

# Production Deployment Script for OKX Trading Bot

set -e  # Exit on any error

echo "🚀 Starting OKX Trading Bot Production Deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.production .env
    echo "📝 Please edit .env file with your production values:"
    echo "   - DATABASE_URL"
    echo "   - OKX API credentials"
    echo "   - SESSION_SECRET"
    echo "   - POSTGRES_PASSWORD"
    read -p "Press Enter after editing .env file..."
fi

# Load environment variables
source .env

# Validate required environment variables
required_vars=("POSTGRES_PASSWORD" "OKX_DEMO_API_KEY" "OKX_DEMO_API_SECRET" "OKX_DEMO_PASSPHRASE" "SESSION_SECRET")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set in .env file"
        exit 1
    fi
done

echo "✅ Environment variables validated"

# Create necessary directories
mkdir -p logs
mkdir -p backups

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose down

# Pull latest images
echo "📥 Pulling latest images..."
docker-compose pull

# Build application image
echo "🏗️  Building application image..."
docker-compose build --no-cache

# Start services
echo "🚀 Starting services..."
docker-compose up -d

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10

# Check service health
echo "🔍 Checking service health..."
docker-compose ps

# Show logs
echo "📋 Recent logs:"
docker-compose logs --tail=20

echo "✅ Deployment completed!"
echo "🌐 Application should be available at: http://localhost:8501"
echo "📊 Database is running on: localhost:5432"

# Optional: Create database backup
echo "💾 Creating initial database backup..."
docker-compose exec -T postgres pg_dump -U postgres trading_bot > "backups/initial_backup_$(date +%Y%m%d_%H%M%S).sql"

echo "🎉 OKX Trading Bot is now running in production mode!"
echo ""
echo "📚 Useful commands:"
echo "   View logs: docker-compose logs -f"
echo "   Stop services: docker-compose down"
echo "   Restart services: docker-compose restart"
echo "   Database backup: docker-compose exec postgres pg_dump -U postgres trading_bot > backup.sql"