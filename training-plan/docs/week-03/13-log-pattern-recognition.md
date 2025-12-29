# Session 13: Log Pattern Recognition with ML

## Learning Objectives
- Implement log parsing and pattern extraction
- Use TF-IDF and clustering for log grouping
- Detect anomalous log patterns automatically
- Build a log anomaly detection pipeline

## Duration: 1 hour

---

## 1. Log Pattern Extraction Pipeline

### Log Parser Implementation

```python
# File: training-plan/ecommerce-app/ml/log_parser.py
"""
Log pattern recognition using ML techniques.
"""

import re
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class LogEntry:
    """Parsed log entry."""
    timestamp: datetime
    level: str
    service: str
    message: str
    raw: str
    template: Optional[str] = None
    cluster_id: Optional[int] = None
    variables: Dict[str, str] = field(default_factory=dict)


class DrainParser:
    """
    Drain-based log parsing algorithm.
    Automatically extracts log templates from unstructured logs.
    """
    
    def __init__(
        self,
        depth: int = 4,
        similarity_threshold: float = 0.4,
        max_children: int = 100
    ):
        self.depth = depth
        self.similarity_threshold = similarity_threshold
        self.max_children = max_children
        self.root = {}
        self.templates: Dict[str, Dict] = {}
        
        # Variable patterns to mask
        self.variable_patterns = [
            (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>'),
            (r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<UUID>'),
            (r'\b[0-9a-f]{24}\b', '<MONGO_ID>'),
            (r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b', '<TIMESTAMP>'),
            (r'\b\d+\.\d+(?:ms|s|m|h)?\b', '<DURATION>'),
            (r'\b\d+\b', '<NUM>'),
            (r'"[^"]*"', '<STRING>'),
            (r"'[^']*'", '<STRING>'),
        ]
    
    def _preprocess(self, message: str) -> Tuple[List[str], Dict[str, str]]:
        """Tokenize and mask variables in log message."""
        variables = {}
        processed = message
        
        for pattern, placeholder in self.variable_patterns:
            matches = re.findall(pattern, processed)
            for i, match in enumerate(matches):
                key = f"{placeholder}_{i}"
                variables[key] = match
            processed = re.sub(pattern, placeholder, processed)
        
        tokens = processed.split()
        return tokens, variables
    
    def _get_template_id(self, tokens: List[str]) -> str:
        """Generate unique template ID."""
        template_str = ' '.join(tokens)
        return hashlib.md5(template_str.encode()).hexdigest()[:8]
    
    def _calculate_similarity(
        self,
        tokens1: List[str],
        tokens2: List[str]
    ) -> float:
        """Calculate similarity between two token sequences."""
        if len(tokens1) != len(tokens2):
            return 0.0
        
        matches = sum(1 for t1, t2 in zip(tokens1, tokens2) if t1 == t2)
        return matches / len(tokens1)
    
    def parse(self, message: str) -> Tuple[str, List[str], Dict[str, str]]:
        """
        Parse a log message and return template.
        
        Returns:
            Tuple of (template_id, template_tokens, variables)
        """
        tokens, variables = self._preprocess(message)
        
        if not tokens:
            return "empty", [], variables
        
        # Navigate tree based on message length and first tokens
        length_key = len(tokens)
        
        if length_key not in self.root:
            self.root[length_key] = {}
        
        current = self.root[length_key]
        
        # Traverse tree by first few tokens
        for i in range(min(self.depth, len(tokens))):
            token = tokens[i]
            
            if token.startswith('<') and token.endswith('>'):
                token = '*'  # Wildcard for variables
            
            if token not in current:
                if len(current) < self.max_children:
                    current[token] = {}
                else:
                    token = '*'
                    if token not in current:
                        current[token] = {}
            
            current = current[token]
        
        # Find matching template
        if '_templates' not in current:
            current['_templates'] = []
        
        best_match = None
        best_similarity = 0
        
        for template_id in current['_templates']:
            template = self.templates[template_id]
            similarity = self._calculate_similarity(tokens, template['tokens'])
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = template_id
        
        if best_similarity >= self.similarity_threshold:
            # Update existing template
            template = self.templates[best_match]
            template['count'] += 1
            
            # Merge tokens (generalize where different)
            for i, (t1, t2) in enumerate(zip(tokens, template['tokens'])):
                if t1 != t2:
                    template['tokens'][i] = '<*>'
            
            return best_match, template['tokens'], variables
        else:
            # Create new template
            template_id = self._get_template_id(tokens)
            self.templates[template_id] = {
                'tokens': tokens.copy(),
                'count': 1,
                'first_seen': datetime.now()
            }
            current['_templates'].append(template_id)
            
            return template_id, tokens, variables
    
    def get_template(self, template_id: str) -> Optional[str]:
        """Get template string by ID."""
        if template_id in self.templates:
            return ' '.join(self.templates[template_id]['tokens'])
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get parsing statistics."""
        return {
            'total_templates': len(self.templates),
            'templates': [
                {
                    'id': tid,
                    'template': ' '.join(t['tokens']),
                    'count': t['count']
                }
                for tid, t in sorted(
                    self.templates.items(),
                    key=lambda x: x[1]['count'],
                    reverse=True
                )
            ]
        }


class LogAnomalyDetector:
    """
    Detects anomalous log patterns using ML.
    """
    
    def __init__(
        self,
        vectorizer: Optional[TfidfVectorizer] = None,
        anomaly_threshold: float = 0.3
    ):
        self.vectorizer = vectorizer or TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),
            stop_words='english'
        )
        self.anomaly_threshold = anomaly_threshold
        self.normal_vectors = None
        self.is_fitted = False
    
    def fit(self, normal_logs: List[str]) -> 'LogAnomalyDetector':
        """Train on normal log patterns."""
        if not normal_logs:
            raise ValueError("Need logs to train on")
        
        self.normal_vectors = self.vectorizer.fit_transform(normal_logs)
        self.is_fitted = True
        return self
    
    def predict(self, logs: List[str]) -> List[Dict[str, Any]]:
        """
        Detect anomalies in logs.
        
        Returns list of predictions with anomaly scores.
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        
        log_vectors = self.vectorizer.transform(logs)
        
        # Calculate similarity to normal patterns
        similarities = cosine_similarity(log_vectors, self.normal_vectors)
        max_similarities = similarities.max(axis=1)
        
        results = []
        for i, (log, sim) in enumerate(zip(logs, max_similarities)):
            is_anomaly = sim < self.anomaly_threshold
            results.append({
                'log': log,
                'similarity': float(sim),
                'is_anomaly': is_anomaly,
                'anomaly_score': float(1 - sim)
            })
        
        return results
    
    def detect_new_patterns(
        self,
        logs: List[str],
        min_cluster_size: int = 5
    ) -> List[Dict[str, Any]]:
        """Detect new log patterns using clustering."""
        if not logs:
            return []
        
        vectors = self.vectorizer.transform(logs)
        
        # Cluster logs
        clustering = DBSCAN(
            eps=0.5,
            min_samples=min_cluster_size,
            metric='cosine'
        )
        labels = clustering.fit_predict(vectors.toarray())
        
        # Group by cluster
        clusters = defaultdict(list)
        for i, label in enumerate(labels):
            clusters[label].append({
                'index': i,
                'log': logs[i]
            })
        
        # Identify new patterns (noise points in DBSCAN)
        new_patterns = clusters.get(-1, [])
        
        return [{
            'cluster_id': -1,
            'logs': new_patterns,
            'is_new_pattern': True,
            'count': len(new_patterns)
        }]


class LogSequenceAnalyzer:
    """
    Analyzes log sequences for pattern anomalies.
    """
    
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.normal_sequences: List[List[str]] = []
        self.sequence_vectors = None
    
    def _create_sequence_vector(
        self,
        templates: List[str]
    ) -> np.ndarray:
        """Create vector representation of template sequence."""
        # Simple frequency-based representation
        template_counts = defaultdict(int)
        for t in templates:
            template_counts[t] += 1
        
        return np.array(list(template_counts.values()))
    
    def fit(self, template_sequences: List[List[str]]) -> 'LogSequenceAnalyzer':
        """Train on normal log sequences."""
        self.normal_sequences = template_sequences
        return self
    
    def detect_sequence_anomaly(
        self,
        templates: List[str]
    ) -> Dict[str, Any]:
        """Detect if a sequence of templates is anomalous."""
        # Check for unexpected template sequences
        anomalies = []
        
        for i in range(len(templates) - 1):
            current = templates[i]
            next_template = templates[i + 1]
            
            # Check if this transition was seen in training
            transition_seen = False
            for seq in self.normal_sequences:
                for j in range(len(seq) - 1):
                    if seq[j] == current and seq[j + 1] == next_template:
                        transition_seen = True
                        break
                if transition_seen:
                    break
            
            if not transition_seen:
                anomalies.append({
                    'position': i,
                    'from': current,
                    'to': next_template,
                    'type': 'unexpected_transition'
                })
        
        return {
            'is_anomalous': len(anomalies) > 0,
            'anomaly_count': len(anomalies),
            'anomalies': anomalies
        }
```

