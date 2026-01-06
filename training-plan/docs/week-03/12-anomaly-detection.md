# Session 12: Anomaly Detection with Isolation Forest

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 3, Day 2 (Tuesday)
- **Prerequisites**: Session 11 completed
- **Deliverable**: Working anomaly detection service

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Understand Isolation Forest algorithm
2. Train an anomaly detection model
3. Build real-time detection pipeline
4. Integrate with Azure Monitor alerts

---

## 📚 Isolation Forest Explained

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ISOLATION FOREST ALGORITHM                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   CONCEPT: Anomalies are "few and different"                                │
│   ─────────────────────────────────────────                                 │
│                                                                              │
│   Normal data points require MORE splits to isolate                         │
│   Anomalies require FEWER splits to isolate                                 │
│                                                                              │
│                     Random Split                                            │
│                         │                                                   │
│              ┌──────────┴──────────┐                                       │
│              │                     │                                       │
│         < threshold          >= threshold                                   │
│              │                     │                                       │
│      ┌───────┴───────┐     ┌───────┴───────┐                              │
│      │               │     │               │                              │
│   [Normal]       [Normal]  [Anomaly!]   [Normal]                          │
│   (many points)  (many)   (isolated     (many)                            │
│                           quickly)                                          │
│                                                                              │
│   SCORING:                                                                  │
│   • Average path length to isolate a point                                 │
│   • Shorter path = higher anomaly score                                    │
│   • Score normalized between 0 and 1                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Hands-On Exercise

### Step 1: Create Anomaly Detection Service

Create `ecommerce-app/aiops/anomaly_detection.py`:

