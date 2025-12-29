# Session 16: ML Pipeline Integration

## Learning Objectives
- Build production ML pipelines for AIOps
- Implement model serving and inference
- Create feedback loops for model improvement
- Integrate ML with operational workflows

## Duration: 1 hour

---

## 1. Production ML Pipeline Architecture

### ML Service Implementation

```python
# File: training-plan/ecommerce-app/ml/service/ml_service.py
"""
Production ML service for AIOps.
"""

import asyncio
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json

import numpy as np
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel


class ModelType(str, Enum):
    ANOMALY_DETECTION = "anomaly_detection"
    LOG_CLASSIFICATION = "log_classification"
    CAPACITY_FORECAST = "capacity_forecast"
    ROOT_CAUSE = "root_cause"


@dataclass
class ModelMetadata:
    """Metadata for a trained model."""
    model_id: str
    model_type: ModelType
    version: str
    trained_at: datetime
    metrics: Dict[str, float]
    features: List[str]
    config: Dict[str, Any]
    path: str


class ModelRegistry:
    """
    Registry for managing ML models.
    """
    
    def __init__(self, storage_path: str = "/models"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.models: Dict[str, ModelMetadata] = {}
        self.active_versions: Dict[str, str] = {}  # model_type -> version
    
    def register_model(
        self,
        model: Any,
        model_type: ModelType,
        version: str,
        metrics: Dict[str, float],
        features: List[str],
        config: Dict[str, Any]
    ) -> ModelMetadata:
        """Register a new model version."""
        model_id = f"{model_type.value}_{version}"
        model_path = self.storage_path / f"{model_id}.pkl"
        
        # Save model
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        
        metadata = ModelMetadata(
            model_id=model_id,
            model_type=model_type,
            version=version,
            trained_at=datetime.now(),
            metrics=metrics,
            features=features,
            config=config,
            path=str(model_path)
        )
        
        self.models[model_id] = metadata
        
        # Save metadata
        metadata_path = self.storage_path / f"{model_id}_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump({
                'model_id': metadata.model_id,
                'model_type': metadata.model_type.value,
                'version': metadata.version,
                'trained_at': metadata.trained_at.isoformat(),
                'metrics': metadata.metrics,
                'features': metadata.features,
                'config': metadata.config,
                'path': metadata.path
            }, f)
        
        return metadata
    
    def load_model(self, model_id: str) -> Any:
        """Load a model from storage."""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found")
        
        metadata = self.models[model_id]
        with open(metadata.path, 'rb') as f:
            return pickle.load(f)
    
    def get_active_model(self, model_type: ModelType) -> Optional[Any]:
        """Get the currently active model for a type."""
        version = self.active_versions.get(model_type.value)
        if not version:
            return None
        
        model_id = f"{model_type.value}_{version}"
        return self.load_model(model_id)
    
    def promote_version(self, model_type: ModelType, version: str) -> None:
        """Promote a version to be the active one."""
        model_id = f"{model_type.value}_{version}"
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found")
        
        self.active_versions[model_type.value] = version
    
    def list_models(
        self,
        model_type: Optional[ModelType] = None
    ) -> List[ModelMetadata]:
        """List all registered models."""
        if model_type:
            return [
                m for m in self.models.values()
                if m.model_type == model_type
            ]
        return list(self.models.values())


class InferenceService:
    """
    Real-time inference service.
    """
    
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self.inference_cache: Dict[str, Any] = {}
        self.predictions: List[Dict] = []
        self.feedback: List[Dict] = []
    
    async def predict_anomaly(
        self,
        metrics: Dict[str, List[float]],
        service: str
    ) -> Dict[str, Any]:
        """
        Predict anomalies in metrics.
        """
        model = self.registry.get_active_model(ModelType.ANOMALY_DETECTION)
        if not model:
            raise RuntimeError("No anomaly detection model available")
        
        # Prepare features
        features = self._prepare_features(metrics)
        
        # Run inference
        start_time = datetime.now()
        predictions = model.predict(features)
        inference_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Process results
        anomalies = []
        for i, (metric_name, values) in enumerate(metrics.items()):
            is_anomaly = predictions[i] == -1  # Isolation Forest convention
            if is_anomaly:
                anomalies.append({
                    'metric': metric_name,
                    'service': service,
                    'score': float(model.score_samples([features[i]])[0]),
                    'values': values[-5:]  # Last 5 values
                })
        
        result = {
            'service': service,
            'timestamp': datetime.now().isoformat(),
            'is_anomaly': len(anomalies) > 0,
            'anomalies': anomalies,
            'inference_time_ms': inference_time
        }
        
        # Store for feedback
        self.predictions.append(result)
        
        return result
    
    async def classify_log(
        self,
        log_message: str,
        service: str
    ) -> Dict[str, Any]:
        """
        Classify a log message.
        """
        model = self.registry.get_active_model(ModelType.LOG_CLASSIFICATION)
        if not model:
            # Fallback to rule-based classification
            return self._rule_based_classification(log_message)
        
        # ML-based classification
        prediction = model.predict([log_message])[0]
        probability = model.predict_proba([log_message])[0]
        
        return {
            'log': log_message,
            'service': service,
            'classification': prediction,
            'confidence': float(max(probability)),
            'timestamp': datetime.now().isoformat()
        }
    
    async def forecast_capacity(
        self,
        resource: str,
        horizon_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Forecast capacity needs.
        """
        model = self.registry.get_active_model(ModelType.CAPACITY_FORECAST)
        if not model:
            raise RuntimeError("No capacity forecast model available")
        
        # Generate forecast
        forecast = model.predict(periods=horizon_hours, freq='H')
        
        return {
            'resource': resource,
            'horizon_hours': horizon_hours,
            'forecast': [
                {
                    'timestamp': f.timestamp.isoformat(),
                    'predicted': f.predicted_value,
                    'lower': f.lower_bound,
                    'upper': f.upper_bound
                }
                for f in forecast
            ],
            'generated_at': datetime.now().isoformat()
        }
    
    def record_feedback(
        self,
        prediction_id: str,
        actual_value: Any,
        correct: bool,
        notes: Optional[str] = None
    ) -> None:
        """Record feedback for a prediction."""
        self.feedback.append({
            'prediction_id': prediction_id,
            'actual_value': actual_value,
            'correct': correct,
            'notes': notes,
            'recorded_at': datetime.now().isoformat()
        })
    
    def _prepare_features(
        self,
        metrics: Dict[str, List[float]]
    ) -> np.ndarray:
        """Prepare feature matrix from metrics."""
        features = []
        for name, values in metrics.items():
            values = np.array(values)
            features.append([
                np.mean(values),
                np.std(values),
                np.min(values),
                np.max(values),
                np.percentile(values, 50),
                np.percentile(values, 95),
                np.percentile(values, 99)
            ])
        return np.array(features)
    
    def _rule_based_classification(
        self,
        log_message: str
    ) -> Dict[str, Any]:
        """Fallback rule-based log classification."""
        log_lower = log_message.lower()
        
        if any(word in log_lower for word in ['error', 'exception', 'failed', 'failure']):
            classification = 'error'
            confidence = 0.8
        elif any(word in log_lower for word in ['warning', 'warn', 'deprecated']):
            classification = 'warning'
            confidence = 0.7
        elif any(word in log_lower for word in ['info', 'started', 'completed', 'success']):
            classification = 'info'
            confidence = 0.6
        else:
            classification = 'unknown'
            confidence = 0.3
        
        return {
            'log': log_message,
            'classification': classification,
            'confidence': confidence,
            'method': 'rule_based'
        }


# FastAPI Application
app = FastAPI(title="AIOps ML Service", version="1.0.0")
registry = ModelRegistry()
inference_service = InferenceService(registry)


class MetricsRequest(BaseModel):
    service: str
    metrics: Dict[str, List[float]]


class LogRequest(BaseModel):
    service: str
    message: str


class FeedbackRequest(BaseModel):
    prediction_id: str
    actual_value: Any
    correct: bool
    notes: Optional[str] = None


@app.post("/predict/anomaly")
async def predict_anomaly(request: MetricsRequest):
    """Predict anomalies in metrics."""
    try:
        result = await inference_service.predict_anomaly(
            metrics=request.metrics,
            service=request.service
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict/log")
async def classify_log(request: LogRequest):
    """Classify a log message."""
    try:
        result = await inference_service.classify_log(
            log_message=request.message,
            service=request.service
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback")
async def record_feedback(request: FeedbackRequest):
    """Record feedback for predictions."""
    inference_service.record_feedback(
        prediction_id=request.prediction_id,
        actual_value=request.actual_value,
        correct=request.correct,
        notes=request.notes
    )
    return {"status": "recorded"}


@app.get("/models")
async def list_models():
    """List all registered models."""
    return [
        {
            'model_id': m.model_id,
            'model_type': m.model_type.value,
            'version': m.version,
            'trained_at': m.trained_at.isoformat(),
            'metrics': m.metrics
        }
        for m in registry.list_models()
    ]
```

