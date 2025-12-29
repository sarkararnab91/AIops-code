# Session 15: Capacity Planning and Forecasting

## Learning Objectives
- Implement time series forecasting with Prophet
- Build capacity planning models
- Create automated scaling recommendations
- Predict resource requirements

## Duration: 1 hour

---

## 1. Prophet-Based Forecasting

### Resource Forecasting Service

```python
# File: training-plan/ecommerce-app/ml/forecasting/capacity_planner.py
"""
Capacity planning using Prophet for time series forecasting.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ForecastResult:
    """Forecast result with confidence intervals."""
    timestamp: datetime
    predicted_value: float
    lower_bound: float
    upper_bound: float
    confidence: float = 0.95


@dataclass
class CapacityPlan:
    """Capacity planning recommendation."""
    resource: str
    current_capacity: float
    predicted_peak: float
    recommended_capacity: float
    scale_time: Optional[datetime]
    urgency: str  # 'low', 'medium', 'high', 'critical'
    reasoning: str


class ProphetForecaster:
    """
    Time series forecasting using Facebook Prophet.
    """
    
    def __init__(
        self,
        seasonality_mode: str = 'multiplicative',
        changepoint_prior_scale: float = 0.05,
        yearly_seasonality: bool = True,
        weekly_seasonality: bool = True,
        daily_seasonality: bool = True
    ):
        self.seasonality_mode = seasonality_mode
        self.changepoint_prior_scale = changepoint_prior_scale
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.daily_seasonality = daily_seasonality
        self.model = None
        self.is_fitted = False
    
    def fit(
        self,
        timestamps: List[datetime],
        values: List[float],
        holidays: Optional[pd.DataFrame] = None
    ) -> 'ProphetForecaster':
        """
        Fit the Prophet model.
        
        Args:
            timestamps: List of timestamps
            values: List of metric values
            holidays: Optional DataFrame with holiday dates
        """
        try:
            from prophet import Prophet
        except ImportError:
            raise ImportError("Prophet not installed. Run: pip install prophet")
        
        # Prepare data in Prophet format
        df = pd.DataFrame({
            'ds': timestamps,
            'y': values
        })
        
        # Remove any NaN values
        df = df.dropna()
        
        # Initialize Prophet
        self.model = Prophet(
            seasonality_mode=self.seasonality_mode,
            changepoint_prior_scale=self.changepoint_prior_scale,
            yearly_seasonality=self.yearly_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=self.daily_seasonality
        )
        
        # Add holidays if provided
        if holidays is not None:
            self.model.add_country_holidays(country_name='US')
        
        # Fit model
        self.model.fit(df)
        self.is_fitted = True
        
        return self
    
    def predict(
        self,
        periods: int,
        freq: str = 'H'
    ) -> List[ForecastResult]:
        """
        Generate forecast for future periods.
        
        Args:
            periods: Number of periods to forecast
            freq: Frequency ('H'=hourly, 'D'=daily, 'W'=weekly)
            
        Returns:
            List of ForecastResult objects
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        
        # Create future dataframe
        future = self.model.make_future_dataframe(
            periods=periods,
            freq=freq
        )
        
        # Generate predictions
        forecast = self.model.predict(future)
        
        # Extract results for future periods only
        results = []
        for _, row in forecast.tail(periods).iterrows():
            results.append(ForecastResult(
                timestamp=row['ds'].to_pydatetime(),
                predicted_value=row['yhat'],
                lower_bound=row['yhat_lower'],
                upper_bound=row['yhat_upper'],
                confidence=0.95
            ))
        
        return results
    
    def get_components(self) -> Dict[str, pd.DataFrame]:
        """Get forecast components (trend, seasonality)."""
        if not self.is_fitted:
            raise RuntimeError("Model not fitted.")
        
        return {
            'trend': self.model.plot_components,
            'seasonalities': {
                'weekly': 'weekly_seasonality',
                'daily': 'daily_seasonality',
                'yearly': 'yearly_seasonality'
            }
        }


class CapacityPlanner:
    """
    Capacity planning using forecasting.
    """
    
    def __init__(
        self,
        safety_margin: float = 0.2,  # 20% safety margin
        scale_lead_time_hours: int = 24  # Time needed to scale
    ):
        self.safety_margin = safety_margin
        self.scale_lead_time_hours = scale_lead_time_hours
        self.forecasters: Dict[str, ProphetForecaster] = {}
    
    def train(
        self,
        resource_name: str,
        historical_data: pd.DataFrame
    ) -> None:
        """
        Train forecaster for a resource.
        
        Args:
            resource_name: Name of the resource (e.g., 'cpu', 'memory', 'requests')
            historical_data: DataFrame with 'timestamp' and 'value' columns
        """
        forecaster = ProphetForecaster()
        forecaster.fit(
            timestamps=historical_data['timestamp'].tolist(),
            values=historical_data['value'].tolist()
        )
        self.forecasters[resource_name] = forecaster
    
    def generate_capacity_plan(
        self,
        resource_name: str,
        current_capacity: float,
        forecast_days: int = 30
    ) -> CapacityPlan:
        """
        Generate capacity plan for a resource.
        """
        if resource_name not in self.forecasters:
            raise ValueError(f"No forecaster trained for {resource_name}")
        
        forecaster = self.forecasters[resource_name]
        
        # Get forecast
        forecast = forecaster.predict(periods=forecast_days * 24, freq='H')
        
        # Find predicted peak
        peak_forecast = max(forecast, key=lambda x: x.upper_bound)
        predicted_peak = peak_forecast.upper_bound
        
        # Calculate recommended capacity with safety margin
        recommended = predicted_peak * (1 + self.safety_margin)
        
        # Determine urgency
        utilization = predicted_peak / current_capacity
        
        if utilization > 0.95:
            urgency = 'critical'
            scale_time = datetime.now() + timedelta(hours=1)
        elif utilization > 0.85:
            urgency = 'high'
            scale_time = datetime.now() + timedelta(hours=self.scale_lead_time_hours)
        elif utilization > 0.7:
            urgency = 'medium'
            scale_time = peak_forecast.timestamp - timedelta(days=3)
        else:
            urgency = 'low'
            scale_time = None
        
        reasoning = self._generate_reasoning(
            current_capacity, predicted_peak, utilization, peak_forecast.timestamp
        )
        
        return CapacityPlan(
            resource=resource_name,
            current_capacity=current_capacity,
            predicted_peak=predicted_peak,
            recommended_capacity=recommended,
            scale_time=scale_time,
            urgency=urgency,
            reasoning=reasoning
        )
    
    def _generate_reasoning(
        self,
        current: float,
        peak: float,
        utilization: float,
        peak_time: datetime
    ) -> str:
        """Generate human-readable reasoning."""
        return (
            f"Based on historical patterns, peak demand of {peak:.2f} is expected "
            f"around {peak_time.strftime('%Y-%m-%d %H:%M')}. "
            f"Current capacity ({current:.2f}) would result in {utilization:.1%} utilization. "
            f"{'Scaling is recommended.' if utilization > 0.7 else 'Current capacity is sufficient.'}"
        )
    
    def optimize_cost(
        self,
        resource_forecasts: Dict[str, List[ForecastResult]],
        pricing: Dict[str, float],
        min_capacity: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Optimize capacity allocation for cost efficiency.
        
        Returns scaling schedule that minimizes cost while meeting demand.
        """
        schedule = []
        total_cost = 0.0
        
        for resource, forecasts in resource_forecasts.items():
            price_per_unit = pricing.get(resource, 1.0)
            min_cap = min_capacity.get(resource, 0)
            
            # Group by day and find daily peaks
            daily_peaks = {}
            for f in forecasts:
                day = f.timestamp.date()
                if day not in daily_peaks:
                    daily_peaks[day] = f.upper_bound
                else:
                    daily_peaks[day] = max(daily_peaks[day], f.upper_bound)
            
            # Create scaling schedule
            for day, peak in sorted(daily_peaks.items()):
                capacity = max(peak * (1 + self.safety_margin), min_cap)
                cost = capacity * price_per_unit * 24  # Daily cost
                
                schedule.append({
                    'date': day.isoformat(),
                    'resource': resource,
                    'capacity': capacity,
                    'peak_demand': peak,
                    'cost': cost
                })
                total_cost += cost
        
        return {
            'schedule': schedule,
            'total_cost': total_cost,
            'optimization_notes': [
                'Consider reserved instances for baseline capacity',
                'Use spot instances for burst capacity',
                'Review after 30 days with actual data'
            ]
        }


class AutoScalingRecommender:
    """
    Generates auto-scaling recommendations based on forecasts.
    """
    
    def __init__(self, capacity_planner: CapacityPlanner):
        self.planner = capacity_planner
    
    def recommend_hpa_config(
        self,
        service_name: str,
        cpu_forecast: List[ForecastResult],
        memory_forecast: List[ForecastResult],
        current_replicas: int,
        pod_cpu_limit: float,
        pod_memory_limit: float
    ) -> Dict[str, Any]:
        """
        Recommend Kubernetes HPA configuration.
        """
        # Calculate required replicas based on CPU
        cpu_peaks = [f.upper_bound for f in cpu_forecast]
        max_cpu = max(cpu_peaks)
        cpu_replicas = int(np.ceil(max_cpu / (pod_cpu_limit * 0.8)))  # 80% target
        
        # Calculate required replicas based on memory
        mem_peaks = [f.upper_bound for f in memory_forecast]
        max_mem = max(mem_peaks)
        mem_replicas = int(np.ceil(max_mem / (pod_memory_limit * 0.8)))
        
        # Take the higher of the two
        recommended_max = max(cpu_replicas, mem_replicas)
        recommended_min = max(1, recommended_max // 3)  # Min is 1/3 of max
        
        return {
            'service': service_name,
            'hpa_config': {
                'apiVersion': 'autoscaling/v2',
                'kind': 'HorizontalPodAutoscaler',
                'metadata': {'name': f'{service_name}-hpa'},
                'spec': {
                    'scaleTargetRef': {
                        'apiVersion': 'apps/v1',
                        'kind': 'Deployment',
                        'name': service_name
                    },
                    'minReplicas': recommended_min,
                    'maxReplicas': recommended_max,
                    'metrics': [
                        {
                            'type': 'Resource',
                            'resource': {
                                'name': 'cpu',
                                'target': {
                                    'type': 'Utilization',
                                    'averageUtilization': 80
                                }
                            }
                        },
                        {
                            'type': 'Resource',
                            'resource': {
                                'name': 'memory',
                                'target': {
                                    'type': 'Utilization',
                                    'averageUtilization': 80
                                }
                            }
                        }
                    ]
                }
            },
            'reasoning': {
                'cpu_based_replicas': cpu_replicas,
                'memory_based_replicas': mem_replicas,
                'current_replicas': current_replicas,
                'scaling_factor': recommended_max / current_replicas if current_replicas > 0 else 0
            }
        }
    
    def recommend_keda_config(
        self,
        service_name: str,
        request_forecast: List[ForecastResult],
        requests_per_pod: int = 100
    ) -> Dict[str, Any]:
        """
        Recommend KEDA ScaledObject configuration.
        """
        max_requests = max(f.upper_bound for f in request_forecast)
        min_requests = min(f.lower_bound for f in request_forecast)
        
        max_replicas = int(np.ceil(max_requests / requests_per_pod))
        min_replicas = max(0, int(np.floor(min_requests / requests_per_pod)))  # KEDA can scale to 0
        
        return {
            'service': service_name,
            'keda_config': {
                'apiVersion': 'keda.sh/v1alpha1',
                'kind': 'ScaledObject',
                'metadata': {'name': f'{service_name}-scaledobject'},
                'spec': {
                    'scaleTargetRef': {
                        'name': service_name
                    },
                    'pollingInterval': 15,
                    'cooldownPeriod': 300,
                    'minReplicaCount': min_replicas,
                    'maxReplicaCount': max_replicas,
                    'triggers': [
                        {
                            'type': 'prometheus',
                            'metadata': {
                                'serverAddress': 'http://prometheus:9090',
                                'metricName': 'http_requests_total',
                                'threshold': str(requests_per_pod),
                                'query': f'sum(rate(http_requests_total{{service="{service_name}"}}[1m]))'
                            }
                        }
                    ]
                }
            },
            'forecast_summary': {
                'peak_requests_per_minute': max_requests,
                'min_requests_per_minute': min_requests,
                'recommended_pods_at_peak': max_replicas
            }
        }
```

