# Session 17: Building the AIOps Data Pipeline

## Learning Objectives
- Design data pipelines for operational data
- Implement feature engineering for ML models
- Build real-time and batch processing pipelines
- Create data quality monitoring

## Duration: 1 hour

---

## 1. Data Pipeline Architecture

### Unified Data Pipeline

```python
# File: training-plan/ecommerce-app/ml/pipeline/data_pipeline.py
"""
Data pipeline for AIOps ML models.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import json

import numpy as np
from azure.servicebus.aio import ServiceBusClient
from azure.cosmos.aio import CosmosClient


class DataSource(str, Enum):
    AZURE_MONITOR = "azure_monitor"
    LOG_ANALYTICS = "log_analytics"
    SERVICE_BUS = "service_bus"
    COSMOS_DB = "cosmos_db"
    PROMETHEUS = "prometheus"


@dataclass
class DataRecord:
    """A single data record in the pipeline."""
    source: DataSource
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'source': self.source.value,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'metadata': self.metadata
        }


@dataclass
class PipelineConfig:
    """Configuration for data pipeline."""
    batch_size: int = 100
    batch_timeout_seconds: int = 10
    max_retries: int = 3
    enable_deduplication: bool = True
    enable_validation: bool = True


class DataIngester:
    """
    Ingests data from multiple sources.
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.sources: Dict[DataSource, Callable] = {}
        self.buffer: deque = deque(maxlen=10000)
    
    def register_source(
        self,
        source: DataSource,
        handler: Callable
    ) -> None:
        """Register a data source handler."""
        self.sources[source] = handler
    
    async def ingest_from_azure_monitor(
        self,
        workspace_id: str,
        query: str,
        timespan: timedelta
    ) -> AsyncIterator[DataRecord]:
        """Ingest data from Azure Monitor."""
        from azure.monitor.query.aio import LogsQueryClient
        from azure.identity.aio import DefaultAzureCredential
        
        async with DefaultAzureCredential() as credential:
            async with LogsQueryClient(credential) as client:
                response = await client.query_workspace(
                    workspace_id=workspace_id,
                    query=query,
                    timespan=timespan
                )
                
                for table in response.tables:
                    for row in table.rows:
                        yield DataRecord(
                            source=DataSource.AZURE_MONITOR,
                            timestamp=row[0] if isinstance(row[0], datetime) else datetime.now(),
                            data=dict(zip([c.name for c in table.columns], row)),
                            metadata={'workspace_id': workspace_id}
                        )
    
    async def ingest_from_service_bus(
        self,
        connection_string: str,
        queue_name: str,
        max_messages: int = 100
    ) -> AsyncIterator[DataRecord]:
        """Ingest data from Azure Service Bus."""
        async with ServiceBusClient.from_connection_string(connection_string) as client:
            async with client.get_queue_receiver(queue_name) as receiver:
                messages = await receiver.receive_messages(
                    max_message_count=max_messages,
                    max_wait_time=5
                )
                
                for msg in messages:
                    try:
                        data = json.loads(str(msg))
                        yield DataRecord(
                            source=DataSource.SERVICE_BUS,
                            timestamp=datetime.now(),
                            data=data,
                            metadata={'queue': queue_name}
                        )
                        await receiver.complete_message(msg)
                    except Exception as e:
                        await receiver.dead_letter_message(msg, str(e))
    
    async def batch_ingest(
        self,
        records: AsyncIterator[DataRecord]
    ) -> AsyncIterator[List[DataRecord]]:
        """Batch records for processing."""
        batch = []
        last_flush = datetime.now()
        
        async for record in records:
            batch.append(record)
            
            should_flush = (
                len(batch) >= self.config.batch_size or
                (datetime.now() - last_flush).seconds >= self.config.batch_timeout_seconds
            )
            
            if should_flush and batch:
                yield batch
                batch = []
                last_flush = datetime.now()
        
        if batch:
            yield batch


class DataTransformer:
    """
    Transforms raw data for ML consumption.
    """
    
    def __init__(self):
        self.transformers: Dict[str, Callable] = {}
    
    def register_transformer(
        self,
        name: str,
        transform_fn: Callable
    ) -> None:
        """Register a transformation function."""
        self.transformers[name] = transform_fn
    
    def normalize_metrics(
        self,
        records: List[DataRecord],
        metric_columns: List[str]
    ) -> List[DataRecord]:
        """Normalize metric values."""
        # Calculate statistics
        values = {col: [] for col in metric_columns}
        for record in records:
            for col in metric_columns:
                if col in record.data and record.data[col] is not None:
                    values[col].append(float(record.data[col]))
        
        stats = {
            col: {'mean': np.mean(v), 'std': np.std(v) if len(v) > 1 else 1}
            for col, v in values.items() if v
        }
        
        # Normalize
        normalized = []
        for record in records:
            new_data = record.data.copy()
            for col in metric_columns:
                if col in new_data and col in stats:
                    new_data[f'{col}_normalized'] = (
                        (new_data[col] - stats[col]['mean']) / 
                        (stats[col]['std'] + 1e-10)
                    )
            
            normalized.append(DataRecord(
                source=record.source,
                timestamp=record.timestamp,
                data=new_data,
                metadata={**record.metadata, 'normalized': 'true'}
            ))
        
        return normalized
    
    def aggregate_by_time(
        self,
        records: List[DataRecord],
        interval_minutes: int = 5,
        aggregations: Dict[str, str] = None
    ) -> List[DataRecord]:
        """Aggregate records by time interval."""
        aggregations = aggregations or {'value': 'mean'}
        
        # Group by interval
        buckets: Dict[datetime, List[DataRecord]] = {}
        for record in records:
            bucket_time = record.timestamp.replace(
                minute=(record.timestamp.minute // interval_minutes) * interval_minutes,
                second=0,
                microsecond=0
            )
            if bucket_time not in buckets:
                buckets[bucket_time] = []
            buckets[bucket_time].append(record)
        
        # Aggregate
        aggregated = []
        for bucket_time, bucket_records in sorted(buckets.items()):
            agg_data = {}
            
            for col, agg_type in aggregations.items():
                values = [
                    r.data[col] for r in bucket_records
                    if col in r.data and r.data[col] is not None
                ]
                
                if values:
                    if agg_type == 'mean':
                        agg_data[col] = np.mean(values)
                    elif agg_type == 'sum':
                        agg_data[col] = np.sum(values)
                    elif agg_type == 'max':
                        agg_data[col] = np.max(values)
                    elif agg_type == 'min':
                        agg_data[col] = np.min(values)
                    elif agg_type == 'count':
                        agg_data[col] = len(values)
                    elif agg_type == 'p95':
                        agg_data[col] = np.percentile(values, 95)
                    elif agg_type == 'p99':
                        agg_data[col] = np.percentile(values, 99)
            
            agg_data['record_count'] = len(bucket_records)
            
            aggregated.append(DataRecord(
                source=bucket_records[0].source,
                timestamp=bucket_time,
                data=agg_data,
                metadata={'aggregation_interval': f'{interval_minutes}m'}
            ))
        
        return aggregated
    
    def enrich_with_context(
        self,
        records: List[DataRecord],
        context_data: Dict[str, Any]
    ) -> List[DataRecord]:
        """Enrich records with contextual information."""
        enriched = []
        for record in records:
            new_data = {**record.data}
            
            # Add time features
            ts = record.timestamp
            new_data['hour_of_day'] = ts.hour
            new_data['day_of_week'] = ts.weekday()
            new_data['is_weekend'] = ts.weekday() >= 5
            new_data['is_business_hours'] = 9 <= ts.hour <= 17
            
            # Add context
            service = record.data.get('service', record.metadata.get('service'))
            if service and service in context_data:
                for key, value in context_data[service].items():
                    new_data[f'context_{key}'] = value
            
            enriched.append(DataRecord(
                source=record.source,
                timestamp=record.timestamp,
                data=new_data,
                metadata={**record.metadata, 'enriched': 'true'}
            ))
        
        return enriched


class DataValidator:
    """
    Validates data quality.
    """
    
    def __init__(self):
        self.rules: List[Callable] = []
        self.validation_results: List[Dict] = []
    
    def add_rule(self, rule: Callable[[DataRecord], bool], name: str) -> None:
        """Add a validation rule."""
        self.rules.append((rule, name))
    
    def validate(self, records: List[DataRecord]) -> Dict[str, Any]:
        """Validate records and return report."""
        valid = []
        invalid = []
        
        for record in records:
            is_valid = True
            violations = []
            
            for rule, name in self.rules:
                try:
                    if not rule(record):
                        is_valid = False
                        violations.append(name)
                except Exception as e:
                    is_valid = False
                    violations.append(f"{name}: {str(e)}")
            
            if is_valid:
                valid.append(record)
            else:
                invalid.append({
                    'record': record.to_dict(),
                    'violations': violations
                })
        
        result = {
            'total': len(records),
            'valid': len(valid),
            'invalid': len(invalid),
            'validation_rate': len(valid) / len(records) if records else 0,
            'violations': invalid[:10]  # First 10 violations
        }
        
        self.validation_results.append({
            'timestamp': datetime.now().isoformat(),
            **result
        })
        
        return result


class FeatureStore:
    """
    Store and retrieve ML features.
    """
    
    def __init__(self, cosmos_client: CosmosClient = None):
        self.cosmos = cosmos_client
        self.cache: Dict[str, Dict] = {}
    
    async def store_features(
        self,
        entity_id: str,
        features: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Store features for an entity."""
        feature_record = {
            'id': f"{entity_id}_{timestamp.isoformat()}",
            'entity_id': entity_id,
            'features': features,
            'timestamp': timestamp.isoformat(),
            'created_at': datetime.now().isoformat()
        }
        
        if self.cosmos:
            container = self.cosmos.get_database_client('aiops').get_container_client('features')
            await container.upsert_item(feature_record)
        else:
            self.cache[feature_record['id']] = feature_record
    
    async def get_latest_features(
        self,
        entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the latest features for an entity."""
        if self.cosmos:
            container = self.cosmos.get_database_client('aiops').get_container_client('features')
            query = f"SELECT TOP 1 * FROM c WHERE c.entity_id = '{entity_id}' ORDER BY c.timestamp DESC"
            items = [item async for item in container.query_items(query)]
            return items[0]['features'] if items else None
        else:
            # Get from cache
            matching = [
                v for k, v in self.cache.items()
                if v['entity_id'] == entity_id
            ]
            if matching:
                latest = max(matching, key=lambda x: x['timestamp'])
                return latest['features']
            return None
    
    async def get_feature_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get feature history for an entity."""
        if self.cosmos:
            container = self.cosmos.get_database_client('aiops').get_container_client('features')
            query = f"""
                SELECT * FROM c 
                WHERE c.entity_id = '{entity_id}' 
                AND c.timestamp >= '{start_time.isoformat()}'
                AND c.timestamp <= '{end_time.isoformat()}'
                ORDER BY c.timestamp
            """
            return [item async for item in container.query_items(query)]
        else:
            return [
                v for v in self.cache.values()
                if v['entity_id'] == entity_id
                and start_time.isoformat() <= v['timestamp'] <= end_time.isoformat()
            ]
```

