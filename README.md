# Opsfleet — Technical & Architecture Assignment

This repository contains both deliverables for the assignment.

## 📁 [`terraform/`](./terraform) — EKS + Karpenter on Graviton & Spot

Terraform that deploys a dedicated VPC and the latest Amazon EKS cluster, with
**Karpenter** provisioning **both x86 (amd64) and Graviton (arm64)** nodes on
**Spot and On-Demand** capacity. Includes a runnable demo showing a developer
scheduling a pod on either architecture with a one-line `nodeSelector` — or a
single command: `make apply ENV=dev OS=arm|x86`.

→ **[terraform/README.md](./terraform/README.md)**

## 📁 [`architecture/`](./architecture) — "Innovate Inc." cloud design

An architecture design document for a startup deploying a Flask + React +
PostgreSQL app on AWS, built for security, scalability (a few hundred → millions
of users), and CI/CD. Covers account structure, networking, the EKS compute
platform, and the database — with a high-level architecture diagram.

→ **[architecture/README.md](./architecture/README.md)**
