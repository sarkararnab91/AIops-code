# Session 11: Failure Simulation & Chaos Engineering

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 3, Day 1 (Monday)
- **Prerequisites**: Weeks 1-2 completed
- **Deliverable**: Chaos engineering scripts and failure scenarios

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Understand chaos engineering principles
2. Create controlled failure scenarios
3. Observe system behavior under stress
4. Generate anomaly data for ML training

---

## 📚 Chaos Engineering Principles

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CHAOS ENGINEERING WORKFLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. DEFINE STEADY STATE                                                     │
│      ├── What does "normal" look like?                                      │
│      ├── Key metrics: latency, error rate, throughput                       │
│      └── Establish baselines                                                │
│                                                                              │
│   2. FORM HYPOTHESIS                                                         │
│      ├── "If X fails, the system should Y"                                  │
│      └── Example: "If payment service is slow, orders should queue"        │
│                                                                              │
│   3. INTRODUCE CHAOS                                                         │
│      ├── Network latency                                                     │
│      ├── Service failures                                                    │
│      ├── Resource exhaustion                                                 │
│      └── Data corruption                                                     │
│                                                                              │
│   4. OBSERVE & LEARN                                                         │
│      ├── Monitor metrics                                                     │
│      ├── Analyze logs                                                        │
│      └── Identify weaknesses                                                 │
│                                                                              │
│   5. FIX & IMPROVE                                                           │
│      ├── Implement fixes                                                     │
│      ├── Add resilience patterns                                            │
│      └── Update runbooks                                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Hands-On Exercise

### Step 1: Create Chaos Engineering Module

Create `ecommerce-app/chaos/chaos_engine.py`:

```python
"""
Chaos Engineering Module for AIOps Training
Simulates various failure scenarios to generate anomaly data.
"""

import os
import random
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, List, Callable
from dataclasses import dataclass
from enum import Enum
import httpx
import structlog

logger = structlog.get_logger()


class FailureType(str, Enum):
    """Types of failures to simulate."""
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    CASCADING_FAILURE = "cascading_failure"
    DATA_CORRUPTION = "data_corruption"
    MEMORY_LEAK = "memory_leak"
    CPU_SPIKE = "cpu_spike"


@dataclass
class ChaosExperiment:
    """Defines a chaos experiment."""
    name: str
    failure_type: FailureType
    target_service: str
    duration_seconds: int
    intensity: float  # 0.0 to 1.0
    parameters: dict = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class ChaosEngine:
    """
    Chaos Engineering Engine for E-Commerce Platform.
    Generates controlled failures for testing and ML training.
    """
    
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url
        self.service_ports = {
            "catalog": 8001,
            "inventory": 8002,
            "order": 8003,
            "cart": 8004,
            "payment": 8005,
            "user": 8006,
            "notification": 8007,
        }
        self.active_experiments: List[ChaosExperiment] = []
        self.metrics_history = []
        
    async def run_experiment(self, experiment: ChaosExperiment) -> dict:
        """Run a chaos experiment."""
        logger.info(
            "Starting chaos experiment",
            name=experiment.name,
            type=experiment.failure_type,
            target=experiment.target_service,
            duration=experiment.duration_seconds
        )
        
        self.active_experiments.append(experiment)
        start_time = datetime.utcnow()
        
        try:
            if experiment.failure_type == FailureType.LATENCY:
                result = await self._inject_latency(experiment)
            elif experiment.failure_type == FailureType.ERROR_RATE:
                result = await self._inject_errors(experiment)
            elif experiment.failure_type == FailureType.CASCADING_FAILURE:
                result = await self._inject_cascade(experiment)
            elif experiment.failure_type == FailureType.CPU_SPIKE:
                result = await self._inject_cpu_spike(experiment)
            elif experiment.failure_type == FailureType.MEMORY_LEAK:
                result = await self._inject_memory_leak(experiment)
            else:
                result = {"status": "unsupported", "message": f"Failure type {experiment.failure_type} not implemented"}
            
            return {
                "experiment": experiment.name,
                "status": "completed",
                "start_time": start_time.isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "result": result
            }
        finally:
            self.active_experiments.remove(experiment)
    
    async def _inject_latency(self, exp: ChaosExperiment) -> dict:
        """Inject artificial latency into service calls."""
        base_latency_ms = exp.parameters.get("base_latency_ms", 100)
        max_latency_ms = exp.parameters.get("max_latency_ms", 5000)
        
        affected_requests = 0
        total_added_latency = 0
        
        # Generate synthetic load with latency
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(exp.duration_seconds * 10):  # 10 requests per second
                # Calculate latency based on intensity
                if random.random() < exp.intensity:
                    latency = random.uniform(base_latency_ms, max_latency_ms) / 1000
                    await asyncio.sleep(latency)
                    affected_requests += 1
                    total_added_latency += latency
                
                # Make request to target service
                port = self.service_ports.get(exp.target_service, 8001)
                try:
                    await client.get(f"{self.base_url}:{port}/health")
                except Exception:
                    pass
                
                await asyncio.sleep(0.1)
        
        return {
            "affected_requests": affected_requests,
            "avg_added_latency_ms": (total_added_latency / affected_requests * 1000) if affected_requests > 0 else 0
        }
    
    async def _inject_errors(self, exp: ChaosExperiment) -> dict:
        """Inject errors into service responses."""
        error_codes = exp.parameters.get("error_codes", [500, 502, 503])
        
        injected_errors = 0
        requests_made = 0
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            end_time = datetime.utcnow() + timedelta(seconds=exp.duration_seconds)
            
            while datetime.utcnow() < end_time:
                requests_made += 1
                
                # Simulate error based on intensity
                if random.random() < exp.intensity:
                    injected_errors += 1
                    # Log the simulated error
                    logger.error(
                        "Simulated error injected",
                        service=exp.target_service,
                        error_code=random.choice(error_codes)
                    )
                
                # Make actual health check
                port = self.service_ports.get(exp.target_service, 8001)
                try:
                    await client.get(f"{self.base_url}:{port}/health")
                except Exception:
                    pass
                
                await asyncio.sleep(0.5)
        
        return {
            "requests_made": requests_made,
            "injected_errors": injected_errors,
            "error_rate": injected_errors / requests_made if requests_made > 0 else 0
        }
    
    async def _inject_cascade(self, exp: ChaosExperiment) -> dict:
        """Simulate cascading failures across services."""
        cascade_sequence = exp.parameters.get(
            "cascade_sequence",
            ["payment", "order", "cart"]
        )
        
        cascade_events = []
        delay_between_failures = exp.duration_seconds / len(cascade_sequence)
        
        for i, service in enumerate(cascade_sequence):
            # Simulate service degradation
            cascade_events.append({
                "service": service,
                "time": datetime.utcnow().isoformat(),
                "event": "degradation_started"
            })
            
            logger.warning(
                "Cascade failure progressing",
                service=service,
                step=i + 1,
                total_steps=len(cascade_sequence)
            )
            
            # Simulate load spike on affected service
            async with httpx.AsyncClient(timeout=5.0) as client:
                port = self.service_ports.get(service, 8001)
                for _ in range(20):
                    try:
                        await client.get(f"{self.base_url}:{port}/health")
                    except Exception:
                        pass
                    await asyncio.sleep(0.1)
            
            await asyncio.sleep(delay_between_failures)
            
            cascade_events.append({
                "service": service,
                "time": datetime.utcnow().isoformat(),
                "event": "recovered"
            })
        
        return {
            "cascade_sequence": cascade_sequence,
            "events": cascade_events
        }
    
    async def _inject_cpu_spike(self, exp: ChaosExperiment) -> dict:
        """Simulate CPU spike through compute-intensive operations."""
        spike_duration = exp.duration_seconds
        
        # Perform CPU-intensive calculations
        start = time.time()
        iterations = 0
        
        while time.time() - start < spike_duration:
            # Compute-intensive operation
            _ = sum(i * i for i in range(10000))
            iterations += 1
            
            if iterations % 1000 == 0:
                await asyncio.sleep(0.01)  # Yield to event loop
        
        return {
            "cpu_iterations": iterations,
            "duration": spike_duration
        }
    
    async def _inject_memory_leak(self, exp: ChaosExperiment) -> dict:
        """Simulate memory leak by gradually allocating memory."""
        max_mb = exp.parameters.get("max_mb", 100)
        
        memory_chunks = []
        chunk_size = 1024 * 1024  # 1 MB
        
        start_time = time.time()
        allocated_mb = 0
        
        while time.time() - start_time < exp.duration_seconds:
            if allocated_mb < max_mb * exp.intensity:
                # Allocate memory
                memory_chunks.append(bytearray(chunk_size))
                allocated_mb += 1
                
                logger.debug("Memory allocated", total_mb=allocated_mb)
            
            await asyncio.sleep(1)
        
        # Release memory
        memory_chunks.clear()
        
        return {
            "peak_allocated_mb": allocated_mb,
            "released": True
        }


# ============================================================
# PREDEFINED EXPERIMENTS
# ============================================================

EXPERIMENTS = {
    "payment_latency": ChaosExperiment(
        name="Payment Service Latency Spike",
        failure_type=FailureType.LATENCY,
        target_service="payment",
        duration_seconds=120,
        intensity=0.7,
        parameters={
            "base_latency_ms": 200,
            "max_latency_ms": 8000
        }
    ),
    
    "order_errors": ChaosExperiment(
        name="Order Service Error Injection",
        failure_type=FailureType.ERROR_RATE,
        target_service="order",
        duration_seconds=60,
        intensity=0.3,
        parameters={
            "error_codes": [500, 502, 503]
        }
    ),
    
    "cascade_failure": ChaosExperiment(
        name="Cascading Failure Simulation",
        failure_type=FailureType.CASCADING_FAILURE,
        target_service="payment",
        duration_seconds=180,
        intensity=0.8,
        parameters={
            "cascade_sequence": ["payment", "order", "cart", "notification"]
        }
    ),
    
    "black_friday": ChaosExperiment(
        name="Black Friday Traffic Spike",
        failure_type=FailureType.LATENCY,
        target_service="catalog",
        duration_seconds=300,
        intensity=0.9,
        parameters={
            "base_latency_ms": 50,
            "max_latency_ms": 3000
        }
    ),
}


async def run_experiment_by_name(name: str) -> dict:
    """Run a predefined experiment by name."""
    if name not in EXPERIMENTS:
        raise ValueError(f"Unknown experiment: {name}. Available: {list(EXPERIMENTS.keys())}")
    
    engine = ChaosEngine()
    return await engine.run_experiment(EXPERIMENTS[name])


# ============================================================
# CLI INTERFACE
# ============================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python chaos_engine.py <experiment_name>")
        print(f"Available experiments: {list(EXPERIMENTS.keys())}")
        sys.exit(1)
    
    experiment_name = sys.argv[1]
    
    print(f"Running chaos experiment: {experiment_name}")
    result = asyncio.run(run_experiment_by_name(experiment_name))
    print(f"Result: {result}")
```

