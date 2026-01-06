# Session 18: Feature Engineering Best Practices

## Learning Objectives
- Advanced feature engineering techniques
- Handle time-series features for operations
- Feature selection and dimensionality reduction
- Build reusable feature pipelines

## Duration: 1 hour

---

## 1. Advanced Feature Engineering

### Domain-Specific Features for AIOps

```python
# File: training-plan/ecommerce-app/ml/features/advanced_features.py
"""
Advanced feature engineering for AIOps.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from scipy import signal
from scipy.fft import fft
import warnings

warnings.filterwarnings('ignore')


@dataclass
class ServiceMetrics:
    """Metrics for a service."""
    service_name: str
    cpu: List[float]
    memory: List[float]
    latency: List[float]
    request_count: List[float]
    error_count: List[float]
    timestamps: List[datetime]


class AdvancedFeatureExtractor:
    """
    Advanced feature extraction for operational data.
    """
    
    def extract_fourier_features(
        self,
        values: List[float],
        n_components: int = 5
    ) -> Dict[str, float]:
        """
        Extract frequency domain features using FFT.
        Useful for detecting periodic patterns.
        """
        if len(values) < 10:
            return {}
        
        arr = np.array(values)
        
        # Remove trend
        detrended = signal.detrend(arr)
        
        # Compute FFT
        fft_values = fft(detrended)
        fft_magnitudes = np.abs(fft_values[:len(fft_values)//2])
        fft_frequencies = np.fft.fftfreq(len(fft_values))[:len(fft_values)//2]
        
        features = {}
        
        # Top frequency components
        top_indices = np.argsort(fft_magnitudes)[-n_components:]
        for i, idx in enumerate(top_indices):
            features[f'fft_freq_{i}'] = float(fft_frequencies[idx])
            features[f'fft_magnitude_{i}'] = float(fft_magnitudes[idx])
        
        # Dominant frequency
        features['dominant_freq'] = float(fft_frequencies[np.argmax(fft_magnitudes)])
        features['spectral_entropy'] = float(
            -np.sum(fft_magnitudes * np.log(fft_magnitudes + 1e-10)) / 
            np.log(len(fft_magnitudes))
        )
        
        return features
    
    def extract_wavelet_features(
        self,
        values: List[float],
        levels: int = 3
    ) -> Dict[str, float]:
        """
        Extract wavelet features for multi-scale analysis.
        """
        try:
            import pywt
        except ImportError:
            return {}
        
        if len(values) < 2**levels:
            return {}
        
        arr = np.array(values)
        
        # Perform wavelet decomposition
        coeffs = pywt.wavedec(arr, 'db4', level=levels)
        
        features = {}
        for i, coeff in enumerate(coeffs):
            level_name = 'approx' if i == 0 else f'detail_{i}'
            features[f'wavelet_{level_name}_energy'] = float(np.sum(coeff**2))
            features[f'wavelet_{level_name}_std'] = float(np.std(coeff))
        
        return features
    
    def extract_change_point_features(
        self,
        values: List[float],
        window_size: int = 10
    ) -> Dict[str, Any]:
        """
        Detect change points in time series.
        """
        if len(values) < window_size * 2:
            return {}
        
        arr = np.array(values)
        
        # Calculate running statistics
        n = len(arr)
        change_scores = []
        
        for i in range(window_size, n - window_size):
            before = arr[i-window_size:i]
            after = arr[i:i+window_size]
            
            # T-test for change detection
            from scipy.stats import ttest_ind
            _, p_value = ttest_ind(before, after)
            change_scores.append(1 - p_value)
        
        change_scores = np.array(change_scores)
        
        # Find significant change points
        threshold = 0.95
        change_points = np.where(change_scores > threshold)[0] + window_size
        
        features = {
            'num_change_points': len(change_points),
            'max_change_score': float(np.max(change_scores)) if len(change_scores) > 0 else 0,
            'mean_change_score': float(np.mean(change_scores)) if len(change_scores) > 0 else 0,
            'has_recent_change': len(change_points) > 0 and change_points[-1] > n - window_size
        }
        
        return features
    
    def extract_seasonality_features(
        self,
        values: List[float],
        expected_period: int = 24
    ) -> Dict[str, float]:
        """
        Extract seasonality-related features.
        """
        if len(values) < expected_period * 2:
            return {}
        
        arr = np.array(values)
        
        # Autocorrelation at expected period
        n = len(arr)
        mean = np.mean(arr)
        var = np.var(arr)
        
        if var == 0:
            return {'seasonality_strength': 0}
        
        autocorr = np.correlate(arr - mean, arr - mean, mode='full')
        autocorr = autocorr[n-1:] / (var * np.arange(n, 0, -1))
        
        features = {
            'autocorr_lag1': float(autocorr[1]) if len(autocorr) > 1 else 0,
            'autocorr_lag_period': float(autocorr[expected_period]) if len(autocorr) > expected_period else 0,
        }
        
        # Seasonality strength
        if len(autocorr) > expected_period:
            seasonal_peaks = autocorr[expected_period::expected_period]
            features['seasonality_strength'] = float(np.mean(seasonal_peaks[:5])) if len(seasonal_peaks) > 0 else 0
        else:
            features['seasonality_strength'] = 0
        
        return features
    
    def extract_resource_utilization_features(
        self,
        metrics: ServiceMetrics
    ) -> Dict[str, float]:
        """
        Extract features specific to resource utilization.
        """
        features = {}
        
        # CPU features
        cpu = np.array(metrics.cpu)
        features['cpu_utilization_avg'] = float(np.mean(cpu))
        features['cpu_headroom'] = float(100 - np.percentile(cpu, 95))
        features['cpu_spike_count'] = int(np.sum(cpu > 80))
        features['cpu_critical_count'] = int(np.sum(cpu > 95))
        
        # Memory features
        memory = np.array(metrics.memory)
        features['memory_utilization_avg'] = float(np.mean(memory))
        features['memory_headroom'] = float(100 - np.percentile(memory, 95))
        features['memory_spike_count'] = int(np.sum(memory > 80))
        features['memory_leak_indicator'] = float(np.polyfit(range(len(memory)), memory, 1)[0])
        
        # Latency features
        latency = np.array(metrics.latency)
        features['latency_avg'] = float(np.mean(latency))
        features['latency_p99'] = float(np.percentile(latency, 99))
        features['latency_stability'] = float(np.std(latency) / (np.mean(latency) + 1e-10))
        features['latency_degradation'] = float(
            np.mean(latency[-len(latency)//4:]) / (np.mean(latency[:len(latency)//4]) + 1e-10) - 1
        )
        
        # Error rate features
        if len(metrics.request_count) > 0 and len(metrics.error_count) > 0:
            error_rate = np.array(metrics.error_count) / (np.array(metrics.request_count) + 1e-10)
            features['error_rate_avg'] = float(np.mean(error_rate))
            features['error_rate_max'] = float(np.max(error_rate))
            features['error_rate_trend'] = float(np.polyfit(range(len(error_rate)), error_rate, 1)[0])
        
        # Resource correlation
        if len(cpu) == len(latency):
            features['cpu_latency_corr'] = float(np.corrcoef(cpu, latency)[0, 1])
        if len(memory) == len(latency):
            features['memory_latency_corr'] = float(np.corrcoef(memory, latency)[0, 1])
        
        return features
    
    def extract_service_health_features(
        self,
        metrics: ServiceMetrics,
        sla_latency: float = 500,
        sla_error_rate: float = 0.01
    ) -> Dict[str, float]:
        """
        Extract service health features based on SLAs.
        """
        features = {}
        
        latency = np.array(metrics.latency)
        request_count = np.array(metrics.request_count)
        error_count = np.array(metrics.error_count)
        
        # SLA compliance
        latency_compliant = np.sum(latency <= sla_latency) / len(latency)
        features['latency_sla_compliance'] = float(latency_compliant)
        
        if len(request_count) > 0:
            error_rate = error_count / (request_count + 1e-10)
            error_rate_compliant = np.sum(error_rate <= sla_error_rate) / len(error_rate)
            features['error_rate_sla_compliance'] = float(error_rate_compliant)
        
        # Availability estimation
        features['estimated_availability'] = float(
            1 - np.sum(error_count) / (np.sum(request_count) + 1e-10)
        )
        
        # Health score (composite)
        health_factors = [
            features.get('latency_sla_compliance', 0.5),
            features.get('error_rate_sla_compliance', 0.5),
            features.get('estimated_availability', 0.5)
        ]
        features['health_score'] = float(np.mean(health_factors))
        
        return features


class FeatureSelector:
    """
    Select important features for ML models.
    """
    
    def __init__(self, max_features: int = 50):
        self.max_features = max_features
        self.selected_features: List[str] = []
        self.feature_importance: Dict[str, float] = {}
    
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str]
    ) -> 'FeatureSelector':
        """
        Fit feature selector using various methods.
        """
        from sklearn.feature_selection import mutual_info_classif, f_classif
        from sklearn.ensemble import RandomForestClassifier
        
        # Mutual information
        mi_scores = mutual_info_classif(X, y)
        
        # Random Forest importance
        rf = RandomForestClassifier(n_estimators=50, random_state=42)
        rf.fit(X, y)
        rf_importance = rf.feature_importances_
        
        # Combine scores
        combined_scores = (mi_scores / (mi_scores.max() + 1e-10) + 
                         rf_importance / (rf_importance.max() + 1e-10)) / 2
        
        # Store importance
        self.feature_importance = {
            name: float(score)
            for name, score in zip(feature_names, combined_scores)
        }
        
        # Select top features
        sorted_features = sorted(
            self.feature_importance.items(),
            key=lambda x: x[1],
            reverse=True
        )
        self.selected_features = [f[0] for f in sorted_features[:self.max_features]]
        
        return self
    
    def transform(
        self,
        X: np.ndarray,
        feature_names: List[str]
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Transform data to selected features only.
        """
        indices = [
            i for i, name in enumerate(feature_names)
            if name in self.selected_features
        ]
        
        return X[:, indices], [feature_names[i] for i in indices]
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores."""
        return self.feature_importance
```