```python
"""
Anomaly Detection Service using Isolation Forest
Detects anomalies in e-commerce metrics in real-time.
"""

import os
import json
import pickle
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import asyncio

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from azure.monitor.query import LogsQueryClient
from azure.identity import DefaultAzureCredential
import structlog

logger = structlog.get_logger()


@dataclass
class MetricPoint:
    """A single metric observation."""
    timestamp: datetime
    service_name: str
    request_count: float
    error_rate: float
    avg_latency: float
    p95_latency: float
    dependency_failures: float


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    timestamp: datetime
    service_name: str
    is_anomaly: bool
    anomaly_score: float
    contributing_factors: List[str]
    metrics: Dict[str, float]


class AnomalyDetector:
    """
    Real-time anomaly detection using Isolation Forest.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        contamination: float = 0.05,
        n_estimators: int = 100
    ):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names = [
            "request_count",
            "error_rate", 
            "avg_latency",
            "p95_latency",
            "dependency_failures"
        ]
        self.model_path = model_path
        self.training_stats = {}
        
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
    
    def _prepare_features(self, metrics: List[MetricPoint]) -> np.ndarray:
        """Convert metrics to feature matrix."""
        features = []
        for m in metrics:
            features.append([
                m.request_count,
                m.error_rate,
                m.avg_latency,
                m.p95_latency,
                m.dependency_failures
            ])
        return np.array(features)
    
    def train(
        self,
        training_data: List[MetricPoint],
        validation_split: float = 0.2
    ) -> Dict[str, Any]:
        """Train the anomaly detection model."""
        logger.info(
            "Training anomaly detection model",
            samples=len(training_data)
        )
        
        # Prepare features
        X = self._prepare_features(training_data)
        
        # Split for validation
        split_idx = int(len(X) * (1 - validation_split))
        X_train = X[:split_idx]
        X_val = X[split_idx:]
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_val_scaled = self.scaler.transform(X_val)
        
        # Train Isolation Forest
        self.model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(X_train_scaled)
        
        # Calculate training statistics
        train_scores = self.model.decision_function(X_train_scaled)
        val_scores = self.model.decision_function(X_val_scaled)
        
        self.training_stats = {
            "mean_score": float(np.mean(train_scores)),
            "std_score": float(np.std(train_scores)),
            "threshold": float(np.percentile(train_scores, 5)),
        }
        
        # Validation metrics
        val_predictions = self.model.predict(X_val_scaled)
        anomaly_rate = (val_predictions == -1).sum() / len(val_predictions)
        
        results = {
            "training_samples": len(X_train),
            "validation_samples": len(X_val),
            "validation_anomaly_rate": float(anomaly_rate),
            "training_stats": self.training_stats
        }
        
        logger.info("Model training complete", **results)
        
        return results
    
    def detect(self, metric: MetricPoint) -> AnomalyResult:
        """Detect if a single metric point is anomalous."""
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        
        # Prepare single observation
        X = self._prepare_features([metric])
        X_scaled = self.scaler.transform(X)
        
        # Get prediction and score
        prediction = self.model.predict(X_scaled)[0]
        score = self.model.decision_function(X_scaled)[0]
        
        # Normalize score to 0-1 range (lower = more anomalous)
        normalized_score = 1 - (score - self.training_stats["mean_score"]) / (3 * self.training_stats["std_score"])
        normalized_score = max(0, min(1, normalized_score))
        
        is_anomaly = prediction == -1
        
        # Identify contributing factors
        contributing_factors = self._identify_factors(metric, X_scaled[0])
        
        return AnomalyResult(
            timestamp=metric.timestamp,
            service_name=metric.service_name,
            is_anomaly=is_anomaly,
            anomaly_score=float(normalized_score),
            contributing_factors=contributing_factors,
            metrics={
                "request_count": metric.request_count,
                "error_rate": metric.error_rate,
                "avg_latency": metric.avg_latency,
                "p95_latency": metric.p95_latency,
                "dependency_failures": metric.dependency_failures
            }
        )
    
    def detect_batch(self, metrics: List[MetricPoint]) -> List[AnomalyResult]:
        """Detect anomalies in a batch of metrics."""
        return [self.detect(m) for m in metrics]
    
    def _identify_factors(
        self,
        metric: MetricPoint,
        scaled_features: np.ndarray
    ) -> List[str]:
        """Identify which features contribute most to anomaly."""
        factors = []
        
        # Check each feature against thresholds
        feature_values = {
            "request_count": (metric.request_count, scaled_features[0]),
            "error_rate": (metric.error_rate, scaled_features[1]),
            "avg_latency": (metric.avg_latency, scaled_features[2]),
            "p95_latency": (metric.p95_latency, scaled_features[3]),
            "dependency_failures": (metric.dependency_failures, scaled_features[4])
        }
        
        for name, (raw, scaled) in feature_values.items():
            if abs(scaled) > 2.0:  # More than 2 std deviations
                direction = "high" if scaled > 0 else "low"
                factors.append(f"{name}_{direction}")
        
        return factors
    
    def save_model(self, path: str) -> None:
        """Save the trained model to disk."""
        model_data = {
            "model": self.model,
            "scaler": self.scaler,
            "training_stats": self.training_stats,
            "feature_names": self.feature_names
        }
        with open(path, "wb") as f:
            pickle.dump(model_data, f)
        logger.info("Model saved", path=path)
    
    def load_model(self, path: str) -> None:
        """Load a trained model from disk."""
        with open(path, "rb") as f:
            model_data = pickle.load(f)
        
        self.model = model_data["model"]
        self.scaler = model_data["scaler"]
        self.training_stats = model_data["training_stats"]
        self.feature_names = model_data["feature_names"]
        logger.info("Model loaded", path=path)


class MetricsCollector:
    """Collects metrics from Azure Monitor Log Analytics."""
    
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        credential = DefaultAzureCredential()
        self.client = LogsQueryClient(credential)
    
    async def fetch_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_minutes: int = 5
    ) -> List[MetricPoint]:
        """Fetch aggregated metrics from Log Analytics."""
        
        query = f"""
        let interval = {interval_minutes}m;
        requests
        | where timestamp between (datetime({start_time.isoformat()}) .. datetime({end_time.isoformat()}))
        | summarize 
            request_count = count(),
            error_rate = 100.0 * countif(success == false) / count(),
            avg_latency = avg(duration),
            p95_latency = percentile(duration, 95)
            by bin(timestamp, interval), cloud_RoleName
        | join kind=leftouter (
            dependencies
            | where timestamp between (datetime({start_time.isoformat()}) .. datetime({end_time.isoformat()}))
            | summarize dependency_failures = countif(success == false)
                by bin(timestamp, interval), cloud_RoleName
        ) on timestamp, cloud_RoleName
        | project 
            timestamp,
            service_name = cloud_RoleName,
            request_count,
            error_rate,
            avg_latency,
            p95_latency,
            dependency_failures = coalesce(dependency_failures, 0)
        | order by timestamp asc
        """
        
        response = self.client.query_workspace(
            workspace_id=self.workspace_id,
            query=query,
            timespan=(start_time, end_time)
        )
        
        metrics = []
        for row in response.tables[0].rows:
            metrics.append(MetricPoint(
                timestamp=row[0],
                service_name=row[1],
                request_count=float(row[2]),
                error_rate=float(row[3]),
                avg_latency=float(row[4]),
                p95_latency=float(row[5]),
                dependency_failures=float(row[6])
            ))
        
        return metrics


class AnomalyAlertManager:
    """Manages alerts based on anomaly detection results."""
    
    def __init__(self, alert_threshold: float = 0.8):
        self.alert_threshold = alert_threshold
        self.alert_history: List[AnomalyResult] = []
    
    def should_alert(self, result: AnomalyResult) -> bool:
        """Determine if an alert should be triggered."""
        if not result.is_anomaly:
            return False
        
        if result.anomaly_score < self.alert_threshold:
            return False
        
        # Check for alert fatigue - don't alert on same service within 5 min
        recent_alerts = [
            a for a in self.alert_history
            if a.service_name == result.service_name
            and (result.timestamp - a.timestamp).seconds < 300
        ]
        
        if recent_alerts:
            return False
        
        self.alert_history.append(result)
        return True
    
    def format_alert(self, result: AnomalyResult) -> Dict[str, Any]:
        """Format anomaly as alert payload."""
        return {
            "severity": self._calculate_severity(result.anomaly_score),
            "title": f"Anomaly detected in {result.service_name}",
            "description": self._build_description(result),
            "timestamp": result.timestamp.isoformat(),
            "service": result.service_name,
            "score": result.anomaly_score,
            "factors": result.contributing_factors,
            "metrics": result.metrics
        }
    
    def _calculate_severity(self, score: float) -> str:
        """Calculate alert severity based on score."""
        if score >= 0.95:
            return "critical"
        elif score >= 0.9:
            return "high"
        elif score >= 0.8:
            return "medium"
        return "low"
    
    def _build_description(self, result: AnomalyResult) -> str:
        """Build human-readable description."""
        factors = ", ".join(result.contributing_factors) if result.contributing_factors else "multiple factors"
        return f"Anomalous behavior detected in {result.service_name}. Contributing factors: {factors}. Anomaly score: {result.anomaly_score:.2f}"


# ============================================================
# DEMO / TRAINING SCRIPT
# ============================================================

def generate_synthetic_training_data(
    n_samples: int = 1000,
    anomaly_ratio: float = 0.05
) -> List[MetricPoint]:
    """Generate synthetic training data for demo purposes."""
    data = []
    base_time = datetime.utcnow() - timedelta(hours=n_samples // 12)
    
    for i in range(n_samples):
        is_anomaly = np.random.random() < anomaly_ratio
        
        if is_anomaly:
            # Generate anomalous metrics
            metric = MetricPoint(
                timestamp=base_time + timedelta(minutes=i * 5),
                service_name="order-service",
                request_count=np.random.uniform(10, 50),
                error_rate=np.random.uniform(10, 50),  # High error rate
                avg_latency=np.random.uniform(2000, 10000),  # High latency
                p95_latency=np.random.uniform(5000, 20000),
                dependency_failures=np.random.uniform(5, 20)
            )
        else:
            # Generate normal metrics
            metric = MetricPoint(
                timestamp=base_time + timedelta(minutes=i * 5),
                service_name="order-service",
                request_count=np.random.uniform(80, 150),
                error_rate=np.random.uniform(0, 2),  # Low error rate
                avg_latency=np.random.uniform(100, 500),  # Normal latency
                p95_latency=np.random.uniform(200, 800),
                dependency_failures=np.random.uniform(0, 2)
            )
        
        data.append(metric)
    
    return data


if __name__ == "__main__":
    # Demo: Train model on synthetic data
    print("Generating synthetic training data...")
    training_data = generate_synthetic_training_data(1000)
    
    print("Training anomaly detection model...")
    detector = AnomalyDetector(contamination=0.05)
    results = detector.train(training_data)
    print(f"Training results: {results}")
    
    # Test on new data
    print("\nTesting anomaly detection...")
    
    # Normal sample
    normal = MetricPoint(
        timestamp=datetime.utcnow(),
        service_name="order-service",
        request_count=100,
        error_rate=1.5,
        avg_latency=300,
        p95_latency=500,
        dependency_failures=1
    )
    
    # Anomalous sample
    anomaly = MetricPoint(
        timestamp=datetime.utcnow(),
        service_name="order-service",
        request_count=20,
        error_rate=35,
        avg_latency=5000,
        p95_latency=12000,
        dependency_failures=15
    )
    
    normal_result = detector.detect(normal)
    anomaly_result = detector.detect(anomaly)
    
    print(f"Normal sample - Is anomaly: {normal_result.is_anomaly}, Score: {normal_result.anomaly_score:.3f}")
    print(f"Anomaly sample - Is anomaly: {anomaly_result.is_anomaly}, Score: {anomaly_result.anomaly_score:.3f}")
    print(f"Contributing factors: {anomaly_result.contributing_factors}")
    
    # Save model
    detector.save_model("anomaly_model.pkl")
    print("\nModel saved to anomaly_model.pkl")
```

---

## 🧪 Verification Checklist

- [ ] Anomaly detection module created
- [ ] Model trained on synthetic data
- [ ] Test normal vs anomalous samples
- [ ] Model persisted to disk
- [ ] Alert manager implemented

---

## 📖 Key Takeaways

1. **Isolation Forest** works well for unsupervised anomaly detection
2. **Feature engineering** is critical - choose meaningful metrics
3. **Score normalization** helps with interpretability
4. **Alert fatigue** must be managed with deduplication

---

## 🔜 Next Session Preview

**Session 13: Capacity Forecasting with Prophet**
- Time series forecasting
- Predict future resource needs
- Plan for traffic spikes
