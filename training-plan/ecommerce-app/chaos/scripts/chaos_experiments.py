"""
Chaos Engineering Scripts for AIOps Training
Inject controlled failures to test observability and ML detection
"""

import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

import httpx
from kubernetes import client, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaultType(str, Enum):
    """Types of faults that can be injected."""
    CPU_STRESS = "cpu_stress"
    MEMORY_STRESS = "memory_stress"
    NETWORK_LATENCY = "network_latency"
    NETWORK_PACKET_LOSS = "network_packet_loss"
    POD_FAILURE = "pod_failure"
    SERVICE_UNAVAILABLE = "service_unavailable"
    DEPENDENCY_FAILURE = "dependency_failure"
    DISK_STRESS = "disk_stress"


class ChaosExperiment:
    """Base class for chaos experiments."""
    
    def __init__(self, namespace: str = "ecommerce"):
        self.namespace = namespace
        self._load_k8s_config()
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
    
    def _load_k8s_config(self):
        """Load Kubernetes configuration."""
        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config()
            except config.ConfigException:
                logger.warning("No K8s config found, running in simulation mode")
    
    async def inject_fault(
        self,
        fault_type: FaultType,
        target_service: str,
        duration_seconds: int = 60,
        intensity: float = 0.5
    ) -> dict:
        """Inject a fault into the target service."""
        
        logger.info(f"Injecting {fault_type} into {target_service} for {duration_seconds}s")
        
        fault_handlers = {
            FaultType.CPU_STRESS: self._inject_cpu_stress,
            FaultType.MEMORY_STRESS: self._inject_memory_stress,
            FaultType.NETWORK_LATENCY: self._inject_network_latency,
            FaultType.POD_FAILURE: self._inject_pod_failure,
            FaultType.SERVICE_UNAVAILABLE: self._inject_service_unavailable,
        }
        
        handler = fault_handlers.get(fault_type)
        if not handler:
            return {"error": f"Unknown fault type: {fault_type}"}
        
        result = await handler(target_service, duration_seconds, intensity)
        
        return {
            "fault_type": fault_type.value,
            "target": target_service,
            "duration_seconds": duration_seconds,
            "intensity": intensity,
            "started_at": datetime.utcnow().isoformat(),
            "result": result
        }
    
    async def _inject_cpu_stress(
        self,
        service: str,
        duration: int,
        intensity: float
    ) -> dict:
        """Inject CPU stress using stress-ng."""
        
        # In production, this would exec into the pod
        # For demo, we simulate the effect
        
        cpu_workers = max(1, int(intensity * 4))
        
        command = f"stress-ng --cpu {cpu_workers} --timeout {duration}s"
        
        return {
            "simulated": True,
            "command": command,
            "expected_cpu_increase": f"{intensity * 100:.0f}%"
        }
    
    async def _inject_memory_stress(
        self,
        service: str,
        duration: int,
        intensity: float
    ) -> dict:
        """Inject memory stress."""
        
        memory_mb = int(intensity * 512)
        
        command = f"stress-ng --vm 1 --vm-bytes {memory_mb}M --timeout {duration}s"
        
        return {
            "simulated": True,
            "command": command,
            "expected_memory_increase": f"{memory_mb}MB"
        }
    
    async def _inject_network_latency(
        self,
        service: str,
        duration: int,
        intensity: float
    ) -> dict:
        """Inject network latency using tc."""
        
        latency_ms = int(intensity * 1000)
        
        command = f"tc qdisc add dev eth0 root netem delay {latency_ms}ms"
        cleanup = "tc qdisc del dev eth0 root"
        
        return {
            "simulated": True,
            "command": command,
            "cleanup_command": cleanup,
            "expected_latency_increase": f"{latency_ms}ms"
        }
    
    async def _inject_pod_failure(
        self,
        service: str,
        duration: int,
        intensity: float
    ) -> dict:
        """Kill random pods of a service."""
        
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app={service}"
            )
            
            if not pods.items:
                return {"error": f"No pods found for {service}"}
            
            # Select pods to kill based on intensity
            num_to_kill = max(1, int(len(pods.items) * intensity))
            pods_to_kill = random.sample(pods.items, min(num_to_kill, len(pods.items)))
            
            killed = []
            for pod in pods_to_kill:
                try:
                    self.core_v1.delete_namespaced_pod(
                        name=pod.metadata.name,
                        namespace=self.namespace
                    )
                    killed.append(pod.metadata.name)
                except Exception as e:
                    logger.error(f"Failed to kill pod {pod.metadata.name}: {e}")
            
            return {
                "pods_killed": killed,
                "total_pods": len(pods.items)
            }
            
        except Exception as e:
            return {
                "simulated": True,
                "message": f"Would kill {int(intensity * 3)} pods of {service}",
                "error_in_real_mode": str(e)
            }
    
    async def _inject_service_unavailable(
        self,
        service: str,
        duration: int,
        intensity: float
    ) -> dict:
        """Make service unavailable by scaling to 0."""
        
        try:
            # Get current replicas
            deployment = self.apps_v1.read_namespaced_deployment(
                name=service,
                namespace=self.namespace
            )
            original_replicas = deployment.spec.replicas
            
            # Scale to 0
            deployment.spec.replicas = 0
            self.apps_v1.patch_namespaced_deployment(
                name=service,
                namespace=self.namespace,
                body=deployment
            )
            
            # Schedule restoration
            asyncio.create_task(self._restore_replicas(service, original_replicas, duration))
            
            return {
                "action": "scaled_to_zero",
                "original_replicas": original_replicas,
                "will_restore_in": f"{duration}s"
            }
            
        except Exception as e:
            return {
                "simulated": True,
                "message": f"Would scale {service} to 0 for {duration}s",
                "error_in_real_mode": str(e)
            }
    
    async def _restore_replicas(self, service: str, replicas: int, delay: int):
        """Restore original replica count after delay."""
        await asyncio.sleep(delay)
        
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=service,
                namespace=self.namespace
            )
            deployment.spec.replicas = replicas
            self.apps_v1.patch_namespaced_deployment(
                name=service,
                namespace=self.namespace,
                body=deployment
            )
            logger.info(f"Restored {service} to {replicas} replicas")
        except Exception as e:
            logger.error(f"Failed to restore {service}: {e}")


