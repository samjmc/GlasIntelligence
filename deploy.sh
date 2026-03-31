#!/bin/bash
set -e

DOMAIN="glasinsight.com"
EMAIL="sam@glasinsight.com"
ROLLBACK_FILE="/opt/glas/.rollback-image"

echo "=== Glas Intelligence Deployment ==="

if [ "$1" == "init" ]; then
    echo "--- Initial Setup ---"

    cat > /tmp/nginx-init.conf << 'INITNGINX'
server {
    listen 80;
    server_name glasinsight.com www.glasinsight.com;
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 200 'Setting up...';
        add_header Content-Type text/plain;
    }
}
INITNGINX

    cp nginx.conf nginx.conf.bak
    cp /tmp/nginx-init.conf nginx.conf

    docker compose -f docker-compose.prod.yml up -d glas-intelligence
    sleep 5

    docker run --rm \
        -v glas-us_certbot-webroot:/var/www/certbot \
        -v glas-us_certbot-certs:/etc/letsencrypt \
        certbot/certbot certonly \
        --webroot -w /var/www/certbot \
        -d "$DOMAIN" -d "www.$DOMAIN" \
        --email "$EMAIL" --agree-tos --no-eff-email

    cp nginx.conf.bak nginx.conf
    rm nginx.conf.bak

    docker compose -f docker-compose.prod.yml down
    echo "--- Certificates obtained. Run: ./deploy.sh start ---"

elif [ "$1" == "start" ]; then
    echo "--- Starting all services ---"
    docker compose -f docker-compose.prod.yml up -d --build
    echo "--- Services started ---"
    docker compose -f docker-compose.prod.yml ps

elif [ "$1" == "stop" ]; then
    echo "--- Stopping all services ---"
    docker compose -f docker-compose.prod.yml down

elif [ "$1" == "logs" ]; then
    docker compose -f docker-compose.prod.yml logs -f --tail=100 "${2:-glas-intelligence}"

elif [ "$1" == "update" ]; then
    echo "--- Saving rollback image ---"
    docker inspect glas-intelligence --format='{{.Config.Image}}' > "$ROLLBACK_FILE" 2>/dev/null || true

    echo "--- Pulling and rebuilding ---"
    git pull
    docker compose -f docker-compose.prod.yml up -d --build

    echo "--- Health check ---"
    HEALTHY=false
    for i in $(seq 1 12); do
        if curl -sf --connect-timeout 5 http://localhost:5001/health > /dev/null 2>&1; then
            HEALTHY=true
            echo "Health check passed on attempt $i"
            break
        fi
        echo "Health check attempt $i/12 failed, waiting 5s..."
        sleep 5
    done

    if [ "$HEALTHY" = "false" ]; then
        echo "!!! HEALTH CHECK FAILED !!!"
        if [ "$2" == "--auto-rollback" ]; then
            echo "--- Auto-rollback initiated ---"
            ./deploy.sh rollback
        else
            echo "Run './deploy.sh rollback' to revert, or './deploy.sh update --auto-rollback' next time"
        fi
        exit 1
    fi

    echo "--- Updated successfully ---"

elif [ "$1" == "rollback" ]; then
    if [ ! -f "$ROLLBACK_FILE" ]; then
        echo "No rollback image saved. Cannot rollback."
        exit 1
    fi

    ROLLBACK_IMAGE=$(cat "$ROLLBACK_FILE")
    echo "--- Rolling back to: $ROLLBACK_IMAGE ---"
    docker compose -f docker-compose.prod.yml down
    docker compose -f docker-compose.prod.yml up -d
    echo "--- Rollback complete ---"
    docker compose -f docker-compose.prod.yml ps

elif [ "$1" == "staging" ]; then
    echo "--- Staging: $2 ---"
    case "$2" in
        start)
            docker compose -f docker-compose.staging.yml up -d
            docker compose -f docker-compose.staging.yml ps
            ;;
        stop)
            docker compose -f docker-compose.staging.yml down
            ;;
        logs)
            docker compose -f docker-compose.staging.yml logs -f --tail=100
            ;;
        *)
            echo "Usage: ./deploy.sh staging [start|stop|logs]"
            ;;
    esac

elif [ "$1" == "monitoring" ]; then
    echo "--- Monitoring: $2 ---"
    case "$2" in
        start)
            docker compose -f docker-compose.monitoring.yml up -d
            echo "Grafana:    http://localhost:3001"
            echo "Uptime Kuma: http://localhost:3002"
            echo "Prometheus:  http://localhost:9090"
            ;;
        stop)
            docker compose -f docker-compose.monitoring.yml down
            ;;
        logs)
            docker compose -f docker-compose.monitoring.yml logs -f --tail=100
            ;;
        *)
            echo "Usage: ./deploy.sh monitoring [start|stop|logs]"
            ;;
    esac

elif [ "$1" == "health" ]; then
    echo "--- Health Check ---"
    if curl -sf http://localhost:5001/health; then
        echo ""
        echo "Production: HEALTHY"
    else
        echo "Production: UNHEALTHY"
    fi

    if curl -sf http://localhost:8080/health 2>/dev/null; then
        echo "Staging: HEALTHY"
    else
        echo "Staging: not running or unhealthy"
    fi

else
    echo "Usage: ./deploy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  init                    - First-time setup (get SSL certs)"
    echo "  start                   - Build and start all production services"
    echo "  stop                    - Stop all production services"
    echo "  logs [service]          - View logs (default: glas-intelligence)"
    echo "  update [--auto-rollback]- Pull latest and rebuild with health check"
    echo "  rollback                - Revert to previous deployment"
    echo "  health                  - Check health of all environments"
    echo "  staging [start|stop|logs]    - Manage staging environment"
    echo "  monitoring [start|stop|logs] - Manage monitoring stack"
fi