---

## 2. Feature Engineering

### Feature Engineering Pipeline

```python
# File: training-plan/ecommerce-app/ml/pipeline/feature_engineering.py
"""
Feature engineering for AIOps ML models.
"""

import numpy as np
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from scipy import stats as scipy_stats


class FeatureEngineer:
    """
    Creates ML features from operational data.
    """
    
    def __init__(self):
        self.feature_definitions: Dict[str, Callable] = {}
    
    def extract_statistical_features(
        self,
        values: List[float],
        prefix: str = ''
    ) -> Dict[str, float]:
        """Extract statistical features from a series."""
        if not values:
            return {}
        
        arr = np.array(values)
        
        features = {
            f'{prefix}mean': float(np.mean(arr)),
            f'{prefix}std': float(np.std(arr)),
            f'{prefix}min': float(np.min(arr)),
            f'{prefix}max': float(np.max(arr)),
            f'{prefix}median': float(np.median(arr)),
            f'{prefix}p25': float(np.percentile(arr, 25)),
            f'{prefix}p75': float(np.percentile(arr, 75)),
            f'{prefix}p90': float(np.percentile(arr, 90)),
            f'{prefix}p95': float(np.percentile(arr, 95)),
            f'{prefix}p99': float(np.percentile(arr, 99)),
            f'{prefix}iqr': float(np.percentile(arr, 75) - np.percentile(arr, 25)),
            f'{prefix}range': float(np.max(arr) - np.min(arr)),
            f'{prefix}skew': float(scipy_stats.skew(arr)) if len(arr) > 2 else 0,
            f'{prefix}kurtosis': float(scipy_stats.kurtosis(arr)) if len(arr) > 3 else 0,
        }
        
        # Trend features
        if len(arr) > 1:
            features[f'{prefix}trend'] = float(np.polyfit(range(len(arr)), arr, 1)[0])
            features[f'{prefix}first_half_mean'] = float(np.mean(arr[:len(arr)//2]))
            features[f'{prefix}second_half_mean'] = float(np.mean(arr[len(arr)//2:]))
        
        return features
    
    def extract_temporal_features(
        self,
        timestamp: datetime
    ) -> Dict[str, Any]:
        """Extract features from timestamp."""
        return {
            'hour': timestamp.hour,
            'day_of_week': timestamp.weekday(),
            'day_of_month': timestamp.day,
            'month': timestamp.month,
            'is_weekend': timestamp.weekday() >= 5,
            'is_night': timestamp.hour < 6 or timestamp.hour >= 22,
            'is_business_hours': 9 <= timestamp.hour <= 17 and timestamp.weekday() < 5,
            'quarter': (timestamp.month - 1) // 3 + 1,
            'hour_sin': np.sin(2 * np.pi * timestamp.hour / 24),
            'hour_cos': np.cos(2 * np.pi * timestamp.hour / 24),
            'day_sin': np.sin(2 * np.pi * timestamp.weekday() / 7),
            'day_cos': np.cos(2 * np.pi * timestamp.weekday() / 7),
        }
    
    def extract_rolling_features(
        self,
        values: List[float],
        windows: List[int] = [5, 15, 30, 60]
    ) -> Dict[str, float]:
        """Extract rolling window features."""
        features = {}
        arr = np.array(values)
        
        for window in windows:
            if len(arr) < window:
                continue
            
            rolling = arr[-window:]
            
            features[f'rolling_{window}_mean'] = float(np.mean(rolling))
            features[f'rolling_{window}_std'] = float(np.std(rolling))
            features[f'rolling_{window}_min'] = float(np.min(rolling))
            features[f'rolling_{window}_max'] = float(np.max(rolling))
            
            # Rate of change
            if len(arr) >= window + 1:
                prev_window = arr[-(window+1):-1]
                features[f'rolling_{window}_change'] = (
                    np.mean(rolling) - np.mean(prev_window)
                )
        
        return features
    
    def extract_anomaly_features(
        self,
        value: float,
        historical: List[float]
    ) -> Dict[str, float]:
        """Extract features for anomaly detection."""
        if not historical:
            return {}
        
        arr = np.array(historical)
        mean = np.mean(arr)
        std = np.std(arr) + 1e-10
        
        z_score = (value - mean) / std
        
        features = {
            'z_score': float(z_score),
            'abs_z_score': float(abs(z_score)),
            'deviation_from_mean': float(value - mean),
            'deviation_from_median': float(value - np.median(arr)),
            'percentile': float(scipy_stats.percentileofscore(arr, value)),
            'is_above_mean': value > mean,
            'is_above_2std': abs(z_score) > 2,
            'is_above_3std': abs(z_score) > 3,
        }
        
        # Distance to nearest historical value
        distances = np.abs(arr - value)
        features['min_distance'] = float(np.min(distances))
        features['avg_distance'] = float(np.mean(distances))
        
        return features
    
    def extract_correlation_features(
        self,
        series_dict: Dict[str, List[float]]
    ) -> Dict[str, float]:
        """Extract cross-correlation features between series."""
        features = {}
        series_names = list(series_dict.keys())
        
        for i, name1 in enumerate(series_names):
            for name2 in series_names[i+1:]:
                arr1 = np.array(series_dict[name1])
                arr2 = np.array(series_dict[name2])
                
                if len(arr1) == len(arr2) and len(arr1) > 1:
                    corr = np.corrcoef(arr1, arr2)[0, 1]
                    if not np.isnan(corr):
                        features[f'corr_{name1}_{name2}'] = float(corr)
        
        return features
    
    def create_feature_vector(
        self,
        current_metrics: Dict[str, float],
        historical_metrics: Dict[str, List[float]],
        timestamp: datetime
    ) -> Tuple[np.ndarray, List[str]]:
        """Create a complete feature vector."""
        all_features = {}
        
        # Temporal features
        all_features.update(self.extract_temporal_features(timestamp))
        
        # Per-metric features
        for metric_name, current_value in current_metrics.items():
            historical = historical_metrics.get(metric_name, [])
            
            # Statistical features
            all_features.update(
                self.extract_statistical_features(historical, f'{metric_name}_')
            )
            
            # Rolling features
            all_features.update(
                self.extract_rolling_features(historical)
            )
            
            # Anomaly features
            all_features.update({
                f'{metric_name}_{k}': v
                for k, v in self.extract_anomaly_features(current_value, historical).items()
            })
            
            # Current value
            all_features[f'{metric_name}_current'] = current_value
        
        # Correlation features
        all_features.update(
            self.extract_correlation_features(historical_metrics)
        )
        
        # Convert to array
        feature_names = sorted(all_features.keys())
        feature_vector = np.array([
            float(all_features[name]) if isinstance(all_features[name], (int, float, bool)) else 0
            for name in feature_names
        ])
        
        return feature_vector, feature_names
```

---

## 3. Key Takeaways

1. **Multi-Source Ingestion**: Handle data from Azure Monitor, Service Bus, Cosmos DB
2. **Batch Processing**: Efficient processing with configurable batching
3. **Data Validation**: Ensure data quality before ML processing
4. **Feature Engineering**: Create rich features for better models
5. **Feature Store**: Centralized storage for computed features

## Next Session Preview
- Session 18: Feature Engineering Best Practices
