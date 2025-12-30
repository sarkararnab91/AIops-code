# Session 14: Automated Root Cause Analysis

## Learning Objectives
- Build dependency graphs from distributed traces
- Implement graph-based root cause detection
- Use causal inference for incident analysis
- Create automated RCA pipelines

## Duration: 1 hour

---

## 1. Dependency Graph Analysis

### Service Dependency Graph

```python
# File: training-plan/ecommerce-app/ml/rca/dependency_graph.py
"""
Build and analyze service dependency graphs for root cause analysis.
"""

from typing import List, Dict, Any, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
import heapq

import networkx as nx
import numpy as np


@dataclass
class ServiceNode:
    """Represents a service in the dependency graph."""
    name: str
    health_score: float = 1.0  # 0.0 = unhealthy, 1.0 = healthy
    latency_p99: float = 0.0
    error_rate: float = 0.0
    request_count: int = 0
    alerts: List[Dict] = field(default_factory=list)


@dataclass
class ServiceEdge:
    """Represents a dependency between services."""
    source: str
    target: str
    call_count: int = 0
    avg_latency: float = 0.0
    error_rate: float = 0.0
    weight: float = 1.0


class DependencyGraph:
    """
    Builds and analyzes service dependency graphs.
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, ServiceNode] = {}
        self.edges: Dict[Tuple[str, str], ServiceEdge] = {}
    
    def add_service(self, service: ServiceNode) -> None:
        """Add a service node to the graph."""
        self.nodes[service.name] = service
        self.graph.add_node(
            service.name,
            health_score=service.health_score,
            latency=service.latency_p99,
            error_rate=service.error_rate
        )
    
    def add_dependency(self, edge: ServiceEdge) -> None:
        """Add a dependency edge between services."""
        key = (edge.source, edge.target)
        self.edges[key] = edge
        self.graph.add_edge(
            edge.source,
            edge.target,
            weight=edge.weight,
            call_count=edge.call_count,
            avg_latency=edge.avg_latency,
            error_rate=edge.error_rate
        )
    
    def build_from_traces(self, traces: List[Dict[str, Any]]) -> None:
        """
        Build dependency graph from distributed traces.
        
        Each trace should have:
        - trace_id: Unique trace identifier
        - spans: List of spans with service, parent_span_id, duration, status
        """
        call_counts = defaultdict(int)
        latencies = defaultdict(list)
        errors = defaultdict(int)
        service_metrics = defaultdict(lambda: {
            'latencies': [],
            'errors': 0,
            'requests': 0
        })
        
        for trace in traces:
            spans = trace.get('spans', [])
            span_map = {s['span_id']: s for s in spans}
            
            for span in spans:
                service = span['service']
                service_metrics[service]['latencies'].append(span['duration'])
                service_metrics[service]['requests'] += 1
                
                if span.get('status') == 'error':
                    service_metrics[service]['errors'] += 1
                
                # Build edges from parent-child relationships
                parent_id = span.get('parent_span_id')
                if parent_id and parent_id in span_map:
                    parent_service = span_map[parent_id]['service']
                    if parent_service != service:
                        key = (parent_service, service)
                        call_counts[key] += 1
                        latencies[key].append(span['duration'])
                        if span.get('status') == 'error':
                            errors[key] += 1
        
        # Create service nodes
        for service, metrics in service_metrics.items():
            lats = metrics['latencies']
            node = ServiceNode(
                name=service,
                latency_p99=np.percentile(lats, 99) if lats else 0,
                error_rate=metrics['errors'] / max(metrics['requests'], 1),
                request_count=metrics['requests'],
                health_score=1.0 - min(metrics['errors'] / max(metrics['requests'], 1), 1.0)
            )
            self.add_service(node)
        
        # Create edges
        for (source, target), count in call_counts.items():
            edge = ServiceEdge(
                source=source,
                target=target,
                call_count=count,
                avg_latency=np.mean(latencies[(source, target)]),
                error_rate=errors[(source, target)] / count,
                weight=count
            )
            self.add_dependency(edge)
    
    def get_upstream_services(self, service: str) -> List[str]:
        """Get all services that call this service."""
        return list(self.graph.predecessors(service))
    
    def get_downstream_services(self, service: str) -> List[str]:
        """Get all services that this service calls."""
        return list(self.graph.successors(service))
    
    def calculate_impact_score(self, service: str) -> float:
        """
        Calculate the impact score of a service.
        Higher score = more critical service.
        """
        if service not in self.graph:
            return 0.0
        
        # PageRank-based importance
        pagerank = nx.pagerank(self.graph)
        
        # Betweenness centrality
        betweenness = nx.betweenness_centrality(self.graph)
        
        # Combined score
        score = (pagerank.get(service, 0) * 0.5 + 
                 betweenness.get(service, 0) * 0.5)
        
        return score
    
    def find_critical_path(
        self,
        source: str,
        target: str
    ) -> List[str]:
        """Find the critical path between two services."""
        try:
            return nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return []
    
    def get_affected_services(
        self,
        failed_service: str,
        max_depth: int = 3
    ) -> Dict[str, int]:
        """
        Get all services affected by a failure.
        
        Returns dict of service -> depth from failed service.
        """
        affected = {}
        visited = set()
        queue = [(failed_service, 0)]
        
        while queue:
            service, depth = queue.pop(0)
            
            if service in visited or depth > max_depth:
                continue
            
            visited.add(service)
            affected[service] = depth
            
            # Add upstream services (they depend on this one)
            for upstream in self.get_upstream_services(service):
                if upstream not in visited:
                    queue.append((upstream, depth + 1))
        
        return affected


class RootCauseAnalyzer:
    """
    Automated root cause analysis using dependency graphs.
    """
    
    def __init__(self, graph: DependencyGraph):
        self.graph = graph
        self.analysis_history: List[Dict] = []
    
    def analyze_incident(
        self,
        symptom_services: List[str],
        time_window: timedelta = timedelta(minutes=15)
    ) -> Dict[str, Any]:
        """
        Analyze an incident and identify root cause.
        
        Args:
            symptom_services: Services showing symptoms
            time_window: Time window to analyze
            
        Returns:
            Analysis result with ranked root causes
        """
        candidates = self._find_root_cause_candidates(symptom_services)
        ranked_causes = self._rank_candidates(candidates, symptom_services)
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'symptom_services': symptom_services,
            'root_cause_candidates': ranked_causes,
            'recommended_actions': self._generate_recommendations(ranked_causes),
            'affected_services': self._calculate_blast_radius(ranked_causes)
        }
        
        self.analysis_history.append(result)
        return result
    
    def _find_root_cause_candidates(
        self,
        symptom_services: List[str]
    ) -> Set[str]:
        """Find candidate root cause services."""
        candidates = set()
        
        for service in symptom_services:
            # Add the service itself
            candidates.add(service)
            
            # Add all downstream dependencies
            for downstream in self.graph.get_downstream_services(service):
                candidates.add(downstream)
                
                # Go deeper
                for deeper in self.graph.get_downstream_services(downstream):
                    candidates.add(deeper)
        
        return candidates
    
    def _rank_candidates(
        self,
        candidates: Set[str],
        symptom_services: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Rank root cause candidates by likelihood.
        """
        ranked = []
        
        for candidate in candidates:
            node = self.graph.nodes.get(candidate)
            if not node:
                continue
            
            # Calculate score based on multiple factors
            score = 0.0
            reasons = []
            
            # Factor 1: Error rate (0-40 points)
            if node.error_rate > 0:
                error_score = min(node.error_rate * 40, 40)
                score += error_score
                reasons.append(f"High error rate: {node.error_rate:.1%}")
            
            # Factor 2: Latency degradation (0-30 points)
            if node.latency_p99 > 1000:  # > 1 second
                latency_score = min((node.latency_p99 - 1000) / 100, 30)
                score += latency_score
                reasons.append(f"High latency: {node.latency_p99:.0f}ms p99")
            
            # Factor 3: Impact on symptom services (0-20 points)
            impact_count = 0
            for symptom in symptom_services:
                if candidate in self._get_all_downstream(symptom):
                    impact_count += 1
            
            impact_score = (impact_count / len(symptom_services)) * 20
            score += impact_score
            if impact_count > 0:
                reasons.append(f"Affects {impact_count} symptom services")
            
            # Factor 4: Graph centrality (0-10 points)
            centrality = self.graph.calculate_impact_score(candidate)
            centrality_score = centrality * 10
            score += centrality_score
            
            ranked.append({
                'service': candidate,
                'score': score,
                'confidence': min(score / 100, 1.0),
                'reasons': reasons,
                'health_score': node.health_score,
                'error_rate': node.error_rate,
                'latency_p99': node.latency_p99
            })
        
        # Sort by score descending
        ranked.sort(key=lambda x: x['score'], reverse=True)
        return ranked
    
    def _get_all_downstream(self, service: str) -> Set[str]:
        """Get all downstream services recursively."""
        result = set()
        queue = [service]
        
        while queue:
            current = queue.pop(0)
            for downstream in self.graph.get_downstream_services(current):
                if downstream not in result:
                    result.add(downstream)
                    queue.append(downstream)
        
        return result
    
    def _generate_recommendations(
        self,
        ranked_causes: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Generate remediation recommendations."""
        recommendations = []
        
        if not ranked_causes:
            return recommendations
        
        top_cause = ranked_causes[0]
        
        # High error rate
        if top_cause['error_rate'] > 0.1:
            recommendations.append({
                'priority': 'high',
                'action': f"Investigate errors in {top_cause['service']}",
                'details': [
                    "Check application logs for exceptions",
                    "Verify external dependency availability",
                    "Check for recent deployments"
                ]
            })
        
        # High latency
        if top_cause['latency_p99'] > 2000:
            recommendations.append({
                'priority': 'high',
                'action': f"Address latency in {top_cause['service']}",
                'details': [
                    "Check database query performance",
                    "Verify resource utilization (CPU/Memory)",
                    "Look for connection pool exhaustion"
                ]
            })
        
        # Multiple affected services
        if len(ranked_causes) > 3:
            recommendations.append({
                'priority': 'medium',
                'action': "Consider infrastructure-level issues",
                'details': [
                    "Check network connectivity",
                    "Verify Kubernetes cluster health",
                    "Check for resource constraints"
                ]
            })
        
        return recommendations
    
    def _calculate_blast_radius(
        self,
        ranked_causes: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate the blast radius of the incident."""
        if not ranked_causes:
            return {'total_affected': 0, 'services': []}
        
        top_cause = ranked_causes[0]['service']
        affected = self.graph.get_affected_services(top_cause)
        
        return {
            'total_affected': len(affected),
            'services': [
                {'name': svc, 'distance': dist}
                for svc, dist in sorted(affected.items(), key=lambda x: x[1])
            ]
        }
```