---

## 2. Feature Pipeline

### Reusable Feature Pipeline

```python
# File: training-plan/ecommerce-app/ml/features/feature_pipeline.py
"""
Reusable feature engineering pipeline.
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import json

import numpy as np


@dataclass
class FeaturePipelineConfig:
    """Configuration for feature pipeline."""
    name: str
    version: str
    steps: List[Dict[str, Any]]
    metadata: Dict[str, Any] = None


class FeatureStep:
    """Base class for feature pipeline steps."""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
    
    def fit(self, data: Any) -> 'FeatureStep':
        """Fit the step (if needed)."""
        return self
    
    def transform(self, data: Any) -> Any:
        """Transform data."""
        raise NotImplementedError
    
    def fit_transform(self, data: Any) -> Any:
        """Fit and transform."""
        return self.fit(data).transform(data)


class NormalizationStep(FeatureStep):
    """Normalize numeric features."""
    
    def __init__(self, method: str = 'zscore'):
        super().__init__('normalization', {'method': method})
        self.stats: Dict[str, Dict[str, float]] = {}
    
    def fit(self, data: Dict[str, np.ndarray]) -> 'NormalizationStep':
        """Compute normalization statistics."""
        for key, values in data.items():
            if isinstance(values, np.ndarray) and values.dtype in [np.float64, np.float32, np.int64]:
                self.stats[key] = {
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)),
                    'min': float(np.min(values)),
                    'max': float(np.max(values))
                }
        return self
    
    def transform(self, data: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Apply normalization."""
        result = {}
        for key, values in data.items():
            if key in self.stats:
                stats = self.stats[key]
                if self.config['method'] == 'zscore':
                    result[key] = (values - stats['mean']) / (stats['std'] + 1e-10)
                elif self.config['method'] == 'minmax':
                    result[key] = (values - stats['min']) / (stats['max'] - stats['min'] + 1e-10)
                else:
                    result[key] = values
            else:
                result[key] = values
        return result


class AggregationStep(FeatureStep):
    """Aggregate features over windows."""
    
    def __init__(self, window_sizes: List[int], aggregations: List[str]):
        super().__init__('aggregation', {
            'window_sizes': window_sizes,
            'aggregations': aggregations
        })
    
    def transform(self, data: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Apply aggregations."""
        result = dict(data)
        
        for key, values in data.items():
            if not isinstance(values, np.ndarray):
                continue
            
            for window in self.config['window_sizes']:
                if len(values) < window:
                    continue
                
                for agg in self.config['aggregations']:
                    agg_values = []
                    for i in range(len(values)):
                        start = max(0, i - window + 1)
                        window_data = values[start:i+1]
                        
                        if agg == 'mean':
                            agg_values.append(np.mean(window_data))
                        elif agg == 'std':
                            agg_values.append(np.std(window_data))
                        elif agg == 'min':
                            agg_values.append(np.min(window_data))
                        elif agg == 'max':
                            agg_values.append(np.max(window_data))
                    
                    result[f'{key}_{agg}_{window}'] = np.array(agg_values)
        
        return result


class FeaturePipeline:
    """
    Configurable feature engineering pipeline.
    """
    
    def __init__(self, config: FeaturePipelineConfig):
        self.config = config
        self.steps: List[FeatureStep] = []
        self._build_pipeline()
    
    def _build_pipeline(self) -> None:
        """Build pipeline from config."""
        for step_config in self.config.steps:
            step_type = step_config['type']
            step_params = step_config.get('params', {})
            
            if step_type == 'normalization':
                self.steps.append(NormalizationStep(**step_params))
            elif step_type == 'aggregation':
                self.steps.append(AggregationStep(**step_params))
            else:
                raise ValueError(f"Unknown step type: {step_type}")
    
    def fit(self, data: Any) -> 'FeaturePipeline':
        """Fit all steps."""
        current_data = data
        for step in self.steps:
            step.fit(current_data)
            current_data = step.transform(current_data)
        return self
    
    def transform(self, data: Any) -> Any:
        """Transform data through all steps."""
        current_data = data
        for step in self.steps:
            current_data = step.transform(current_data)
        return current_data
    
    def fit_transform(self, data: Any) -> Any:
        """Fit and transform."""
        return self.fit(data).transform(data)
    
    def save(self, path: str) -> None:
        """Save pipeline configuration and fitted state."""
        state = {
            'config': {
                'name': self.config.name,
                'version': self.config.version,
                'steps': self.config.steps,
                'metadata': self.config.metadata
            },
            'fitted_state': {
                step.name: step.stats if hasattr(step, 'stats') else {}
                for step in self.steps
            }
        }
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> 'FeaturePipeline':
        """Load pipeline from saved state."""
        with open(path, 'r') as f:
            state = json.load(f)
        
        config = FeaturePipelineConfig(**state['config'])
        pipeline = cls(config)
        
        # Restore fitted state
        for step in pipeline.steps:
            if step.name in state['fitted_state'] and hasattr(step, 'stats'):
                step.stats = state['fitted_state'][step.name]
        
        return pipeline
```

---

## 3. Key Takeaways

1. **Frequency Features**: FFT reveals periodic patterns in metrics
2. **Change Detection**: Identify sudden shifts in behavior
3. **Domain Features**: Resource utilization and health metrics
4. **Feature Selection**: Reduce dimensionality for better models
5. **Pipeline Pattern**: Reusable, configurable feature engineering

## Next Session Preview
- Session 19: Model Training and Evaluation