### Step 2: Create Load Generator

Create `ecommerce-app/chaos/load_generator.py`:

```python
"""
Load Generator for E-Commerce Platform
Generates realistic traffic patterns for testing and ML training.
"""

import asyncio
import random
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass
import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class LoadProfile:
    """Defines a load testing profile."""
    name: str
    requests_per_second: float
    duration_seconds: int
    user_pattern: str  # "constant", "ramp_up", "spike", "wave"
    endpoints: List[str]


class LoadGenerator:
    """Generates synthetic load for e-commerce services."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.metrics = {
            "requests_sent": 0,
            "successful": 0,
            "failed": 0,
            "total_latency": 0.0
        }
    
    async def generate_load(self, profile: LoadProfile) -> dict:
        """Generate load based on profile."""
        logger.info(
            "Starting load generation",
            profile=profile.name,
            rps=profile.requests_per_second,
            duration=profile.duration_seconds
        )
        
        start_time = datetime.utcnow()
        end_time = start_time.timestamp() + profile.duration_seconds
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while datetime.utcnow().timestamp() < end_time:
                # Calculate current RPS based on pattern
                elapsed = datetime.utcnow().timestamp() - start_time.timestamp()
                current_rps = self._calculate_rps(
                    profile.requests_per_second,
                    profile.user_pattern,
                    elapsed,
                    profile.duration_seconds
                )
                
                # Generate requests
                tasks = []
                for _ in range(int(current_rps)):
                    endpoint = random.choice(profile.endpoints)
                    tasks.append(self._make_request(client, endpoint))
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(1)
        
        return {
            "profile": profile.name,
            "duration": profile.duration_seconds,
            "metrics": self.metrics.copy()
        }
    
    def _calculate_rps(
        self,
        base_rps: float,
        pattern: str,
        elapsed: float,
        duration: float
    ) -> float:
        """Calculate current RPS based on pattern."""
        progress = elapsed / duration
        
        if pattern == "constant":
            return base_rps
        elif pattern == "ramp_up":
            return base_rps * progress
        elif pattern == "spike":
            # Spike at 50% of duration
            if 0.4 < progress < 0.6:
                return base_rps * 5
            return base_rps
        elif pattern == "wave":
            import math
            return base_rps * (1 + 0.5 * math.sin(progress * math.pi * 4))
        
        return base_rps
    
    async def _make_request(self, client: httpx.AsyncClient, endpoint: str) -> None:
        """Make a single HTTP request."""
        url = f"{self.base_url}{endpoint}"
        start = datetime.utcnow().timestamp()
        
        try:
            response = await client.get(url)
            latency = datetime.utcnow().timestamp() - start
            
            self.metrics["requests_sent"] += 1
            self.metrics["total_latency"] += latency
            
            if response.status_code < 400:
                self.metrics["successful"] += 1
            else:
                self.metrics["failed"] += 1
                
        except Exception as e:
            self.metrics["requests_sent"] += 1
            self.metrics["failed"] += 1
            logger.debug("Request failed", url=url, error=str(e))


# Predefined load profiles
PROFILES = {
    "normal_day": LoadProfile(
        name="Normal Day Traffic",
        requests_per_second=10,
        duration_seconds=300,
        user_pattern="wave",
        endpoints=[
            "/api/v1/products",
            "/api/v1/products/featured",
            "/health"
        ]
    ),
    
    "black_friday": LoadProfile(
        name="Black Friday Rush",
        requests_per_second=100,
        duration_seconds=600,
        user_pattern="spike",
        endpoints=[
            "/api/v1/products",
            "/api/v1/products/featured",
            "/api/v1/cart",
            "/api/v1/orders"
        ]
    ),
    
    "gradual_growth": LoadProfile(
        name="Gradual Traffic Growth",
        requests_per_second=50,
        duration_seconds=300,
        user_pattern="ramp_up",
        endpoints=[
            "/api/v1/products",
            "/health"
        ]
    ),
}


async def run_load_test(profile_name: str) -> dict:
    """Run a predefined load test."""
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown profile: {profile_name}")
    
    generator = LoadGenerator()
    return await generator.generate_load(PROFILES[profile_name])


if __name__ == "__main__":
    import sys
    
    profile = sys.argv[1] if len(sys.argv) > 1 else "normal_day"
    result = asyncio.run(run_load_test(profile))
    print(f"Load test complete: {result}")
```

---

## 🧪 Verification Checklist

- [ ] Chaos engine module created
- [ ] Load generator module created
- [ ] Run at least one chaos experiment
- [ ] Observe Application Insights during experiment
- [ ] Capture baseline vs chaos metrics

---

## 📖 Key Takeaways

1. **Chaos engineering** builds confidence in system resilience
2. **Controlled failures** help discover weaknesses before production
3. **Generated data** is essential for training ML models
4. **Observability** is crucial during chaos experiments

---

## 🔜 Next Session Preview

**Session 12: Anomaly Detection with Isolation Forest**
- Train ML model on normal behavior
- Detect anomalies in real-time
- Build alerting on predictions