---

## 2. Correlation-Based RCA

### Metric Correlation Analysis

```python
# File: training-plan/ecommerce-app/ml/rca/correlation_analyzer.py
"""
Correlation-based root cause analysis using time-series metrics.
"""

import numpy as np
from scipy import stats
from scipy.signal import correlate
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class MetricSeries:
    """Time series metric data."""
    name: str
    service: str
    values: List[float]
    timestamps: List[datetime]
    metric_type: str  # 'latency', 'error_rate', 'cpu', 'memory', etc.


class CorrelationAnalyzer:
    """
    Analyzes correlations between metrics to find root causes.
    """
    
    def __init__(self, lag_range: int = 10):
        self.lag_range = lag_range  # Max lag to consider in correlation
    
    def cross_correlate(
        self,
        series1: np.ndarray,
        series2: np.ndarray,
        max_lag: int = None
    ) -> Tuple[float, int]:
        """
        Calculate cross-correlation between two series.
        
        Returns:
            (correlation_coefficient, optimal_lag)
        """
        max_lag = max_lag or self.lag_range
        
        # Normalize series
        s1 = (series1 - np.mean(series1)) / (np.std(series1) + 1e-10)
        s2 = (series2 - np.mean(series2)) / (np.std(series2) + 1e-10)
        
        best_corr = 0
        best_lag = 0
        
        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                corr = np.corrcoef(s1[:lag], s2[-lag:])[0, 1]
            elif lag > 0:
                corr = np.corrcoef(s1[lag:], s2[:-lag])[0, 1]
            else:
                corr = np.corrcoef(s1, s2)[0, 1]
            
            if not np.isnan(corr) and abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag
        
        return best_corr, best_lag
    
    def find_causal_relationships(
        self,
        metrics: List[MetricSeries],
        incident_metric: MetricSeries,
        correlation_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find metrics that might have caused the incident.
        
        A metric is considered a potential cause if:
        1. It has high correlation with incident metric
        2. It leads (precedes) the incident metric
        """
        incident_values = np.array(incident_metric.values)
        relationships = []
        
        for metric in metrics:
            if metric.name == incident_metric.name and metric.service == incident_metric.service:
                continue
            
            values = np.array(metric.values)
            if len(values) != len(incident_values):
                continue
            
            corr, lag = self.cross_correlate(values, incident_values)
            
            if abs(corr) >= correlation_threshold:
                # Negative lag means this metric leads the incident metric
                is_potential_cause = lag < 0
                
                relationships.append({
                    'metric': metric.name,
                    'service': metric.service,
                    'correlation': float(corr),
                    'lag': lag,
                    'lag_seconds': lag * 60,  # Assuming 1-minute intervals
                    'is_potential_cause': is_potential_cause,
                    'relationship': 'leads' if lag < 0 else ('lags' if lag > 0 else 'simultaneous')
                })
        
        # Sort by causality likelihood
        relationships.sort(
            key=lambda x: (x['is_potential_cause'], abs(x['correlation'])),
            reverse=True
        )
        
        return relationships
    
    def granger_causality_test(
        self,
        cause_series: np.ndarray,
        effect_series: np.ndarray,
        max_lag: int = 5
    ) -> Dict[str, Any]:
        """
        Perform Granger causality test.
        
        Tests if 'cause_series' Granger-causes 'effect_series'.
        """
        from scipy.stats import f as f_dist
        
        n = len(effect_series)
        
        # Restricted model: effect only depends on its own past
        restricted_residuals = []
        for t in range(max_lag, n):
            y = effect_series[t]
            x = effect_series[t-max_lag:t]
            pred = np.mean(x)  # Simple prediction
            restricted_residuals.append(y - pred)
        
        # Unrestricted model: effect depends on both its past and cause's past
        unrestricted_residuals = []
        for t in range(max_lag, n):
            y = effect_series[t]
            x_effect = effect_series[t-max_lag:t]
            x_cause = cause_series[t-max_lag:t]
            pred = 0.5 * np.mean(x_effect) + 0.5 * np.mean(x_cause)
            unrestricted_residuals.append(y - pred)
        
        # Calculate F-statistic
        rss_r = np.sum(np.array(restricted_residuals) ** 2)
        rss_u = np.sum(np.array(unrestricted_residuals) ** 2)
        
        df1 = max_lag
        df2 = n - 2 * max_lag - 1
        
        if rss_u == 0:
            f_stat = 0
            p_value = 1
        else:
            f_stat = ((rss_r - rss_u) / df1) / (rss_u / df2)
            p_value = 1 - f_dist.cdf(f_stat, df1, df2)
        
        return {
            'f_statistic': float(f_stat),
            'p_value': float(p_value),
            'is_significant': p_value < 0.05,
            'granger_causes': p_value < 0.05
        }


class TimeSeriesRCA:
    """
    Root cause analysis using time series analysis.
    """
    
    def __init__(self):
        self.correlation_analyzer = CorrelationAnalyzer()
    
    def detect_anomaly_propagation(
        self,
        metrics: Dict[str, MetricSeries],
        anomaly_times: Dict[str, datetime]
    ) -> List[Dict[str, Any]]:
        """
        Detect how anomalies propagate through services.
        
        Args:
            metrics: Dict of service_name -> MetricSeries
            anomaly_times: Dict of service_name -> first anomaly time
            
        Returns:
            Propagation chain from root cause to symptoms
        """
        if not anomaly_times:
            return []
        
        # Sort by anomaly time
        sorted_anomalies = sorted(
            anomaly_times.items(),
            key=lambda x: x[1]
        )
        
        # The first anomaly is likely the root cause
        chain = []
        for i, (service, time) in enumerate(sorted_anomalies):
            chain.append({
                'service': service,
                'anomaly_time': time.isoformat(),
                'order': i + 1,
                'is_potential_root_cause': i == 0,
                'delay_from_first': (time - sorted_anomalies[0][1]).total_seconds()
            })
        
        return chain
    
    def analyze_incident(
        self,
        all_metrics: List[MetricSeries],
        incident_start: datetime,
        incident_service: str
    ) -> Dict[str, Any]:
        """
        Comprehensive incident analysis using time series.
        """
        # Find the incident metric
        incident_metric = None
        for m in all_metrics:
            if m.service == incident_service and m.metric_type == 'error_rate':
                incident_metric = m
                break
        
        if not incident_metric:
            return {'error': 'Incident metric not found'}
        
        # Find correlated metrics
        relationships = self.correlation_analyzer.find_causal_relationships(
            all_metrics,
            incident_metric,
            correlation_threshold=0.6
        )
        
        # Identify potential root causes
        potential_causes = [r for r in relationships if r['is_potential_cause']]
        
        # Generate timeline
        timeline = self._build_incident_timeline(all_metrics, incident_start)
        
        return {
            'incident_service': incident_service,
            'incident_start': incident_start.isoformat(),
            'potential_root_causes': potential_causes[:5],
            'correlated_metrics': relationships[:10],
            'timeline': timeline
        }
    
    def _build_incident_timeline(
        self,
        metrics: List[MetricSeries],
        incident_start: datetime
    ) -> List[Dict[str, Any]]:
        """Build a timeline of events leading to the incident."""
        events = []
        
        for metric in metrics:
            values = np.array(metric.values)
            
            # Find significant changes
            mean = np.mean(values[:len(values)//2])  # Baseline from first half
            std = np.std(values[:len(values)//2])
            
            for i, (val, ts) in enumerate(zip(metric.values, metric.timestamps)):
                if abs(val - mean) > 3 * std:  # 3-sigma deviation
                    events.append({
                        'timestamp': ts.isoformat(),
                        'service': metric.service,
                        'metric': metric.name,
                        'value': val,
                        'deviation': (val - mean) / (std + 1e-10),
                        'type': 'anomaly'
                    })
        
        # Sort by timestamp
        events.sort(key=lambda x: x['timestamp'])
        
        return events
```

