# Session 20: Deploying ML Models to Production

## Learning Objectives
- Deploy ML models with FastAPI
- Implement model versioning and A/B testing
- Create monitoring for ML models
- Handle model updates and rollbacks

## Duration: 1 hour

---

## 1. Production ML Deployment

### Model Serving Service

```python
# File: training-plan/ecommerce-app/ml/deployment/model_server.py
"""
Production model serving with FastAPI.
"""

import asyncio
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json
import hashlib
import time

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import numpy as np


@dataclass
class ModelVersion:
    """Represents a model version."""
    version_id: str
    model_type: str
    created_at: datetime
    metrics: Dict[str, float]
    config: Dict[str, Any]
    path: str
    status: str = "inactive"  # active, inactive, deprecated
    traffic_percentage: float = 0.0


class ModelVersionManager:
    """
    Manages model versions for production deployment.
    """
    
    def __init__(self, storage_path: str = "/models"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.versions: Dict[str, Dict[str, ModelVersion]] = {}
        self.loaded_models: Dict[str, Any] = {}
    
    def register_version(
        self,
        model: Any,
        model_type: str,
        metrics: Dict[str, float],
        config: Dict[str, Any]
    ) -> ModelVersion:
        """Register a new model version."""
        version_id = self._generate_version_id()
        model_path = self.storage_path / f"{model_type}_{version_id}.pkl"
        
        # Save model
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        
        version = ModelVersion(
            version_id=version_id,
            model_type=model_type,
            created_at=datetime.now(),
            metrics=metrics,
            config=config,
            path=str(model_path)
        )
        
        if model_type not in self.versions:
            self.versions[model_type] = {}
        
        self.versions[model_type][version_id] = version
        
        # Save metadata
        self._save_metadata()
        
        return version
    
    def activate_version(
        self,
        model_type: str,
        version_id: str,
        traffic_percentage: float = 100.0
    ) -> None:
        """Activate a model version."""
        if model_type not in self.versions:
            raise ValueError(f"Unknown model type: {model_type}")
        
        if version_id not in self.versions[model_type]:
            raise ValueError(f"Unknown version: {version_id}")
        
        # Adjust traffic for other versions
        remaining_traffic = 100.0 - traffic_percentage
        active_count = sum(
            1 for v in self.versions[model_type].values()
            if v.status == "active" and v.version_id != version_id
        )
        
        for v in self.versions[model_type].values():
            if v.version_id == version_id:
                v.status = "active"
                v.traffic_percentage = traffic_percentage
            elif v.status == "active" and active_count > 0:
                v.traffic_percentage = remaining_traffic / active_count
        
        # Load model into memory
        self._load_model(model_type, version_id)
        self._save_metadata()
    
    def deactivate_version(
        self,
        model_type: str,
        version_id: str
    ) -> None:
        """Deactivate a model version."""
        if model_type in self.versions and version_id in self.versions[model_type]:
            version = self.versions[model_type][version_id]
            version.status = "inactive"
            version.traffic_percentage = 0.0
            
            # Redistribute traffic
            self._redistribute_traffic(model_type)
            self._save_metadata()
    
    def get_model_for_inference(
        self,
        model_type: str
    ) -> Optional[Any]:
        """Get a model for inference based on traffic routing."""
        if model_type not in self.versions:
            return None
        
        active_versions = [
            v for v in self.versions[model_type].values()
            if v.status == "active"
        ]
        
        if not active_versions:
            return None
        
        # Weighted random selection based on traffic percentage
        weights = [v.traffic_percentage for v in active_versions]
        total = sum(weights)
        
        if total == 0:
            return None
        
        rand = np.random.random() * total
        cumsum = 0
        
        for version in active_versions:
            cumsum += version.traffic_percentage
            if rand <= cumsum:
                model_key = f"{model_type}_{version.version_id}"
                if model_key not in self.loaded_models:
                    self._load_model(model_type, version.version_id)
                return self.loaded_models.get(model_key)
        
        return None
    
    def _generate_version_id(self) -> str:
        """Generate unique version ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
        return f"v{timestamp}_{random_suffix}"
    
    def _load_model(self, model_type: str, version_id: str) -> None:
        """Load model into memory."""
        version = self.versions[model_type][version_id]
        with open(version.path, 'rb') as f:
            self.loaded_models[f"{model_type}_{version_id}"] = pickle.load(f)
    
    def _redistribute_traffic(self, model_type: str) -> None:
        """Redistribute traffic among active versions."""
        active_versions = [
            v for v in self.versions[model_type].values()
            if v.status == "active"
        ]
        
        if active_versions:
            traffic_per_version = 100.0 / len(active_versions)
            for v in active_versions:
                v.traffic_percentage = traffic_per_version
    
    def _save_metadata(self) -> None:
        """Save version metadata."""
        metadata = {}
        for model_type, versions in self.versions.items():
            metadata[model_type] = {
                vid: {
                    'version_id': v.version_id,
                    'created_at': v.created_at.isoformat(),
                    'metrics': v.metrics,
                    'config': v.config,
                    'path': v.path,
                    'status': v.status,
                    'traffic_percentage': v.traffic_percentage
                }
                for vid, v in versions.items()
            }
        
        with open(self.storage_path / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)


# FastAPI Application
app = FastAPI(
    title="AIOps ML Model Server",
    version="1.0.0",
    description="Production ML model serving for AIOps"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
model_manager = ModelVersionManager()
inference_metrics: Dict[str, List[float]] = {}


# Request/Response Models
class AnomalyRequest(BaseModel):
    service: str
    metrics: Dict[str, List[float]]
    timestamp: Optional[str] = None


class AnomalyResponse(BaseModel):
    service: str
    is_anomaly: bool
    anomaly_score: float
    anomalies: List[Dict[str, Any]]
    model_version: str
    inference_time_ms: float


class HealthResponse(BaseModel):
    status: str
    models_loaded: int
    active_versions: Dict[str, List[str]]


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    active_versions = {}
    for model_type, versions in model_manager.versions.items():
        active = [v.version_id for v in versions.values() if v.status == "active"]
        if active:
            active_versions[model_type] = active
    
    return HealthResponse(
        status="healthy",
        models_loaded=len(model_manager.loaded_models),
        active_versions=active_versions
    )


@app.post("/predict/anomaly", response_model=AnomalyResponse)
async def predict_anomaly(request: AnomalyRequest):
    """Predict anomalies in metrics."""
    start_time = time.time()
    
    model = model_manager.get_model_for_inference("anomaly_detection")
    if not model:
        raise HTTPException(
            status_code=503,
            detail="No anomaly detection model available"
        )
    
    # Prepare features
    features = []
    for metric_name, values in request.metrics.items():
        arr = np.array(values)
        features.append([
            np.mean(arr),
            np.std(arr),
            np.min(arr),
            np.max(arr),
            np.percentile(arr, 50),
            np.percentile(arr, 95),
            np.percentile(arr, 99),
            arr[-1] if len(arr) > 0 else 0
        ])
    
    features = np.array(features)
    
    # Predict
    predictions = model.predict(features)
    scores = model.score_samples(features)
    
    # Build response
    anomalies = []
    for i, (metric_name, is_anomaly, score) in enumerate(zip(
        request.metrics.keys(),
        predictions == -1,
        scores
    )):
        if is_anomaly:
            anomalies.append({
                'metric': metric_name,
                'score': float(score),
                'values': request.metrics[metric_name][-5:]
            })
    
    inference_time = (time.time() - start_time) * 1000
    
    # Track metrics
    if 'inference_time' not in inference_metrics:
        inference_metrics['inference_time'] = []
    inference_metrics['inference_time'].append(inference_time)
    
    return AnomalyResponse(
        service=request.service,
        is_anomaly=len(anomalies) > 0,
        anomaly_score=float(np.min(scores)),
        anomalies=anomalies,
        model_version="current",
        inference_time_ms=inference_time
    )


@app.get("/models")
async def list_models():
    """List all model versions."""
    result = {}
    for model_type, versions in model_manager.versions.items():
        result[model_type] = [
            {
                'version_id': v.version_id,
                'created_at': v.created_at.isoformat(),
                'status': v.status,
                'traffic_percentage': v.traffic_percentage,
                'metrics': v.metrics
            }
            for v in versions.values()
        ]
    return result


@app.post("/models/{model_type}/versions/{version_id}/activate")
async def activate_model(
    model_type: str,
    version_id: str,
    traffic_percentage: float = 100.0
):
    """Activate a model version."""
    try:
        model_manager.activate_version(model_type, version_id, traffic_percentage)
        return {"status": "activated", "version_id": version_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/models/{model_type}/versions/{version_id}/deactivate")
async def deactivate_model(model_type: str, version_id: str):
    """Deactivate a model version."""
    try:
        model_manager.deactivate_version(model_type, version_id)
        return {"status": "deactivated", "version_id": version_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    """Get inference metrics."""
    result = {}
    for metric_name, values in inference_metrics.items():
        if values:
            result[metric_name] = {
                'count': len(values),
                'mean': float(np.mean(values)),
                'p50': float(np.percentile(values, 50)),
                'p95': float(np.percentile(values, 95)),
                'p99': float(np.percentile(values, 99)),
            }
    return result
```

