 = "aiopstrainacr"

Write-Host "Building Catalog Service..."
az acr build --registry $registry --image catalog-service:v1 ./services/catalog-service

Write-Host "Building Inventory Service..."
az acr build --registry $registry --image inventory-service:v1 ./services/inventory-service

Write-Host "Building User Service..."
az acr build --registry $registry --image user-service:v2 ./services/user-service

Write-Host "Building Cart Service..."
az acr build --registry $registry --image cart-service:v1 ./services/cart-service

Write-Host "Building Payment Service..."
az acr build --registry $registry --image payment-service:v1 ./services/payment-service

Write-Host "Building Order Service..."
az acr build --registry $registry --image order-service:v1 ./services/order-service

Write-Host "Building Notification Service..."
az acr build --registry $registry --image notification-service:v1 ./services/notification-service

Write-Host "All builds completed."