---

## 3. Hands-On Exercise

### Build an Automated RCA System

```python
# File: training-plan/ecommerce-app/ml/exercises/rca_exercise.py
"""
Exercise: Build an automated root cause analysis system.
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict

def generate_incident_scenario() -> Dict:
    """
    Generate a simulated incident scenario.
    
    Scenario: Database slowdown causes cascade of failures.
    """
    # Base time
    base_time = datetime.now() - timedelta(hours=1)
    
    # Services in dependency order
    services = ['database', 'order-service', 'cart-service', 'api-gateway']
    
    # Generate traces showing the cascade
    traces = []
    for i in range(100):
        trace_time = base_time + timedelta(minutes=i * 0.6)
        
        # Database slows down at minute 30
        db_latency = 50 if i < 50 else 50 + (i - 50) * 20
        
        spans = [
            {
                'span_id': f'{i}_1',
                'service': 'api-gateway',
                'duration': 100 + db_latency,
                'status': 'error' if db_latency > 500 else 'ok',
                'parent_span_id': None
            },
            {
                'span_id': f'{i}_2',
                'service': 'order-service',
                'duration': 50 + db_latency,
                'status': 'error' if db_latency > 400 else 'ok',
                'parent_span_id': f'{i}_1'
            },
            {
                'span_id': f'{i}_3',
                'service': 'database',
                'duration': db_latency,
                'status': 'error' if db_latency > 600 else 'ok',
                'parent_span_id': f'{i}_2'
            }
        ]
        
        traces.append({
            'trace_id': f'trace_{i}',
            'timestamp': trace_time,
            'spans': spans
        })
    
    # Generate metrics
    metrics = []
    for service in services:
        latencies = []
        error_rates = []
        timestamps = []
        
        for i in range(100):
            ts = base_time + timedelta(minutes=i * 0.6)
            timestamps.append(ts)
            
            if service == 'database':
                lat = 50 if i < 50 else 50 + (i - 50) * 20
            elif service == 'order-service':
                lat = 70 if i < 52 else 70 + (i - 52) * 18
            else:
                lat = 100 if i < 54 else 100 + (i - 54) * 15
            
            latencies.append(lat + random.gauss(0, 10))
            error_rates.append(0.01 if lat < 300 else min((lat - 300) / 1000, 0.5))
        
        metrics.append({
            'service': service,
            'metric': 'latency_p99',
            'values': latencies,
            'timestamps': timestamps
        })
        metrics.append({
            'service': service,
            'metric': 'error_rate',
            'values': error_rates,
            'timestamps': timestamps
        })
    
    return {
        'traces': traces,
        'metrics': metrics,
        'incident_start': base_time + timedelta(minutes=30),
        'symptom_services': ['api-gateway', 'order-service'],
        'actual_root_cause': 'database'
    }


EXERCISE = """
# Automated Root Cause Analysis Exercise

## Objective
Build an automated RCA system that can:
1. Construct a service dependency graph from traces
2. Identify the root cause of an incident
3. Calculate the blast radius
4. Generate remediation recommendations

## Tasks

### Task 1: Build Dependency Graph (15 minutes)
1. Parse the trace data to extract service dependencies
2. Calculate edge weights based on call frequency
3. Visualize the dependency graph

### Task 2: Implement RCA Algorithm (25 minutes)
1. Given symptom services, find candidate root causes
2. Score candidates based on:
   - Error rates
   - Latency degradation
   - Graph position (downstream of symptoms)
3. Rank and return top candidates

### Task 3: Validate with Correlation (15 minutes)
1. Use time series correlation to validate findings
2. Check if the identified cause leads the symptoms
3. Calculate confidence score

### Task 4: Generate Report (5 minutes)
1. Create an incident summary
2. List affected services
3. Provide remediation steps

## Expected Output
Your RCA system should identify "database" as the root cause with high confidence.
"""

if __name__ == "__main__":
    print(EXERCISE)
    
    # Generate scenario
    scenario = generate_incident_scenario()
    print(f"\n--- Incident Scenario Generated ---")
    print(f"Traces: {len(scenario['traces'])}")
    print(f"Symptom services: {scenario['symptom_services']}")
    print(f"Actual root cause: {scenario['actual_root_cause']}")
```

---

## 4. Key Takeaways

1. **Dependency Graphs**: Essential for understanding service relationships
2. **Graph Centrality**: PageRank and betweenness identify critical services
3. **Time Correlation**: Leading metrics often indicate root causes
4. **Blast Radius**: Understanding impact scope helps prioritization
5. **Automated RCA**: Reduces MTTR by quickly identifying root causes

## Next Session Preview
- Session 15: Capacity Planning and Forecasting with Prophet