class ChaosScenario:
    """Pre-defined chaos scenarios for testing."""
    
    def __init__(self, experiment: ChaosExperiment):
        self.experiment = experiment
    
    async def run_cascading_failure(self, root_service: str):
        """Simulate cascading failure from a root service."""
        
        logger.info(f"Starting cascading failure scenario from {root_service}")
        
        # Dependencies map
        dependencies = {
            "api-gateway": ["catalog-service", "order-service"],
            "order-service": ["inventory-service", "payment-service"],
            "catalog-service": ["inventory-service"]
        }
        
        affected = [root_service]
        results = []
        
        # Inject fault into root service
        result = await self.experiment.inject_fault(
            FaultType.SERVICE_UNAVAILABLE,
            root_service,
            duration_seconds=120
        )
        results.append(result)
        
        # Find dependent services
        for service, deps in dependencies.items():
            if root_service in deps:
                # Dependent service will experience errors
                await asyncio.sleep(5)  # Propagation delay
                
                result = await self.experiment.inject_fault(
                    FaultType.NETWORK_LATENCY,
                    service,
                    duration_seconds=60,
                    intensity=0.8
                )
                results.append(result)
                affected.append(service)
        
        return {
            "scenario": "cascading_failure",
            "root_service": root_service,
            "affected_services": affected,
            "results": results
        }
    
    async def run_resource_exhaustion(self, service: str):
        """Simulate gradual resource exhaustion."""
        
        logger.info(f"Starting resource exhaustion scenario on {service}")
        
        results = []
        
        # Gradually increase load
        for intensity in [0.3, 0.5, 0.7, 0.9]:
            result = await self.experiment.inject_fault(
                FaultType.CPU_STRESS,
                service,
                duration_seconds=30,
                intensity=intensity
            )
            results.append({
                "phase": intensity,
                "result": result
            })
            
            await asyncio.sleep(30)
        
        return {
            "scenario": "resource_exhaustion",
            "target_service": service,
            "phases": results
        }
    
    async def run_network_partition(self, service_a: str, service_b: str):
        """Simulate network partition between two services."""
        
        logger.info(f"Starting network partition between {service_a} and {service_b}")
        
        results = []
        
        # Block traffic in both directions
        for service in [service_a, service_b]:
            result = await self.experiment.inject_fault(
                FaultType.NETWORK_LATENCY,
                service,
                duration_seconds=60,
                intensity=1.0  # Complete timeout
            )
            results.append(result)
        
        return {
            "scenario": "network_partition",
            "services": [service_a, service_b],
            "duration_seconds": 60,
            "results": results
        }