---

## 2. Training Pipeline

### Automated Model Training

```python
# File: training-plan/ecommerce-app/ml/training/training_pipeline.py
"""
Automated ML training pipeline for AIOps.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import precision_score, recall_score, f1_score


@dataclass
class TrainingJob:
    """Training job specification."""
    job_id: str
    model_type: str
    config: Dict[str, Any]
    status: str  # 'pending', 'running', 'completed', 'failed'
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metrics: Dict[str, float] = None
    error: Optional[str] = None


class DataLoader:
    """
    Load training data from various sources.
    """
    
    def __init__(self, azure_monitor_client=None, cosmos_client=None):
        self.azure_monitor = azure_monitor_client
        self.cosmos = cosmos_client
    
    async def load_metrics_data(
        self,
        services: List[str],
        timespan: timedelta = timedelta(days=7)
    ) -> Dict[str, np.ndarray]:
        """Load metrics data for training."""
        # In production, this would query Azure Monitor
        # For demo, generate synthetic data
        
        data = {}
        for service in services:
            # Simulate loading metrics
            n_samples = int(timespan.total_seconds() / 60)  # 1-minute intervals
            data[service] = {
                'cpu': np.random.normal(50, 10, n_samples),
                'memory': np.random.normal(60, 15, n_samples),
                'latency': np.random.exponential(100, n_samples),
                'error_rate': np.random.beta(1, 20, n_samples)
            }
        
        return data
    
    async def load_log_data(
        self,
        services: List[str],
        timespan: timedelta = timedelta(days=7)
    ) -> List[Dict[str, Any]]:
        """Load log data for training."""
        # In production, this would query Log Analytics
        logs = []
        
        templates = [
            ("INFO", "Request completed successfully in {duration}ms"),
            ("WARN", "High latency detected: {duration}ms"),
            ("ERROR", "Failed to process request: {error}"),
            ("INFO", "User {user_id} authenticated"),
            ("ERROR", "Database connection timeout after {duration}ms"),
        ]
        
        for _ in range(1000):
            level, template = np.random.choice(templates)
            logs.append({
                'level': level,
                'message': template.format(
                    duration=np.random.randint(10, 5000),
                    error=np.random.choice(['timeout', 'auth_failed', 'not_found']),
                    user_id=f"user_{np.random.randint(1, 1000)}"
                ),
                'service': np.random.choice(services)
            })
        
        return logs


class AnomalyDetectionTrainer:
    """
    Train anomaly detection models.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {
            'contamination': 0.05,
            'n_estimators': 100,
            'max_samples': 'auto',
            'random_state': 42
        }
    
    def prepare_features(
        self,
        metrics_data: Dict[str, Dict[str, np.ndarray]]
    ) -> Tuple[np.ndarray, List[str]]:
        """Prepare feature matrix from metrics."""
        features = []
        feature_names = []
        
        for service, metrics in metrics_data.items():
            for metric_name, values in metrics.items():
                # Window-based features
                window_size = 10
                for i in range(window_size, len(values)):
                    window = values[i-window_size:i]
                    features.append([
                        np.mean(window),
                        np.std(window),
                        np.min(window),
                        np.max(window),
                        np.percentile(window, 50),
                        np.percentile(window, 95),
                        values[i]  # Current value
                    ])
                
                if not feature_names:
                    feature_names = [
                        'mean', 'std', 'min', 'max', 'p50', 'p95', 'current'
                    ]
        
        return np.array(features), feature_names
    
    def train(
        self,
        X: np.ndarray,
        labels: Optional[np.ndarray] = None
    ) -> Tuple[Any, Dict[str, float]]:
        """
        Train the anomaly detection model.
        
        Returns:
            Tuple of (model, metrics)
        """
        # Split data
        X_train, X_test = train_test_split(
            X, test_size=0.2, random_state=42
        )
        
        # Train model
        model = IsolationForest(**self.config)
        model.fit(X_train)
        
        # Evaluate
        train_preds = model.predict(X_train)
        test_preds = model.predict(X_test)
        
        metrics = {
            'train_anomaly_rate': float((train_preds == -1).mean()),
            'test_anomaly_rate': float((test_preds == -1).mean()),
            'n_samples': len(X),
            'n_features': X.shape[1]
        }
        
        # If we have labels, calculate precision/recall
        if labels is not None:
            test_labels = labels[-len(test_preds):]
            predictions_binary = (test_preds == -1).astype(int)
            
            metrics['precision'] = float(precision_score(test_labels, predictions_binary))
            metrics['recall'] = float(recall_score(test_labels, predictions_binary))
            metrics['f1'] = float(f1_score(test_labels, predictions_binary))
        
        return model, metrics


class TrainingOrchestrator:
    """
    Orchestrates the training pipeline.
    """
    
    def __init__(self, registry, data_loader: DataLoader):
        self.registry = registry
        self.data_loader = data_loader
        self.jobs: Dict[str, TrainingJob] = {}
    
    async def submit_job(
        self,
        model_type: str,
        config: Dict[str, Any]
    ) -> TrainingJob:
        """Submit a new training job."""
        job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        job = TrainingJob(
            job_id=job_id,
            model_type=model_type,
            config=config,
            status='pending'
        )
        
        self.jobs[job_id] = job
        
        # Start training in background
        asyncio.create_task(self._run_job(job))
        
        return job
    
    async def _run_job(self, job: TrainingJob) -> None:
        """Run a training job."""
        try:
            job.status = 'running'
            job.started_at = datetime.now()
            
            if job.model_type == 'anomaly_detection':
                await self._train_anomaly_model(job)
            elif job.model_type == 'log_classification':
                await self._train_log_model(job)
            else:
                raise ValueError(f"Unknown model type: {job.model_type}")
            
            job.status = 'completed'
            job.completed_at = datetime.now()
            
        except Exception as e:
            job.status = 'failed'
            job.error = str(e)
            job.completed_at = datetime.now()
    
    async def _train_anomaly_model(self, job: TrainingJob) -> None:
        """Train anomaly detection model."""
        services = job.config.get('services', ['catalog', 'order', 'payment'])
        timespan = timedelta(days=job.config.get('days', 7))
        
        # Load data
        data = await self.data_loader.load_metrics_data(services, timespan)
        
        # Train model
        trainer = AnomalyDetectionTrainer(job.config.get('model_params'))
        X, features = trainer.prepare_features(data)
        model, metrics = trainer.train(X)
        
        # Register model
        version = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.registry.register_model(
            model=model,
            model_type='anomaly_detection',
            version=version,
            metrics=metrics,
            features=features,
            config=job.config
        )
        
        job.metrics = metrics
    
    async def _train_log_model(self, job: TrainingJob) -> None:
        """Train log classification model."""
        # Implementation similar to anomaly model
        pass
    
    def get_job_status(self, job_id: str) -> Optional[TrainingJob]:
        """Get job status."""
        return self.jobs.get(job_id)
    
    def list_jobs(
        self,
        status: Optional[str] = None
    ) -> List[TrainingJob]:
        """List all jobs."""
        jobs = list(self.jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs
```

---

## 3. Key Takeaways

1. **Model Registry**: Central management of model versions
2. **Inference Service**: Low-latency predictions with caching
3. **Feedback Loops**: Capture ground truth for improvement
4. **Training Pipelines**: Automated retraining workflows
5. **Version Management**: Track and promote model versions

## Next Session Preview
- Session 17: Building the Data Pipeline for ML
