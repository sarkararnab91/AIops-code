# Chaos Engineering Scripts

Controlled fault injection for testing AIOps capabilities.

## Setup

```bash
cd ecommerce-app/chaos

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

## Usage

### Inject Single Fault

```bash
# CPU stress on catalog-service
python scripts/chaos_experiments.py --fault cpu_stress --service catalog-service --duration 60 --intensity 0.7

# Network latency on order-service
python scripts/chaos_experiments.py --fault network_latency --service order-service --duration 30 --intensity 0.5

# Pod failure
python scripts/chaos_experiments.py --fault pod_failure --service payment-service --intensity 0.3
```

### Run Scenarios

```bash
# Cascading failure from order-service
python scripts/chaos_experiments.py --scenario cascading --service order-service

# Resource exhaustion
python scripts/chaos_experiments.py --scenario exhaustion --service catalog-service

# Full game day exercise
python scripts/chaos_experiments.py --scenario gameday --service any
```

## Fault Types

| Type | Description |
|------|-------------|
| `cpu_stress` | Increase CPU usage |
| `memory_stress` | Increase memory usage |
| `network_latency` | Add network delay |
| `network_packet_loss` | Drop network packets |
| `pod_failure` | Kill pods randomly |
| `service_unavailable` | Scale service to 0 |

## Safety Notes

1. **Always use in non-production environments first**
2. **Set appropriate duration limits**
3. **Monitor during experiments**
4. **Have rollback procedures ready**
5. **Notify team before running**

## Integration with Training

Use these scripts during:
- Session 11: Chaos Engineering basics
- Session 27: Testing anomaly detection
- Sessions 39-40: Capstone project
