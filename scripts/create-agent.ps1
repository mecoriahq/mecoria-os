param(
    [Parameter(Mandatory = $true)]
    [string]$AgentName
)

$templatePath = Join-Path $PSScriptRoot "..\agents\_template"
$agentPath = Join-Path $PSScriptRoot "..\agents\$AgentName"

if (Test-Path $agentPath) {
    Write-Host "Agent '$AgentName' already exists."
    exit
}

Copy-Item -Path $templatePath -Destination $agentPath -Recurse

Write-Host "Agent '$AgentName' created successfully."