---

## 2. Real-Time Log Analysis Pipeline

### Streaming Log Processor

```python
# File: training-plan/ecommerce-app/ml/log_stream_processor.py
"""
Real-time log stream processing for pattern recognition.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Callable, Optional
from collections import deque
from dataclasses import dataclass
import json

from azure.servicebus.aio import ServiceBusClient
from azure.monitor.query.aio import LogsQueryClient
from azure.identity.aio import DefaultAzureCredential


@dataclass
class LogWindow:
    """Sliding window of logs for analysis."""
    entries: deque
    start_time: datetime
    window_duration: timedelta
    
    def __init__(self, window_minutes: int = 5, max_entries: int = 10000):
        self.entries = deque(maxlen=max_entries)
        self.window_duration = timedelta(minutes=window_minutes)
        self.start_time = datetime.now()
    
    def add(self, entry: Dict[str, Any]) -> None:
        """Add log entry to window."""
        self.entries.append(entry)
        self._cleanup_old_entries()
    
    def _cleanup_old_entries(self) -> None:
        """Remove entries outside the window."""
        cutoff = datetime.now() - self.window_duration
        while self.entries and self.entries[0].get('timestamp', datetime.now()) < cutoff:
            self.entries.popleft()
    
    def get_entries(self) -> List[Dict[str, Any]]:
        """Get all entries in current window."""
        self._cleanup_old_entries()
        return list(self.entries)


class StreamingLogAnalyzer:
    """
    Real-time log analysis with pattern detection.
    """
    
    def __init__(
        self,
        parser,  # DrainParser instance
        detector,  # LogAnomalyDetector instance
        alert_callback: Optional[Callable] = None
    ):
        self.parser = parser
        self.detector = detector
        self.alert_callback = alert_callback
        self.windows: Dict[str, LogWindow] = {}
        self.pattern_counts: Dict[str, Dict[str, int]] = {}
        self.anomaly_buffer: deque = deque(maxlen=100)
    
    async def process_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single log entry.
        
        Returns analysis result.
        """
        service = log.get('service', 'unknown')
        message = log.get('message', '')
        
        # Initialize window for service
        if service not in self.windows:
            self.windows[service] = LogWindow()
            self.pattern_counts[service] = {}
        
        # Parse log template
        template_id, tokens, variables = self.parser.parse(message)
        
        # Update pattern counts
        if template_id not in self.pattern_counts[service]:
            self.pattern_counts[service][template_id] = 0
        self.pattern_counts[service][template_id] += 1
        
        # Add to window
        entry = {
            'timestamp': datetime.now(),
            'service': service,
            'message': message,
            'template_id': template_id,
            'template': ' '.join(tokens),
            'variables': variables
        }
        self.windows[service].add(entry)
        
        # Check for anomalies
        result = {
            'entry': entry,
            'is_anomaly': False,
            'alerts': []
        }
        
        # Detect anomalies in current window
        window_entries = self.windows[service].get_entries()
        if len(window_entries) >= 10:
            messages = [e['message'] for e in window_entries[-10:]]
            anomaly_results = self.detector.predict(messages)
            
            if anomaly_results[-1]['is_anomaly']:
                result['is_anomaly'] = True
                result['anomaly_score'] = anomaly_results[-1]['anomaly_score']
                
                alert = {
                    'type': 'log_anomaly',
                    'service': service,
                    'message': message,
                    'score': anomaly_results[-1]['anomaly_score'],
                    'timestamp': datetime.now().isoformat()
                }
                result['alerts'].append(alert)
                self.anomaly_buffer.append(alert)
                
                if self.alert_callback:
                    await self.alert_callback(alert)
        
        # Check for pattern frequency anomalies
        freq_alert = self._check_pattern_frequency(service, template_id)
        if freq_alert:
            result['alerts'].append(freq_alert)
            if self.alert_callback:
                await self.alert_callback(freq_alert)
        
        return result
    
    def _check_pattern_frequency(
        self,
        service: str,
        template_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check if pattern frequency is anomalous."""
        window = self.windows[service]
        entries = window.get_entries()
        
        if len(entries) < 100:
            return None
        
        # Count template occurrences in window
        template_count = sum(
            1 for e in entries if e['template_id'] == template_id
        )
        
        # Calculate rate
        rate = template_count / len(entries)
        
        # Historical average (simplified)
        total = self.pattern_counts[service].get(template_id, 1)
        expected_rate = total / sum(self.pattern_counts[service].values())
        
        # Alert if rate is 3x higher than expected
        if rate > expected_rate * 3 and template_count > 10:
            return {
                'type': 'pattern_spike',
                'service': service,
                'template_id': template_id,
                'template': self.parser.get_template(template_id),
                'current_rate': rate,
                'expected_rate': expected_rate,
                'count_in_window': template_count,
                'timestamp': datetime.now().isoformat()
            }
        
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current analysis statistics."""
        return {
            'services': list(self.windows.keys()),
            'pattern_stats': self.parser.get_statistics(),
            'recent_anomalies': list(self.anomaly_buffer),
            'window_sizes': {
                service: len(window.entries)
                for service, window in self.windows.items()
            }
        }


async def connect_to_log_analytics(
    workspace_id: str,
    query: str,
    analyzer: StreamingLogAnalyzer
):
    """
    Connect to Azure Log Analytics and stream logs.
    """
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)
    
    while True:
        # Query recent logs
        response = await client.query_workspace(
            workspace_id=workspace_id,
            query=query,
            timespan=timedelta(minutes=5)
        )
        
        for table in response.tables:
            for row in table.rows:
                log = {
                    'timestamp': row[0],
                    'service': row[1],
                    'message': row[2],
                    'level': row[3]
                }
                await analyzer.process_log(log)
        
        await asyncio.sleep(30)  # Poll every 30 seconds
```