---

## 2. Hands-On Exercise

### Build a Capacity Planning Dashboard

```python
# File: training-plan/ecommerce-app/ml/exercises/capacity_exercise.py
"""
Exercise: Build a capacity planning system.
"""

import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_traffic_data(days: int = 90) -> pd.DataFrame:
    """
    Generate realistic e-commerce traffic data with patterns.
    
    Patterns included:
    - Daily cycle (peak at noon and evening)
    - Weekly cycle (higher on weekends)
    - Monthly trend (growth)
    - Holiday spikes
    """
    timestamps = []
    values = []
    
    start = datetime.now() - timedelta(days=days)
    
    for hour in range(days * 24):
        ts = start + timedelta(hours=hour)
        
        # Base traffic
        base = 1000
        
        # Daily pattern (peaks at 12pm and 7pm)
        hour_of_day = ts.hour
        daily = 500 * (np.sin(np.pi * (hour_of_day - 6) / 12) + 1)
        evening_boost = 300 if 18 <= hour_of_day <= 22 else 0
        
        # Weekly pattern (higher on weekends)
        day_of_week = ts.weekday()
        weekly = 200 if day_of_week >= 5 else 0  # Weekend boost
        
        # Monthly trend (5% growth per month)
        days_elapsed = (ts - start).days
        trend = base * 0.05 * (days_elapsed / 30)
        
        # Random noise
        noise = random.gauss(0, 100)
        
        # Holiday spikes (random)
        holiday_spike = random.choice([0, 0, 0, 0, 500]) if day_of_week >= 5 else 0
        
        traffic = base + daily + evening_boost + weekly + trend + noise + holiday_spike
        traffic = max(0, traffic)
        
        timestamps.append(ts)
        values.append(traffic)
    
    return pd.DataFrame({
        'timestamp': timestamps,
        'value': values
    })


EXERCISE = """
# Capacity Planning Exercise

## Objective
Build a capacity planning system that:
1. Forecasts future resource demands
2. Generates scaling recommendations
3. Optimizes cost while meeting SLAs

## Tasks

### Task 1: Data Exploration (10 minutes)
1. Load the generated traffic data
2. Visualize daily, weekly, and monthly patterns
3. Identify trends and seasonality

### Task 2: Build Forecaster (20 minutes)
1. Train a Prophet model on the historical data
2. Generate 30-day forecast
3. Evaluate forecast accuracy using holdout data

### Task 3: Capacity Planning (20 minutes)
1. Given current capacity, determine if scaling is needed
2. Calculate recommended capacity with safety margin
3. Generate scaling schedule

### Task 4: Auto-Scaling Config (10 minutes)
1. Generate HPA configuration
2. Generate KEDA configuration
3. Document reasoning

## Starter Code
```python
from capacity_planner import ProphetForecaster, CapacityPlanner

