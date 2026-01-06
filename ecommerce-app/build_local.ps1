$services = @("catalog-service", "inventory-service", "user-service")
$root = Get-Location

foreach ($service in $services) {
    Write-Host "Building $service..."
    $servicePath = Join-Path $root "services\$service"
    
    # Check if Dockerfile exists
    if (Test-Path "$servicePath\Dockerfile") {
        Set-Location $servicePath
        docker build -t "aiops/$service`:latest" .
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Successfully built $service" -ForegroundColor Green
        } else {
            Write-Host "Failed to build $service" -ForegroundColor Red
            exit 1
        }
        Set-Location $root
    } else {
        Write-Host "Dockerfile not found for $service in $servicePath" -ForegroundColor Yellow
    }
}

Write-Host "All services built successfully!" -ForegroundColor Green
