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

## ⚙️ [`.github/workflows/terraform.yml`](./.github/workflows/terraform.yml) — CI/CD for the Terraform

The Terraform is wired into GitHub Actions with **OIDC auth** (short-lived AWS
credentials, no stored keys) and **S3 remote state**, so the pipeline and
developers share one state:

| You do                                   | The pipeline does                                             |
| ---------------------------------------- | ------------------------------------------------------------- |
| Open a PR touching `terraform/**`        | `terraform fmt -check` + `validate`, then a **plan for dev** posted in the job log |
| Merge / push to `master`                 | **Auto-deploys dev** (`make apply ENV=dev`)                    |
| Actions → *terraform* → **Run workflow** | Same deploy, with an **OS dropdown** (`none`/`arm`/`x86`/`both`) that also launches the demo workload on the chosen architecture(s) via Karpenter |

Verified end-to-end: a manual `arm` run builds the VPC + EKS cluster from an
empty state (two-phase bootstrap) and Karpenter launches a Graviton **Spot**
node for the demo. Teardown: `make destroy-demo ENV=dev` removes just the demo
workload; `make destroy ENV=dev` removes the environment.

One-time account bootstrap (state bucket, OIDC role, `AWS_ROLE_ARN` repo
variable) is documented in
**[terraform/README.md → CI/CD](./terraform/README.md#cicd-auto-deploy-to-dev)**.
