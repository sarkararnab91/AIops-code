$AppUrl = "https://traditional-bxf2fbbedsh6egay.canadacentral-01.azurewebsites.net" # actual URL
Write-Host "Monitoring $AppUrl - Sending traffic..." -ForegroundColor Green

while($true) {
    try {
        $response = Invoke-WebRequest -Uri $AppUrl -Method Get -UseBasicParsing
        Write-Host "$(Get-Date): Success (HTTP $($response.StatusCode))" -ForegroundColor Gray
    } catch {
        Write-Host "$(Get-Date): Failed ($($_.Exception.Message))" -ForegroundColor Red
    }
    Start-Sleep -Seconds 1
}