---

## 3. Hands-On Exercise

### Building a Log Pattern Dashboard

```python
# File: training-plan/ecommerce-app/ml/exercises/log_pattern_exercise.py
"""
Exercise: Build a log pattern recognition system.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict

# Sample log templates for e-commerce
LOG_TEMPLATES = [
    "User {user_id} logged in from IP {ip}",
    "Order {order_id} created for user {user_id}",
    "Payment processed for order {order_id}: ${amount}",
    "Failed to process payment for order {order_id}: {error}",
    "Product {product_id} added to cart by user {user_id}",
    "Inventory low for product {product_id}: {count} remaining",
    "API request to {endpoint} completed in {duration}ms",
    "Database query took {duration}ms for {operation}",
    "Cache miss for key {cache_key}",
    "Service {service} health check: {status}",
]

ANOMALOUS_LOGS = [
    "CRITICAL: Database connection pool exhausted",
    "ERROR: Memory usage exceeded 95%",
    "ALERT: Unusual login pattern detected for user {user_id}",
    "SECURITY: Multiple failed login attempts from IP {ip}",
    "ERROR: Unhandled exception in {service}: {error}",
]


def generate_sample_logs(count: int = 1000) -> List[Dict]:
    """Generate sample logs for training."""
    logs = []
    base_time = datetime.now() - timedelta(hours=1)
    
    for i in range(count):
        # 95% normal logs, 5% anomalous
        if random.random() < 0.95:
            template = random.choice(LOG_TEMPLATES)
        else:
            template = random.choice(ANOMALOUS_LOGS)
        
        # Fill in variables
        message = template.format(
            user_id=f"user_{random.randint(1, 100)}",
            ip=f"192.168.1.{random.randint(1, 255)}",
            order_id=f"ORD-{random.randint(10000, 99999)}",
            amount=random.randint(10, 500),
            error=random.choice(["timeout", "invalid_card", "declined"]),
            product_id=f"PROD-{random.randint(100, 999)}",
            count=random.randint(0, 20),
            endpoint=random.choice(["/api/orders", "/api/products", "/api/users"]),
            duration=random.randint(5, 2000),
            operation=random.choice(["SELECT", "INSERT", "UPDATE"]),
            cache_key=f"session:{random.randint(1, 1000)}",
            service=random.choice(["catalog", "order", "payment"]),
            status=random.choice(["healthy", "degraded"])
        )
        
        logs.append({
            'timestamp': base_time + timedelta(seconds=i * 3.6),
            'service': random.choice(['catalog', 'order', 'payment', 'cart']),
            'level': random.choices(
                ['INFO', 'WARN', 'ERROR'],
                weights=[0.8, 0.15, 0.05]
            )[0],
            'message': message
        })
    
    return logs


# Exercise Instructions
EXERCISE = """
# Log Pattern Recognition Exercise

## Objective
Build a log pattern recognition system that:
1. Automatically extracts templates from logs
2. Detects anomalous log messages
3. Tracks pattern frequency over time

## Tasks

### Task 1: Template Extraction (20 minutes)
1. Initialize a DrainParser
2. Process the generated sample logs
3. Print the top 10 most common templates

### Task 2: Anomaly Detection (20 minutes)
1. Split logs into training (80%) and test (20%)
2. Train LogAnomalyDetector on training logs
3. Detect anomalies in test logs
4. Calculate precision and recall

### Task 3: Real-Time Analysis (20 minutes)
1. Create a StreamingLogAnalyzer
2. Simulate real-time log ingestion
3. Track pattern frequencies
4. Generate alerts for anomalies

## Starter Code
```python
from log_parser import DrainParser, LogAnomalyDetector
from log_stream_processor import StreamingLogAnalyzer

