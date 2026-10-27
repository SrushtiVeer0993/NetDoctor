$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"
$AgentScript = Join-Path $ProjectRoot "backend\host_agent\windows_agent.py"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install/start Docker Desktop, then run this script again."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install Python 3, then run this script again."
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Missing .env. Copy .env.example to .env and configure the required settings first."
}

$envLines = [System.Collections.Generic.List[string]]::new()
$envLines.AddRange([string[]](Get-Content -LiteralPath $EnvFile))
$tokenLineIndex = -1
for ($i = 0; $i -lt $envLines.Count; $i++) {
    if ($envLines[$i] -match '^NETDOCTOR_AGENT_TOKEN\s*=') {
        $tokenLineIndex = $i
        break
    }
}

$token = if ($tokenLineIndex -ge 0) {
    ($envLines[$tokenLineIndex] -split '=', 2)[1].Trim()
} else {
    ""
}
if ($token.Length -lt 32) {
    $randomBytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    $token = [Convert]::ToBase64String($randomBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    if ($tokenLineIndex -ge 0) {
        $envLines[$tokenLineIndex] = "NETDOCTOR_AGENT_TOKEN=$token"
    } else {
        $envLines.Add("NETDOCTOR_AGENT_TOKEN=$token")
    }
    Set-Content -LiteralPath $EnvFile -Value $envLines -Encoding utf8
    Write-Host "Created a private host-agent token in .env."
}

Write-Host "Starting NetDoctor services..."
Push-Location $ProjectRoot
try {
    docker compose up -d --build db backend
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed to start the database or backend." }
    docker compose up -d frontend
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "The frontend could not start (its port may already be in use). The backend and Windows host agent will continue starting."
    }
} finally {
    Pop-Location
}

$env:NETDOCTOR_AGENT_TOKEN = $token
Write-Host "Starting Windows host diagnostics. Keep this window open while using NetDoctor."
Write-Host "Diagnostics will use the active Windows adapter and its physical router gateway."
python $AgentScript
