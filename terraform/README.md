# EKS + Karpenter on Graviton & Spot — Terraform POC

Terraform that stands up a **production-shaped proof of concept**: a fresh, dedicated
VPC, the latest **Amazon EKS** cluster, and **Karpenter** configured to launch
**both x86 (amd64) and Graviton (arm64)** nodes on **Spot** (with On-Demand
fallback) for the best price/performance.

A developer then runs a pod on x86 *or* Graviton by setting a single
`nodeSelector` — no infra changes required. See [Run a workload](#4-run-a-workload-on-x86-or-graviton-the-demo).

---

## What gets created

```
┌─────────────────────────────────────── VPC (10.0.0.0/16, 3 AZs) ───────────────────────────────────────┐
│                                                                                                         │
│   Public subnets  ──►  NAT gateway + (future) load balancers                                            │
│                                                                                                         │
│   Private subnets ──►  EKS managed node group "system" (2× Graviton On-Demand, Bottlerocket)            │
│                          └─ runs CoreDNS, kube-proxy, VPC CNI, EKS Pod Identity agent, Karpenter        │
│                        Karpenter-provisioned nodes (amd64 + arm64, Spot-first)  ◄── created on demand   │
│                                                                                                         │
│   Intra subnets   ──►  EKS control-plane ENIs (no internet route)                                       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Layer      | What                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------- |
| Networking | `terraform-aws-modules/vpc` — 3 AZs, public/private/intra subnets, NAT, EKS + Karpenter tags       |
| Cluster    | `terraform-aws-modules/eks` v21 — EKS (API auth mode), managed add-ons, public+private endpoint    |
| Bootstrap  | One small **Graviton** managed node group for system pods + the Karpenter controller               |
| Autoscaler | **Karpenter** (Pod Identity, SQS interruption queue) + one flexible `NodePool` and an `EC2NodeClass`|

**The bootstrap node group exists to solve a chicken-and-egg problem:** Karpenter
cannot provision the node it runs on, so a minimal always-on group hosts the
controller and cluster-critical pods. Every *workload* node is launched by
Karpenter, just-in-time, and consolidated away when idle.

---

## Repository layout

```
terraform/
├── versions.tf        # Terraform + provider version constraints
├── providers.tf       # aws (+ us-east-1 alias for ECR Public), helm, kubectl auth
├── main.tf            # AZ lookup, locals, common tags
├── vpc.tf             # dedicated VPC
├── eks.tf             # EKS cluster, add-ons, bootstrap node group
├── karpenter.tf       # Karpenter IAM/SQS + Helm + NodePool/EC2NodeClass
├── variables.tf       # region, cluster_name, versions, CIDR
├── outputs.tf         # cluster info + kubeconfig command
└── examples/
    ├── amd64-deployment.yaml   # runs on x86 Spot
    └── arm64-deployment.yaml   # runs on Graviton Spot
```

---

## Prerequisites

- **Terraform** ≥ 1.5
- **AWS CLI** v2, authenticated to an account with permissions to create VPC/EKS/IAM
  (`aws sts get-caller-identity` should work)
- **kubectl** ≥ 1.30
- The identity you run Terraform with becomes cluster-admin automatically
  (`enable_cluster_creator_admin_permissions = true`).

---

## Usage

### 1. Deploy

```bash
cd terraform
terraform init
terraform apply           # review the plan, then confirm
```

Takes **~15–20 minutes** (most of it is the EKS control plane). Override any
default inline, e.g. a different region or a pinned Kubernetes version:

```bash
terraform apply -var="region=eu-west-1" -var="kubernetes_version=1.35"
```

### 2. Configure kubectl

```bash
$(terraform output -raw configure_kubectl)
# equivalent to:
# aws eks update-kubeconfig --region us-east-1 --name opsfleet-poc
```

### 3. Verify the cluster

```bash
kubectl get nodes -L kubernetes.io/arch,karpenter.sh/capacity-type
# You should see 2 system nodes, ARCH=arm64, (no capacity-type label — they are
# the managed node group, not Karpenter-owned).

kubectl get pods -n kube-system | grep karpenter   # controller should be Running
```

### 4. Run a workload on x86 *or* Graviton (the demo)

This is the whole point: **the same cluster serves both architectures, and the
developer chooses per-workload.** Architecture is selected with
`nodeSelector: kubernetes.io/arch`; capacity type with
`nodeSelector: karpenter.sh/capacity-type`.

**Graviton + Spot:**

```bash
kubectl apply -f examples/arm64-deployment.yaml

# Watch Karpenter create a NodeClaim and then a node:
kubectl get nodeclaims -w        # Ctrl-C once Ready

kubectl get nodes -L kubernetes.io/arch,karpenter.sh/capacity-type,node.kubernetes.io/instance-type,topology.kubernetes.io/zone
```

Expected — a brand-new node appears, provisioned in seconds:

```
NAME                        ARCH    CAPACITY-TYPE   INSTANCE-TYPE   ZONE
ip-10-0-x-x.ec2.internal    arm64   spot            c7g.large       us-east-1a   ◄── Graviton, Spot
ip-10-0-y-y...(system)      arm64                   m7g.large       us-east-1b
```

**x86 + Spot:**

```bash
kubectl apply -f examples/amd64-deployment.yaml
kubectl get nodes -L kubernetes.io/arch,karpenter.sh/capacity-type,node.kubernetes.io/instance-type
# A second new node appears with ARCH=amd64, CAPACITY-TYPE=spot (e.g. c6i.large).
```

Confirm the pods actually landed where intended:

```bash
kubectl get pods -o wide -l app=hello-graviton
kubectl get pods -o wide -l app=hello-x86
```

> **Why a new node is guaranteed:** the system nodes are **arm64 On-Demand**, so
> they can satisfy *neither* selector combination in the examples (the x86 pods
> fail the arch check; the arm64 pods fail the `spot` check). Karpenter therefore
> has to launch fresh Spot capacity of the requested architecture — which is
> exactly what we want to demonstrate.

---

## ⚠️ The multi-arch image gotcha

A container image is architecture-specific. If you schedule an **amd64-only image
onto a Graviton (arm64) node**, the pod crashes with `exec format error`. The
`nginx` image used in the examples is a **multi-arch manifest**, so it runs on
both. For your own apps, build a multi-arch image once and it runs anywhere:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/app:tag --push .
```

Then the *same* image works whether Karpenter places the pod on x86 or Graviton.

---

## How the price/performance win works

- **Graviton (arm64)** instances are typically **~20% cheaper** than comparable
  x86 for **~40% better price/performance** on many workloads.
- **Spot** instances are up to **~90% cheaper** than On-Demand.
- The `NodePool` allows the `c`, `m`, and `r` families across generations ≥ 6 and
  both architectures, giving Karpenter a **wide, diverse pool** to pick from —
  which both lowers cost and reduces the chance of Spot capacity shortfalls.
- Karpenter **consolidates**: when pods are removed it bin-packs survivors and
  terminates now-empty nodes (`consolidationPolicy: WhenEmptyOrUnderutilized`),
  and it handles Spot interruptions gracefully via the SQS queue.

---

## Cleanup

**Order matters.** Delete the workloads first so Karpenter deprovisions the EC2
instances it created (those instances are *not* in Terraform state, and leftover
ENIs can block VPC deletion):

```bash
kubectl delete -f examples/           # Karpenter scales its nodes back to zero
sleep 60                              # give it a moment to terminate instances
terraform destroy
```

---

## Production hardening (intentionally out of scope for this POC)

This POC optimizes for "clone and `apply`". For a real environment you would:

- **State:** use a remote backend (S3 + native state locking / DynamoDB) instead
  of local state. A commented template is below.
- **API endpoint:** make it private-only, or set `endpoint_public_access_cidrs`
  to your office/VPN ranges.
- **NAT:** set `single_nat_gateway = false` for one NAT per AZ (HA).
- **Guardrails:** add `PodDisruptionBudgets`, resource `LimitRanges`/`ResourceQuotas`,
  and a policy engine (Kyverno/Gatekeeper); enable control-plane logging + GuardDuty.
- **Multi-tenancy:** split the single `NodePool` into several (e.g. per team/arch)
  with `limits` and `weight` to cap spend and steer scheduling.

```hcl
# versions.tf — example remote backend
# terraform {
#   backend "s3" {
#     bucket       = "my-tf-state-bucket"
#     key          = "opsfleet/eks-karpenter/terraform.tfstate"
#     region       = "us-east-1"
#     use_lockfile = true   # S3-native state locking (Terraform ≥ 1.10)
#   }
# }
```

---

## Version matrix

| Component                     | Version        | Notes                                             |
| ----------------------------- | -------------- | ------------------------------------------------- |
| Kubernetes (EKS)              | `1.36`         | Latest GA; override via `-var kubernetes_version` |
| Karpenter                     | `1.13.0`       | Supports K8s 1.36 (v1 stable `NodePool` API)      |
| `terraform-aws-modules/eks`   | `~> 21.0`      | Karpenter submodule defaults to EKS Pod Identity  |
| `terraform-aws-modules/vpc`   | `~> 5.0`       |                                                   |
| Node OS (system group)        | Bottlerocket   | Minimal, security-hardened container host         |
| Node OS (Karpenter workloads) | AL2023         | `amiSelectorTerms: alias al2023@latest`           |
