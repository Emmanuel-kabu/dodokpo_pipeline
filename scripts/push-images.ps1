# Build and push the three Lambda container images to ECR.
#
# Reads ECR repository URLs from `terraform output` in ./infra, logs into the
# ECR registry, and runs `docker compose build` + `docker compose push` with
# image URIs set in the environment.
#
# Usage:
#   .\scripts\push-images.ps1                       # tag=bootstrap, region=eu-west-1
#   .\scripts\push-images.ps1 -Tag v1.2.3
#   .\scripts\push-images.ps1 -Tag (git rev-parse --short HEAD)
#
# Prereqs: docker, aws cli, terraform; ECR repos already applied
# (`terraform -chdir=infra apply -target=module.lambda.aws_ecr_repository.this`).

[CmdletBinding()]
param(
  [string]$Tag    = "bootstrap",
  [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Reading ECR URLs from terraform output..." -ForegroundColor Cyan
$bronzeUrl = (terraform -chdir="$repoRoot\infra" output -raw bronze_ecr_url)
$silverUrl = (terraform -chdir="$repoRoot\infra" output -raw silver_ecr_url)
$goldUrl   = (terraform -chdir="$repoRoot\infra" output -raw gold_ecr_url)

if (-not $bronzeUrl) {
  throw "bronze_ecr_url is empty. Apply the ECR repos first: terraform -chdir=infra apply -target=module.lambda.aws_ecr_repository.this"
}

$registry = ($bronzeUrl -split '/')[0]
Write-Host "  bronze: ${bronzeUrl}:${Tag}"
Write-Host "  silver: ${silverUrl}:${Tag}"
Write-Host "  gold:   ${goldUrl}:${Tag}"

Write-Host "`nLogging into ECR registry $registry..." -ForegroundColor Cyan
$loginPwd = aws ecr get-login-password --region $Region
if ($LASTEXITCODE -ne 0) { throw "aws ecr get-login-password failed" }
$loginPwd | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { throw "docker login failed" }

$env:BRONZE_IMAGE_URI = "${bronzeUrl}:${Tag}"
$env:SILVER_IMAGE_URI = "${silverUrl}:${Tag}"
$env:GOLD_IMAGE_URI   = "${goldUrl}:${Tag}"

# AWS Lambda only accepts Docker v2 manifests, not OCI indexes. We bypass
# `docker compose build/push` (which wraps images in an OCI index by default
# for SBOM/provenance attestations) and call buildx directly with
# --provenance=false. This forces a single-platform Docker v2 manifest.
$builds = @(
  @{ Name = "bronze"; Tag = "${bronzeUrl}:${Tag}"; Context = "$repoRoot\src\lambda" }
  @{ Name = "silver"; Tag = "${silverUrl}:${Tag}"; Context = "$repoRoot\src\lambda\silver" }
  @{ Name = "gold";   Tag = "${goldUrl}:${Tag}";   Context = "$repoRoot\src\lambda\gold" }
)

foreach ($b in $builds) {
  Write-Host "`nBuilding+pushing $($b.Name) ($($b.Tag))..." -ForegroundColor Cyan
  docker buildx build --provenance=false --platform=linux/amd64 --push -t $b.Tag $b.Context
  if ($LASTEXITCODE -ne 0) { throw "buildx build/push failed for $($b.Name)" }
}

Write-Host "`nDone. Pushed:" -ForegroundColor Green
Write-Host "  $env:BRONZE_IMAGE_URI"
Write-Host "  $env:SILVER_IMAGE_URI"
Write-Host "  $env:GOLD_IMAGE_URI"
