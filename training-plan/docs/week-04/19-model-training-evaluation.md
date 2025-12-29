# Session 19: Model Training and Evaluation

## Learning Objectives
- Train ML models for AIOps use cases
- Implement proper evaluation strategies
- Handle imbalanced datasets
- Deploy models with confidence

## Duration: 1 hour

---

## 1. Model Training Framework

### Unified Training Framework

```python
# File: training-plan/ecommerce-app/ml/training/model_trainer.py
"""
Unified model training framework for AIOps.
"""

import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Type
from dataclasses import dataclass, field
from enum import Enum
import json

from sklearn.base import BaseEstimator
from sklearn.model_selection import (
    train_test_split, 
    cross_val_score,
    TimeSeriesSplit,
    StratifiedKFold
)
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
    mean_squared_error,
    mean_absolute_error,
    r2_score
)
from sklearn.ensemble import (
    IsolationForest,
    RandomForestClassifier,
    GradientBoostingClassifier
)
from sklearn.preprocessing import StandardScaler


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    ANOMALY_DETECTION = "anomaly_detection"
    CLUSTERING = "clustering"


@dataclass
class TrainingConfig:
    """Configuration for model training."""
    task_type: TaskType
    model_class: str
    model_params: Dict[str, Any]
    test_size: float = 0.2
    validation_size: float = 0.1
    cross_validation_folds: int = 5
    use_time_series_split: bool = False
    random_state: int = 42
    scale_features: bool = True
    handle_imbalance: bool = True


@dataclass
class TrainingResult:
    """Result of model training."""
    model: Any
    metrics: Dict[str, float]
    train_metrics: Dict[str, float]
    validation_metrics: Dict[str, float]
    test_metrics: Dict[str, float]
    feature_importance: Dict[str, float]
    confusion_matrix: Optional[np.ndarray]
    training_time: float
    config: TrainingConfig
    timestamp: datetime = field(default_factory=datetime.now)


class ModelTrainer:
    """
    Unified model training for AIOps use cases.
    """
    
    MODEL_REGISTRY = {
        'IsolationForest': IsolationForest,
        'RandomForestClassifier': RandomForestClassifier,
        'GradientBoostingClassifier': GradientBoostingClassifier,
    }
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.scaler = StandardScaler() if config.scale_features else None
        self.model = None
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None
    ) -> TrainingResult:
        """
        Train the model with proper validation.
        """
        start_time = datetime.now()
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=self.config.test_size,
            random_state=self.config.random_state,
            stratify=y if self.config.task_type == TaskType.CLASSIFICATION else None
        )
        
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train,
            test_size=self.config.validation_size,
            random_state=self.config.random_state,
            stratify=y_train if self.config.task_type == TaskType.CLASSIFICATION else None
        )
        
        # Scale features
        if self.scaler:
            X_train = self.scaler.fit_transform(X_train)
            X_val = self.scaler.transform(X_val)
            X_test = self.scaler.transform(X_test)
        
        # Handle imbalance
        if self.config.handle_imbalance and self.config.task_type == TaskType.CLASSIFICATION:
            X_train, y_train = self._handle_imbalance(X_train, y_train)
        
        # Create and train model
        model_class = self.MODEL_REGISTRY.get(self.config.model_class)
        if not model_class:
            raise ValueError(f"Unknown model class: {self.config.model_class}")
        
        self.model = model_class(**self.config.model_params)
        
        if self.config.task_type == TaskType.ANOMALY_DETECTION:
            self.model.fit(X_train)
        else:
            self.model.fit(X_train, y_train)
        
        # Evaluate
        train_metrics = self._evaluate(X_train, y_train)
        val_metrics = self._evaluate(X_val, y_val)
        test_metrics = self._evaluate(X_test, y_test)
        
        # Cross-validation
        cv_scores = self._cross_validate(X, y)
        
        # Feature importance
        feature_importance = self._get_feature_importance(feature_names)
        
        # Confusion matrix
        if self.config.task_type == TaskType.CLASSIFICATION:
            y_pred = self.model.predict(X_test)
            conf_matrix = confusion_matrix(y_test, y_pred)
        else:
            conf_matrix = None
        
        training_time = (datetime.now() - start_time).total_seconds()
        
        return TrainingResult(
            model=self.model,
            metrics={
                **test_metrics,
                'cv_mean': float(np.mean(cv_scores)),
                'cv_std': float(np.std(cv_scores))
            },
            train_metrics=train_metrics,
            validation_metrics=val_metrics,
            test_metrics=test_metrics,
            feature_importance=feature_importance,
            confusion_matrix=conf_matrix,
            training_time=training_time,
            config=self.config
        )
    
    def _evaluate(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Dict[str, float]:
        """Evaluate model on data."""
        if self.config.task_type == TaskType.ANOMALY_DETECTION:
            y_pred = self.model.predict(X)
            y_pred_binary = (y_pred == -1).astype(int)
            
            if len(np.unique(y)) > 1:
                return {
                    'accuracy': float(accuracy_score(y, y_pred_binary)),
                    'precision': float(precision_score(y, y_pred_binary, zero_division=0)),
                    'recall': float(recall_score(y, y_pred_binary, zero_division=0)),
                    'f1': float(f1_score(y, y_pred_binary, zero_division=0)),
                }
            return {'anomaly_rate': float(np.mean(y_pred_binary))}
        
        elif self.config.task_type == TaskType.CLASSIFICATION:
            y_pred = self.model.predict(X)
            y_proba = self.model.predict_proba(X)[:, 1] if hasattr(self.model, 'predict_proba') else None
            
            metrics = {
                'accuracy': float(accuracy_score(y, y_pred)),
                'precision': float(precision_score(y, y_pred, average='weighted', zero_division=0)),
                'recall': float(recall_score(y, y_pred, average='weighted', zero_division=0)),
                'f1': float(f1_score(y, y_pred, average='weighted', zero_division=0)),
            }
            
            if y_proba is not None and len(np.unique(y)) == 2:
                metrics['roc_auc'] = float(roc_auc_score(y, y_proba))
            
            return metrics
        
        elif self.config.task_type == TaskType.REGRESSION:
            y_pred = self.model.predict(X)
            
            return {
                'mse': float(mean_squared_error(y, y_pred)),
                'rmse': float(np.sqrt(mean_squared_error(y, y_pred))),
                'mae': float(mean_absolute_error(y, y_pred)),
                'r2': float(r2_score(y, y_pred)),
            }
        
        return {}
    
    def _cross_validate(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> np.ndarray:
        """Perform cross-validation."""
        if self.config.use_time_series_split:
            cv = TimeSeriesSplit(n_splits=self.config.cross_validation_folds)
        else:
            cv = StratifiedKFold(
                n_splits=self.config.cross_validation_folds,
                shuffle=True,
                random_state=self.config.random_state
            )
        
        if self.config.task_type == TaskType.ANOMALY_DETECTION:
            return np.array([0.0])  # CV not applicable for unsupervised
        
        scoring = 'f1_weighted' if self.config.task_type == TaskType.CLASSIFICATION else 'neg_mean_squared_error'
        
        model = self.MODEL_REGISTRY[self.config.model_class](**self.config.model_params)
        scores = cross_val_score(model, X, y, cv=cv, scoring=scoring)
        
        return scores
    
    def _handle_imbalance(
        self,
        X: np.ndarray,
        y: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Handle class imbalance using SMOTE."""
        try:
            from imblearn.over_sampling import SMOTE
            
            smote = SMOTE(random_state=self.config.random_state)
            X_resampled, y_resampled = smote.fit_resample(X, y)
            
            return X_resampled, y_resampled
        except ImportError:
            return X, y
    
    def _get_feature_importance(
        self,
        feature_names: Optional[List[str]]
    ) -> Dict[str, float]:
        """Extract feature importance."""
        if not hasattr(self.model, 'feature_importances_'):
            return {}
        
        importance = self.model.feature_importances_
        names = feature_names or [f'feature_{i}' for i in range(len(importance))]
        
        return {
            name: float(imp)
            for name, imp in sorted(
                zip(names, importance),
                key=lambda x: x[1],
                reverse=True
            )
        }


class AnomalyDetectionTrainer(ModelTrainer):
    """
    Specialized trainer for anomaly detection.
    """
    
    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100
    ):
        config = TrainingConfig(
            task_type=TaskType.ANOMALY_DETECTION,
            model_class='IsolationForest',
            model_params={
                'contamination': contamination,
                'n_estimators': n_estimators,
                'random_state': 42,
                'n_jobs': -1
            }
        )
        super().__init__(config)
    
    def train_unsupervised(
        self,
        X: np.ndarray,
        feature_names: Optional[List[str]] = None
    ) -> TrainingResult:
        """Train without labels."""
        # Create pseudo-labels (all normal)
        y = np.zeros(len(X))
        return self.train(X, y, feature_names)
    
    def detect_threshold(
        self,
        X: np.ndarray,
        percentile: float = 95
    ) -> float:
        """Find optimal anomaly threshold."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        scores = self.model.score_samples(X)
        threshold = np.percentile(scores, 100 - percentile)
        
        return float(threshold)
```