# Generate data
traffic_data = generate_traffic_data(90)

# Split into train/test
train_data = traffic_data.iloc[:-7*24]  # All but last week
test_data = traffic_data.iloc[-7*24:]   # Last week

# Task 1: Explore data
print(traffic_data.describe())

# Task 2: Train forecaster
# TODO: Initialize and train ProphetForecaster

# Task 3: Generate capacity plan
# TODO: Generate capacity recommendations

# Task 4: Auto-scaling config
# TODO: Generate HPA/KEDA configurations
```

## Expected Output
- 30-day traffic forecast with confidence intervals
- Scaling recommendations with urgency levels
- HPA and KEDA configurations
- Cost optimization schedule
"""


if __name__ == "__main__":
    print(EXERCISE)
    
    # Solution demonstration
    print("\n--- Solution Demo ---\n")
    
    # Generate data
    print("Generating 90 days of traffic data...")
    traffic_data = generate_traffic_data(90)
    
    print(f"Data range: {traffic_data['timestamp'].min()} to {traffic_data['timestamp'].max()}")
    print(f"Traffic range: {traffic_data['value'].min():.0f} to {traffic_data['value'].max():.0f}")
    
    # Note: Full solution requires Prophet installation
    print("\nTo run full solution:")
    print("  pip install prophet")
    print("  Then run the capacity_planner module")
```

---

## 3. Key Takeaways

1. **Prophet**: Excellent for time series with multiple seasonalities
2. **Safety Margins**: Always plan for more capacity than predicted
3. **Lead Time**: Consider how long scaling takes
4. **Cost Optimization**: Balance performance with cost
5. **Auto-Scaling**: Use HPA for CPU/memory, KEDA for custom metrics

## Next Session Preview
- Session 16: Integrating ML Models into Operations Pipeline
