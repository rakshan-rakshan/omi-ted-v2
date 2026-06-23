param(
    [Parameter(Mandatory=$true)]
    [string]$Host
)

Write-Host "→ Deploying to $Host..."
ssh "$Host" @'
  set -e
  echo '1. Installing Docker...'
  command -v docker >/dev/null 2>&1 || {
    apt-get update && apt-get install -y docker.io docker-compose-plugin
  }

  echo '2. Cloning/updating repo...'
  mkdir -p /opt/omitred
  cd /opt/omitred
  if [ -d .git ]; then
    git pull origin main
  else
    git clone https://github.com/rakshan-rakshan/omi-ted-v2 .
  fi

  echo '3. Creating .env if not exists...'
  [ -f .env ] || cp .env.example .env

  echo '4. Starting services...'
  docker compose up -d --build

  echo '5. Cleaning up...'
  docker system prune -f

  echo '6. Health checks...'
  sleep 10
  curl -sf http://localhost:8000/health && echo '✓ Backend healthy' || echo '✗ Backend failed'
  curl -sf http://localhost:3000 && echo '✓ Frontend healthy' || echo '✗ Frontend failed'

  echo '→ Done.'
'@