class ChaosOrchestrator:
    """Orchestrate multiple chaos experiments."""
    
    def __init__(self, namespace: str = "ecommerce"):
        self.experiment = ChaosExperiment(namespace)
        self.scenarios = ChaosScenario(self.experiment)
        self.running_experiments = []
    
    async def run_random_fault(
        self,
        services: list[str],
        duration: int = 60
    ) -> dict:
        """Run a random fault on a random service."""
        
        service = random.choice(services)
        fault_type = random.choice(list(FaultType))
        intensity = random.uniform(0.3, 0.8)
        
        return await self.experiment.inject_fault(
            fault_type,
            service,
            duration_seconds=duration,
            intensity=intensity
        )
    
    async def run_scheduled_chaos(
        self,
        schedule: list[dict],
        interval_seconds: int = 60
    ):
        """Run chaos experiments on a schedule."""
        
        for item in schedule:
            fault_type = FaultType(item["fault_type"])
            service = item["service"]
            duration = item.get("duration", 60)
            intensity = item.get("intensity", 0.5)
            
            await self.experiment.inject_fault(
                fault_type,
                service,
                duration_seconds=duration,
                intensity=intensity
            )
            
            await asyncio.sleep(interval_seconds)
    
    async def run_game_day(self) -> dict:
        """Run a full game day chaos exercise."""
        
        logger.info("Starting Game Day chaos exercise")
        
        services = [
            "catalog-service", "order-service", "cart-service",
            "user-service", "payment-service", "inventory-service"
        ]
        
        results = []
        
        # Phase 1: Individual service faults
        logger.info("Phase 1: Individual service faults")
        for service in random.sample(services, 3):
            result = await self.run_random_fault([service], duration=30)
            results.append({"phase": 1, "result": result})
            await asyncio.sleep(45)
        
        # Phase 2: Cascading failure
        logger.info("Phase 2: Cascading failure")
        result = await self.scenarios.run_cascading_failure("order-service")
        results.append({"phase": 2, "result": result})
        await asyncio.sleep(120)
        
        # Phase 3: Resource exhaustion
        logger.info("Phase 3: Resource exhaustion")
        result = await self.scenarios.run_resource_exhaustion("catalog-service")
        results.append({"phase": 3, "result": result})
        
        return {
            "type": "game_day",
            "started_at": datetime.utcnow().isoformat(),
            "phases_completed": 3,
            "results": results
        }


# CLI interface
async def main():
    """Run chaos experiments from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chaos Engineering CLI")
    parser.add_argument("--fault", type=str, choices=[f.value for f in FaultType])
    parser.add_argument("--service", type=str, required=True)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--intensity", type=float, default=0.5)
    parser.add_argument("--scenario", type=str, choices=["cascading", "exhaustion", "partition", "gameday"])
    parser.add_argument("--namespace", type=str, default="ecommerce")
    
    args = parser.parse_args()
    
    orchestrator = ChaosOrchestrator(args.namespace)
    
    if args.scenario:
        if args.scenario == "cascading":
            result = await orchestrator.scenarios.run_cascading_failure(args.service)
        elif args.scenario == "exhaustion":
            result = await orchestrator.scenarios.run_resource_exhaustion(args.service)
        elif args.scenario == "gameday":
            result = await orchestrator.run_game_day()
        else:
            result = {"error": "Unknown scenario"}
    elif args.fault:
        result = await orchestrator.experiment.inject_fault(
            FaultType(args.fault),
            args.service,
            args.duration,
            args.intensity
        )
    else:
        result = {"error": "Specify --fault or --scenario"}
    
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
