# Dynamic IT Orchestrator

An **AI-driven Kubernetes failure detection and remediation platform** built using Chaos Engineering and microservices telemetry.

This project uses the **Google Online Boutique microservices application** deployed on Kubernetes to simulate real-world failures and generate telemetry datasets for AI-based incident diagnosis.

## Project Goals

* Inject controlled failures into microservices using Chaos Mesh
* Collect telemetry data (logs, metrics, events)
* Build datasets for AI-based root cause analysis
* Develop intelligent remediation agents for Kubernetes

## System Architecture

```
Microservices Application (Online Boutique)
           │
           ▼
      Kubernetes Cluster
           │
           ▼
       Chaos Mesh
   (Failure Injection)
           │
           ▼
    Telemetry Collector
 (Logs + Metrics + Events)
           │
           ▼
     Dataset Generator
           │
           ▼
   AI Diagnosis Engine
           │
           ▼
   Automated Remediation
```

## Failure Scenarios

The following failure scenarios are injected using Chaos Mesh:

* Pod Kill
* CPU Stress
* Network Latency
* Redis Failure

These failures help generate realistic telemetry datasets for AI models.

## Dataset Structure

```
dataset/

   cpu_spike/
      timestamp/
         snapshot_0
         snapshot_1

   network_delay/
      timestamp/
         snapshot_0
         snapshot_1
```

Each snapshot contains:

* Pod metrics
* Cluster events
* Service logs
* Pod states

## Running Chaos Experiments

Run the experiment pipeline:

```
bash run_experiments.sh
```

This will:

1. Inject chaos
2. Collect telemetry snapshots
3. Store dataset for AI training

## Technologies Used

* Kubernetes
* Chaos Mesh
* Minikube
* Microservices (Online Boutique)
* Bash Telemetry Collectors
* Python (planned AI agents)

## Future Improvements

* AI root cause analysis model
* Automated remediation agents
* Real-time telemetry streaming
* Intelligent anomaly detection

## Reference Application

This project uses the **Google Cloud Online Boutique microservices demo** as the base application:

https://github.com/GoogleCloudPlatform/microservices-demo

---

Built as part of a **DevOps + AIOps research project** exploring automated failure diagnosis in cloud-native systems.