# Generate sample data
logs = generate_sample_logs(1000)

# Task 1: Template Extraction
parser = DrainParser()
# TODO: Process logs and extract templates

# Task 2: Anomaly Detection  
# TODO: Train and evaluate anomaly detector

# Task 3: Real-Time Analysis
# TODO: Set up streaming analyzer
```
"""

if __name__ == "__main__":
    print(EXERCISE)
    
    # Solution demonstration
    print("\n--- Running Solution ---\n")
    
    # Import (in practice, these would be separate files)
    from training_plan.ecommerce_app.ml.log_parser import (
        DrainParser,
        LogAnomalyDetector
    )
    
    # Generate logs
    logs = generate_sample_logs(1000)
    print(f"Generated {len(logs)} sample logs")
    
    # Task 1: Extract templates
    parser = DrainParser()
    for log in logs:
        parser.parse(log['message'])
    
    stats = parser.get_statistics()
    print(f"\nExtracted {stats['total_templates']} templates")
    print("\nTop 10 templates:")
    for t in stats['templates'][:10]:
        print(f"  [{t['count']:4d}] {t['template'][:60]}...")
    
    # Task 2: Anomaly detection
    messages = [log['message'] for log in logs]
    train_size = int(len(messages) * 0.8)
    train_msgs = messages[:train_size]
    test_msgs = messages[train_size:]
    
    detector = LogAnomalyDetector(anomaly_threshold=0.3)
    detector.fit(train_msgs)
    
    results = detector.predict(test_msgs)
    anomalies = [r for r in results if r['is_anomaly']]
    
    print(f"\nAnomalies detected: {len(anomalies)}/{len(test_msgs)}")
    print("\nSample anomalies:")
    for a in anomalies[:5]:
        print(f"  Score: {a['anomaly_score']:.2f} - {a['log'][:50]}...")
```

---

## 4. Key Takeaways

1. **Template Extraction**: Drain algorithm efficiently groups similar logs
2. **Anomaly Detection**: TF-IDF + cosine similarity identifies unusual logs
3. **Sequence Analysis**: Log order matters for detecting issues
4. **Real-Time Processing**: Sliding windows enable streaming analysis
5. **Pattern Frequency**: Sudden spikes in patterns indicate problems

## Next Session Preview
- Session 14: Automated Root Cause Analysis with ML
