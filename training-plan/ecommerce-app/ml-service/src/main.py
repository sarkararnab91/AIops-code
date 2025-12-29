"""
ML Service for AIOps
FastAPI service for anomaly detection and prediction
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model storage
models = {}
scalers = {}


class MetricData(BaseModel):
    """Input metrics for anomaly detection."""
    service_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    request_rate: float = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    latency_p50: float = Field(ge=0)
    latency_p95: float = Field(ge=0)
    latency_p99: float = Field(ge=0)


class BatchMetricData(BaseModel):
    """Batch metrics for training."""
    service_name: str
    metrics: list[MetricData]


class AnomalyResult(BaseModel):
    """Result of anomaly detection."""
    service_name: str
    timestamp: datetime
    is_anomaly: bool
    anomaly_score: float
    contributing_factors: list[str]
    confidence: float


class TrainingResult(BaseModel):
    """Result of model training."""
    service_name: str
    samples_used: int
    model_version: str
    trained_at: datetime
    metrics: dict


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    models_loaded: list[str]
    uptime_seconds: float


# Track uptime
start_time = datetime.utcnow()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting ML Service...")
    
    # Load pre-trained models if available
    model_dir = os.getenv("MODEL_DIR", "./models")
    if os.path.exists(model_dir):
        for filename in os.listdir(model_dir):
            if filename.endswith("_model.joblib"):
                service_name = filename.replace("_model.joblib", "")
                try:
                    models[service_name] = joblib.load(os.path.join(model_dir, filename))
                    scaler_path = os.path.join(model_dir, f"{service_name}_scaler.joblib")
                    if os.path.exists(scaler_path):
                        scalers[service_name] = joblib.load(scaler_path)
                    logger.info(f"Loaded model for {service_name}")
                except Exception as e:
                    logger.error(f"Failed to load model for {service_name}: {e}")
    
    yield
    
    logger.info("Shutting down ML Service...")


app = FastAPI(
    title="AIOps ML Service",
    description="Machine Learning service for anomaly detection and prediction",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        models_loaded=list(models.keys()),
        uptime_seconds=(datetime.utcnow() - start_time).total_seconds()
    )


@app.post("/predict", response_model=AnomalyResult)
async def predict_anomaly(data: MetricData):
    """Predict if the given metrics indicate an anomaly."""
    
    service_name = data.service_name
    
    # Check if model exists
    if service_name not in models:
        # Use default thresholds if no trained model
        return _rule_based_detection(data)
    
    model = models[service_name]
    scaler = scalers.get(service_name)
    
    # Prepare features
    features = np.array([[
        data.cpu_percent,
        data.memory_percent,
        data.request_rate,
        data.error_rate * 100,  # Scale to percentage
        data.latency_p50,
        data.latency_p95,
        data.latency_p99
    ]])
    
    # Scale features
    if scaler:
        features = scaler.transform(features)
    
    # Predict
    prediction = model.predict(features)[0]
    score = model.decision_function(features)[0]
    
    # Determine contributing factors
    factors = _analyze_contributing_factors(data)
    
    is_anomaly = prediction == -1
    
    # Convert score to probability-like confidence
    confidence = 1 / (1 + np.exp(score))  # Sigmoid transformation
    
    return AnomalyResult(
        service_name=service_name,
        timestamp=data.timestamp,
        is_anomaly=is_anomaly,
        anomaly_score=float(-score),  # Negate so higher = more anomalous
        contributing_factors=factors if is_anomaly else [],
        confidence=float(confidence if is_anomaly else 1 - confidence)
    )


def _rule_based_detection(data: MetricData) -> AnomalyResult:
    """Fallback rule-based anomaly detection."""
    
    factors = []
    anomaly_score = 0.0
    
    # Check CPU
    if data.cpu_percent > 85:
        factors.append(f"High CPU: {data.cpu_percent}%")
        anomaly_score += (data.cpu_percent - 85) / 15
    
    # Check Memory
    if data.memory_percent > 85:
        factors.append(f"High Memory: {data.memory_percent}%")
        anomaly_score += (data.memory_percent - 85) / 15
    
    # Check Error Rate
    if data.error_rate > 0.05:
        factors.append(f"High Error Rate: {data.error_rate*100:.1f}%")
        anomaly_score += (data.error_rate - 0.05) / 0.1 * 2
    
    # Check Latency
    if data.latency_p99 > 2000:
        factors.append(f"High P99 Latency: {data.latency_p99}ms")
        anomaly_score += (data.latency_p99 - 2000) / 3000
    
    is_anomaly = len(factors) > 0
    
    return AnomalyResult(
        service_name=data.service_name,
        timestamp=data.timestamp,
        is_anomaly=is_anomaly,
        anomaly_score=min(1.0, anomaly_score),
        contributing_factors=factors,
        confidence=min(0.95, 0.5 + anomaly_score * 0.3)
    )


def _analyze_contributing_factors(data: MetricData) -> list[str]:
    """Analyze which metrics are contributing to the anomaly."""
    
    factors = []
    
    # Define thresholds
    thresholds = {
        "cpu_percent": (70, 85, "CPU"),
        "memory_percent": (75, 90, "Memory"),
        "error_rate": (0.02, 0.05, "Error Rate"),
        "latency_p99": (1000, 2000, "P99 Latency")
    }
    
    for metric, (warning, critical, name) in thresholds.items():
        value = getattr(data, metric)
        
        if metric == "error_rate":
            value_str = f"{value*100:.2f}%"
        elif "latency" in metric:
            value_str = f"{value}ms"
        else:
            value_str = f"{value}%"
        
        if value >= critical:
            factors.append(f"Critical {name}: {value_str}")
        elif value >= warning:
            factors.append(f"Warning {name}: {value_str}")
    
    return factors


@app.post("/train", response_model=TrainingResult)
async def train_model(data: BatchMetricData, background_tasks: BackgroundTasks):
    """Train an anomaly detection model for a service."""
    
    if len(data.metrics) < 100:
        raise HTTPException(
            status_code=400,
            detail="Need at least 100 samples for training"
        )
    
    service_name = data.service_name
    
    # Prepare training data
    X = np.array([[
        m.cpu_percent,
        m.memory_percent,
        m.request_rate,
        m.error_rate * 100,
        m.latency_p50,
        m.latency_p95,
        m.latency_p99
    ] for m in data.metrics])
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train Isolation Forest
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,  # Expect 5% anomalies
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_scaled)
    
    # Store model and scaler
    models[service_name] = model
    scalers[service_name] = scaler
    
    # Save to disk in background
    background_tasks.add_task(_save_model, service_name, model, scaler)
    
    # Calculate training metrics
    predictions = model.predict(X_scaled)
    anomaly_ratio = (predictions == -1).sum() / len(predictions)
    
    version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    return TrainingResult(
        service_name=service_name,
        samples_used=len(data.metrics),
        model_version=version,
        trained_at=datetime.utcnow(),
        metrics={
            "anomaly_ratio": float(anomaly_ratio),
            "feature_count": X.shape[1],
            "n_estimators": 100
        }
    )


async def _save_model(service_name: str, model, scaler):
    """Save model and scaler to disk."""
    model_dir = os.getenv("MODEL_DIR", "./models")
    os.makedirs(model_dir, exist_ok=True)
    
    try:
        joblib.dump(model, os.path.join(model_dir, f"{service_name}_model.joblib"))
        joblib.dump(scaler, os.path.join(model_dir, f"{service_name}_scaler.joblib"))
        logger.info(f"Saved model for {service_name}")
    except Exception as e:
        logger.error(f"Failed to save model for {service_name}: {e}")


@app.post("/batch-predict", response_model=list[AnomalyResult])
async def batch_predict(data: BatchMetricData):
    """Predict anomalies for a batch of metrics."""
    
    results = []
    for metric in data.metrics:
        metric.service_name = data.service_name
        result = await predict_anomaly(metric)
        results.append(result)
    
    return results


class ForecastRequest(BaseModel):
    """Request for metric forecasting."""
    service_name: str
    metric_name: str = Field(..., description="Metric to forecast: cpu, memory, latency, error_rate")
    historical_values: list[float]
    periods: int = Field(default=12, ge=1, le=48)


class ForecastResult(BaseModel):
    """Result of metric forecasting."""
    service_name: str
    metric_name: str
    forecast: list[float]
    upper_bound: list[float]
    lower_bound: list[float]
    trend: str


@app.post("/forecast", response_model=ForecastResult)
async def forecast_metric(request: ForecastRequest):
    """Forecast future metric values using simple moving average."""
    
    values = np.array(request.historical_values)
    
    if len(values) < 10:
        raise HTTPException(
            status_code=400,
            detail="Need at least 10 historical values for forecasting"
        )
    
    # Simple exponential smoothing forecast
    alpha = 0.3  # Smoothing factor
    
    # Calculate smoothed values
    smoothed = [values[0]]
    for i in range(1, len(values)):
        smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[-1])
    
    # Calculate trend
    trend = (smoothed[-1] - smoothed[0]) / len(smoothed)
    
    # Generate forecast
    forecast = []
    last_smoothed = smoothed[-1]
    for i in range(request.periods):
        forecast_value = last_smoothed + trend * (i + 1)
        forecast.append(max(0, forecast_value))  # Non-negative
    
    # Calculate confidence bounds
    std = np.std(values)
    upper = [f + 1.96 * std for f in forecast]
    lower = [max(0, f - 1.96 * std) for f in forecast]
    
    # Determine trend direction
    if trend > std * 0.1:
        trend_direction = "increasing"
    elif trend < -std * 0.1:
        trend_direction = "decreasing"
    else:
        trend_direction = "stable"
    
    return ForecastResult(
        service_name=request.service_name,
        metric_name=request.metric_name,
        forecast=forecast,
        upper_bound=upper,
        lower_bound=lower,
        trend=trend_direction
    )


class CorrelationRequest(BaseModel):
    """Request for alert correlation."""
    alerts: list[dict]
    time_window_minutes: int = Field(default=15, ge=1, le=60)


class CorrelatedAlertGroup(BaseModel):
    """Group of correlated alerts."""
    group_id: str
    probable_root_cause: str
    affected_services: list[str]
    alerts: list[dict]
    confidence: float


@app.post("/correlate-alerts", response_model=list[CorrelatedAlertGroup])
async def correlate_alerts(request: CorrelationRequest):
    """Correlate related alerts to reduce noise."""
    
    alerts = request.alerts
    time_window = timedelta(minutes=request.time_window_minutes)
    
    if not alerts:
        return []
    
    # Group alerts by time proximity and service relationships
    groups = []
    used_alerts = set()
    
    # Service dependency map
    dependencies = {
        "api-gateway": ["catalog-service", "order-service", "cart-service", "user-service"],
        "order-service": ["inventory-service", "payment-service", "cart-service"],
        "cart-service": ["catalog-service", "inventory-service"],
        "catalog-service": ["inventory-service"]
    }
    
    for i, alert in enumerate(alerts):
        if i in used_alerts:
            continue
        
        group = [alert]
        used_alerts.add(i)
        
        alert_time = datetime.fromisoformat(alert.get("timestamp", datetime.utcnow().isoformat()))
        alert_service = alert.get("service", "unknown")
        
        # Find related alerts
        for j, other_alert in enumerate(alerts):
            if j in used_alerts:
                continue
            
            other_time = datetime.fromisoformat(other_alert.get("timestamp", datetime.utcnow().isoformat()))
            other_service = other_alert.get("service", "unknown")
            
            # Check time proximity
            if abs((other_time - alert_time).total_seconds()) > time_window.total_seconds():
                continue
            
            # Check service relationship
            is_related = (
                alert_service == other_service or
                other_service in dependencies.get(alert_service, []) or
                alert_service in dependencies.get(other_service, [])
            )
            
            if is_related:
                group.append(other_alert)
                used_alerts.add(j)
        
        if group:
            # Determine probable root cause
            services = list(set(a.get("service", "unknown") for a in group))
            root_cause = _determine_root_cause(group, dependencies)
            
            groups.append(CorrelatedAlertGroup(
                group_id=f"group-{len(groups)+1}",
                probable_root_cause=root_cause,
                affected_services=services,
                alerts=group,
                confidence=min(0.95, 0.5 + len(group) * 0.1)
            ))
    
    return groups


def _determine_root_cause(alerts: list[dict], dependencies: dict) -> str:
    """Determine probable root cause from correlated alerts."""
    
    services = [a.get("service", "unknown") for a in alerts]
    alert_types = [a.get("type", "unknown") for a in alerts]
    
    # Check if there's a common upstream service
    service_counts = {}
    for service in services:
        # Count how many other services depend on this one
        dependents = sum(1 for deps in dependencies.values() if service in deps)
        service_counts[service] = dependents
    
    # The service with most dependents is likely the root cause
    if service_counts:
        root_service = max(service_counts, key=service_counts.get)
        if service_counts[root_service] > 0:
            return f"Issue in {root_service} affecting downstream services"
    
    # Check for common alert type
    if "connection_error" in alert_types or "timeout" in alert_types:
        return "Network or connectivity issue"
    
    if "high_cpu" in alert_types or "high_memory" in alert_types:
        return "Resource exhaustion"
    
    return f"Multiple issues detected in {', '.join(set(services))}"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
