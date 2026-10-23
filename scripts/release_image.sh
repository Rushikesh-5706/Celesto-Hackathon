#!/usr/bin/env bash
set -euo pipefail

IMAGE="rushi5706/celesto-hackathon-api"
VERSION="${1:-1.0.0}"

cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

wait_healthy() {
  local service="$1" cid status
  for _ in $(seq 1 60); do
    cid="$(docker compose ps -q "$service")"
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo starting)"
    if [ "$status" = "healthy" ]; then
      echo "$service is healthy"
      return 0
    fi
    sleep 5
  done
  echo "$service did not become healthy within 5 minutes" >&2
  docker compose logs --tail 80 "$service" >&2
  return 1
}

docker compose config -q
docker compose build api
docker compose up -d
wait_healthy ledger
wait_healthy api

echo "--- contract checks"
curl -fsS http://localhost:8080/health
echo
curl -fsS http://localhost:8080/api/runs | grep -q "sbx-seeddemo1" && echo "seed row present"

created="$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8080/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"run-release-check","sandbox_name":"sbx-releasechk1","problem_id":"release-check","state":"created","execution_target":"celesto_sandbox"}')"
rejected="$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8080/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"run-release-bad","sandbox_name":"sbx-releasechk2","problem_id":"release-check","state":"created","execution_target":"host"}')"
echo "valid post: $created (expect 201)"
echo "host target: $rejected (expect 400)"
[ "$created" = "201" ] && [ "$rejected" = "400" ]

docker compose down -v

echo "--- pushing $IMAGE:$VERSION and :latest (linux/amd64 and linux/arm64)"
docker info 2>/dev/null | grep -q "Username:" || docker login -u rushi5706
docker buildx inspect celesto-builder >/dev/null 2>&1 || docker buildx create --name celesto-builder --driver docker-container --use
docker buildx use celesto-builder
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "$IMAGE:$VERSION" \
  -t "$IMAGE:latest" \
  --push .

echo "pushed $IMAGE:$VERSION and $IMAGE:latest"