---

## 2. Model Evaluation

### Comprehensive Evaluation

```python
# File: training-plan/ecommerce-app/ml/training/model_evaluator.py
"""
Comprehensive model evaluation for AIOps.
"""

import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from sklearn.metrics import (
    precision_recall_curve,
    roc_curve,
    average_precision_score
)


@dataclass
class EvaluationReport:
    """Comprehensive evaluation report."""
    model_name: str
    task_type: str
    metrics: Dict[str, float]
    threshold_analysis: Dict[str, Any]
    error_analysis: Dict[str, Any]
    recommendations: List[str]
    timestamp: datetime


class ModelEvaluator:
    """
    Comprehensive model evaluation.
    """
    
    def evaluate_anomaly_detector(
        self,
        model: Any,
        X_test: np.ndarray,
        y_true: Optional[np.ndarray] = None,
        threshold: Optional[float] = None
    ) -> EvaluationReport:
        """Evaluate anomaly detection model."""
        scores = model.score_samples(X_test)
        
        # Threshold analysis
        thresholds = np.percentile(scores, [1, 5, 10, 25, 50])
        threshold_analysis = {
            'score_distribution': {
                'min': float(np.min(scores)),
                'max': float(np.max(scores)),
                'mean': float(np.mean(scores)),
                'std': float(np.std(scores)),
            },
            'thresholds': {
                f'p{p}': float(t)
                for p, t in zip([1, 5, 10, 25, 50], thresholds)
            }
        }
        
        # If we have labels
        metrics = {}
        if y_true is not None:
            y_pred = model.predict(X_test)
            y_pred_binary = (y_pred == -1).astype(int)
            
            from sklearn.metrics import precision_score, recall_score, f1_score
            
            metrics = {
                'precision': float(precision_score(y_true, y_pred_binary, zero_division=0)),
                'recall': float(recall_score(y_true, y_pred_binary, zero_division=0)),
                'f1': float(f1_score(y_true, y_pred_binary, zero_division=0)),
                'anomaly_rate': float(np.mean(y_pred_binary)),
                'true_anomaly_rate': float(np.mean(y_true)),
            }
            
            # Threshold sweep
            for t in thresholds:
                y_pred_t = (scores < t).astype(int)
                metrics[f'recall_at_threshold_{int((1-np.mean(scores < t))*100)}'] = float(
                    recall_score(y_true, y_pred_t, zero_division=0)
                )
        
        # Error analysis
        error_analysis = self._analyze_errors_anomaly(scores, y_true, X_test)
        
        # Recommendations
        recommendations = self._generate_recommendations_anomaly(metrics, threshold_analysis)
        
        return EvaluationReport(
            model_name='IsolationForest',
            task_type='anomaly_detection',
            metrics=metrics,
            threshold_analysis=threshold_analysis,
            error_analysis=error_analysis,
            recommendations=recommendations,
            timestamp=datetime.now()
        )
    
    def evaluate_classifier(
        self,
        model: Any,
        X_test: np.ndarray,
        y_true: np.ndarray,
        class_names: Optional[List[str]] = None
    ) -> EvaluationReport:
        """Evaluate classification model."""
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test) if hasattr(model, 'predict_proba') else None
        
        from sklearn.metrics import classification_report, accuracy_score
        
        # Basic metrics
        report = classification_report(y_true, y_pred, output_dict=True)
        
        metrics = {
            'accuracy': float(accuracy_score(y_true, y_pred)),
            'macro_f1': float(report['macro avg']['f1-score']),
            'weighted_f1': float(report['weighted avg']['f1-score']),
        }
        
        # Per-class metrics
        for i, (class_id, class_metrics) in enumerate(report.items()):
            if class_id in ['accuracy', 'macro avg', 'weighted avg']:
                continue
            class_name = class_names[i] if class_names and i < len(class_names) else f'class_{class_id}'
            metrics[f'{class_name}_precision'] = float(class_metrics['precision'])
            metrics[f'{class_name}_recall'] = float(class_metrics['recall'])
            metrics[f'{class_name}_f1'] = float(class_metrics['f1-score'])
        
        # Threshold analysis for binary classification
        threshold_analysis = {}
        if y_proba is not None and len(np.unique(y_true)) == 2:
            precision, recall, thresholds = precision_recall_curve(y_true, y_proba[:, 1])
            threshold_analysis = {
                'optimal_threshold': float(thresholds[np.argmax(2 * precision * recall / (precision + recall + 1e-10))]),
                'average_precision': float(average_precision_score(y_true, y_proba[:, 1])),
            }
        
        # Error analysis
        error_analysis = self._analyze_errors_classification(y_true, y_pred, X_test)
        
        # Recommendations
        recommendations = self._generate_recommendations_classifier(metrics, error_analysis)
        
        return EvaluationReport(
            model_name=type(model).__name__,
            task_type='classification',
            metrics=metrics,
            threshold_analysis=threshold_analysis,
            error_analysis=error_analysis,
            recommendations=recommendations,
            timestamp=datetime.now()
        )
    
    def _analyze_errors_anomaly(
        self,
        scores: np.ndarray,
        y_true: Optional[np.ndarray],
        X: np.ndarray
    ) -> Dict[str, Any]:
        """Analyze anomaly detection errors."""
        if y_true is None:
            return {}
        
        y_pred = (scores < np.percentile(scores, 5)).astype(int)
        
        # False positives and negatives
        false_positives = np.where((y_pred == 1) & (y_true == 0))[0]
        false_negatives = np.where((y_pred == 0) & (y_true == 1))[0]
        
        return {
            'false_positive_count': len(false_positives),
            'false_negative_count': len(false_negatives),
            'false_positive_rate': float(len(false_positives) / (np.sum(y_true == 0) + 1e-10)),
            'false_negative_rate': float(len(false_negatives) / (np.sum(y_true == 1) + 1e-10)),
            'sample_false_positives': false_positives[:5].tolist(),
            'sample_false_negatives': false_negatives[:5].tolist(),
        }
    
    def _analyze_errors_classification(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        X: np.ndarray
    ) -> Dict[str, Any]:
        """Analyze classification errors."""
        errors = np.where(y_true != y_pred)[0]
        
        return {
            'error_count': len(errors),
            'error_rate': float(len(errors) / len(y_true)),
            'sample_errors': errors[:10].tolist(),
        }
    
    def _generate_recommendations_anomaly(
        self,
        metrics: Dict[str, float],
        threshold_analysis: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for anomaly detection."""
        recommendations = []
        
        if metrics.get('recall', 0) < 0.7:
            recommendations.append(
                "Low recall - consider lowering the threshold to catch more anomalies"
            )
        
        if metrics.get('precision', 0) < 0.5:
            recommendations.append(
                "Low precision - too many false positives. Consider raising the threshold."
            )
        
        if metrics.get('anomaly_rate', 0) > 0.2:
            recommendations.append(
                "High anomaly rate detected. Review data quality or adjust contamination parameter."
            )
        
        return recommendations
    
    def _generate_recommendations_classifier(
        self,
        metrics: Dict[str, float],
        error_analysis: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for classification."""
        recommendations = []
        
        if metrics.get('accuracy', 0) < 0.8:
            recommendations.append(
                "Accuracy below 80%. Consider feature engineering or trying different models."
            )
        
        if error_analysis.get('error_rate', 0) > 0.1:
            recommendations.append(
                "Error rate above 10%. Analyze error patterns for improvement opportunities."
            )
        
        return recommendations
```

---

## 3. Key Takeaways

1. **Proper Splits**: Use time-aware splits for operational data
2. **Imbalance Handling**: Critical for incident detection (rare events)
3. **Threshold Tuning**: Optimize for your operational needs
4. **Cross-Validation**: Validate model stability
5. **Error Analysis**: Understand failure modes

## Next Session Preview
- Session 20: Deploying ML Models to Production
