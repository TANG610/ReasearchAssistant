$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $PSScriptRoot "backups"
New-Item -ItemType Directory -Force $backupDir | Out-Null
docker compose -f (Join-Path $PSScriptRoot "docker-compose.yml") exec -T postgres pg_dump -U ${env:POSTGRES_USER} ${env:POSTGRES_DB} > (Join-Path $backupDir "research-$timestamp.sql")

$knowledgeBaseDir = $env:KNOWLEDGE_BASE_HOST_DIR
if (-not $knowledgeBaseDir) {
    $knowledgeBaseDir = "/data/paper-agent/knowledge_base"
}
Write-Output "Postgres backup written. Knowledge base directory is $knowledgeBaseDir; back it up with your server file backup workflow."