---

## 2. Model Monitoring

### Production Model Monitoring

```python
# File: training-plan/ecommerce-app/ml/deployment/model_monitor.py
"""
Monitor ML models in production.
"""

import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque
import json


@dataclass
class PredictionRecord:
    """Record of a prediction."""
    model_type: str
    version_id: str
    timestamp: datetime
    input_features: Dict[str, Any]
    prediction: Any
    confidence: float
    inference_time_ms: float
    feedback: Optional[Dict] = None


class ModelMonitor:
    """
    Monitor ML model performance in production.
    """
    
    def __init__(
        self,
        window_size: int = 1000,
        alert_threshold_drift: float = 0.1,
        alert_threshold_accuracy: float = 0.8
    ):
        self.window_size = window_size
        self.alert_threshold_drift = alert_threshold_drift
        self.alert_threshold_accuracy = alert_threshold_accuracy
        
        self.predictions: Dict[str, deque] = {}
        self.baseline_distributions: Dict[str, Dict[str, np.ndarray]] = {}
        self.alerts: List[Dict] = []
    
    def record_prediction(
        self,
        record: PredictionRecord
    ) -> None:
        """Record a prediction for monitoring."""
        key = f"{record.model_type}_{record.version_id}"
        
        if key not in self.predictions:
            self.predictions[key] = deque(maxlen=self.window_size)
        
        self.predictions[key].append(record)
        
        # Check for issues
        self._check_data_drift(key)
        self._check_prediction_drift(key)
        self._check_latency(key)
    
    def record_feedback(
        self,
        model_type: str,
        version_id: str,
        prediction_id: str,
        actual_value: Any,
        correct: bool
    ) -> None:
        """Record feedback for a prediction."""
        key = f"{model_type}_{version_id}"
        
        if key in self.predictions:
            for record in self.predictions[key]:
                if id(record) == prediction_id:
                    record.feedback = {
                        'actual': actual_value,
                        'correct': correct,
                        'timestamp': datetime.now().isoformat()
                    }
                    break
        
        # Check accuracy
        self._check_accuracy(key)
    
    def set_baseline(
        self,
        model_type: str,
        version_id: str,
        feature_distributions: Dict[str, np.ndarray]
    ) -> None:
        """Set baseline distributions for drift detection."""
        key = f"{model_type}_{version_id}"
        self.baseline_distributions[key] = feature_distributions
    
    def _check_data_drift(self, key: str) -> None:
        """Check for data drift."""
        if key not in self.baseline_distributions:
            return
        
        records = list(self.predictions[key])
        if len(records) < 100:
            return
        
        baseline = self.baseline_distributions[key]
        
        for feature_name, baseline_dist in baseline.items():
            current_values = []
            for record in records[-100:]:
                if feature_name in record.input_features:
                    current_values.append(record.input_features[feature_name])
            
            if not current_values:
                continue
            
            current_dist = np.array(current_values)
            
            # KS test for drift
            from scipy.stats import ks_2samp
            stat, p_value = ks_2samp(baseline_dist, current_dist)
            
            if p_value < 0.05:  # Significant drift
                self._create_alert(
                    alert_type='data_drift',
                    model_key=key,
                    details={
                        'feature': feature_name,
                        'ks_statistic': float(stat),
                        'p_value': float(p_value)
                    }
                )
    
    def _check_prediction_drift(self, key: str) -> None:
        """Check for prediction distribution drift."""
        records = list(self.predictions[key])
        if len(records) < 200:
            return
        
        # Compare first half vs second half
        half = len(records) // 2
        first_half = [r.prediction for r in records[:half]]
        second_half = [r.prediction for r in records[half:]]
        
        # For binary predictions
        first_rate = np.mean([1 if p else 0 for p in first_half])
        second_rate = np.mean([1 if p else 0 for p in second_half])
        
        drift = abs(second_rate - first_rate)
        
        if drift > self.alert_threshold_drift:
            self._create_alert(
                alert_type='prediction_drift',
                model_key=key,
                details={
                    'first_half_rate': float(first_rate),
                    'second_half_rate': float(second_rate),
                    'drift': float(drift)
                }
            )
    
    def _check_latency(self, key: str) -> None:
        """Check inference latency."""
        records = list(self.predictions[key])
        if len(records) < 50:
            return
        
        recent_latencies = [r.inference_time_ms for r in records[-50:]]
        p99 = np.percentile(recent_latencies, 99)
        
        # Alert if p99 > 100ms
        if p99 > 100:
            self._create_alert(
                alert_type='high_latency',
                model_key=key,
                details={
                    'p99_latency_ms': float(p99),
                    'mean_latency_ms': float(np.mean(recent_latencies))
                }
            )
    
    def _check_accuracy(self, key: str) -> None:
        """Check model accuracy based on feedback."""
        records = list(self.predictions[key])
        feedback_records = [r for r in records if r.feedback is not None]
        
        if len(feedback_records) < 50:
            return
        
        recent = feedback_records[-50:]
        accuracy = np.mean([r.feedback['correct'] for r in recent])
        
        if accuracy < self.alert_threshold_accuracy:
            self._create_alert(
                alert_type='low_accuracy',
                model_key=key,
                details={
                    'accuracy': float(accuracy),
                    'threshold': self.alert_threshold_accuracy,
                    'sample_size': len(recent)
                }
            )
    
    def _create_alert(
        self,
        alert_type: str,
        model_key: str,
        details: Dict[str, Any]
    ) -> None:
        """Create a monitoring alert."""
        alert = {
            'type': alert_type,
            'model_key': model_key,
            'timestamp': datetime.now().isoformat(),
            'details': details
        }
        self.alerts.append(alert)
        
        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
    
    def get_model_stats(self, model_type: str, version_id: str) -> Dict[str, Any]:
        """Get statistics for a model version."""
        key = f"{model_type}_{version_id}"
        
        if key not in self.predictions:
            return {}
        
        records = list(self.predictions[key])
        
        latencies = [r.inference_time_ms for r in records]
        confidences = [r.confidence for r in records]
        
        feedback_records = [r for r in records if r.feedback is not None]
        accuracy = np.mean([r.feedback['correct'] for r in feedback_records]) if feedback_records else None
        
        return {
            'total_predictions': len(records),
            'predictions_with_feedback': len(feedback_records),
            'accuracy': float(accuracy) if accuracy else None,
            'latency': {
                'mean': float(np.mean(latencies)),
                'p50': float(np.percentile(latencies, 50)),
                'p95': float(np.percentile(latencies, 95)),
                'p99': float(np.percentile(latencies, 99)),
            },
            'confidence': {
                'mean': float(np.mean(confidences)),
                'min': float(np.min(confidences)),
                'max': float(np.max(confidences)),
            },
            'recent_alerts': [
                a for a in self.alerts
                if a['model_key'] == key
            ][-5:]
        }
```

---

## 3. Key Takeaways

1. **Version Management**: Track and manage model versions
2. **A/B Testing**: Route traffic between model versions
3. **Drift Detection**: Monitor for data and prediction drift
4. **Latency Monitoring**: Track inference performance
5. **Feedback Loops**: Collect ground truth for improvement

## Week 4 Summary

This week you learned:
- Session 16: Building production ML pipelines
- Session 17: Data pipeline architecture
- Session 18: Advanced feature engineering
- Session 19: Model training and evaluation
- Session 20: Production deployment and monitoring

## Next Week Preview
- Week 5: MCP (Model Context Protocol) Server Development
