# EKS + Karpenter on Graviton & Spot — Terraform POC

Terraform that stands up a **production-shaped proof of concept**: a fresh, dedicated
VPC, the latest **Amazon EKS** cluster, and **Karpenter** configured to launch
**both x86 (amd64) and Graviton (arm64)** nodes on **Spot and On-Demand**
capacity for the best price/performance.

A developer then runs a pod on x86 *or* Graviton by setting a single
`nodeSelector` — or with one command: `make apply ENV=dev OS=arm`. No infra
changes required. See [Run a workload](#run-a-workload-on-x86-or-graviton-the-demo).

---

## What gets created

```
┌─────────────────────────────────────── VPC (3 AZs) ────────────────────────────────────────┐
│                                                                                             │
│   Public subnets  ──►  NAT gateway + (future) load balancers                                │
│                                                                                             │
│   Private subnets ──►  EKS managed node group "system" (2× Graviton On-Demand, Bottlerocket)│
│                          └─ runs CoreDNS, kube-proxy, VPC CNI, Pod Identity agent, Karpenter │
│                        Karpenter-provisioned nodes (amd64 + arm64, Spot-first)  ◄── on demand │
│                                                                                             │
│   Intra subnets   ──►  EKS control-plane ENIs (no internet route)                           │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Layer      | What                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------- |
| Networking | `terraform-aws-modules/vpc` — 3 AZs, public/private/intra subnets, NAT, EKS + Karpenter tags       |
| Cluster    | `terraform-aws-modules/eks` v21 — EKS (API auth mode), managed add-ons, public+private endpoint    |
| Bootstrap  | One small **Graviton** managed node group for system pods + the Karpenter controller               |
| Autoscaler | **Karpenter** (Pod Identity, SQS interruption queue) + one flexible `NodePool` and an `EC2NodeClass`|

The bootstrap node group exists to solve a chicken-and-egg problem: Karpenter
cannot provision the node it runs on, so a minimal always-on group hosts the
controller and cluster-critical pods. Every *workload* node is launched by
Karpenter, just-in-time, and consolidated away when idle.

---

## Repository layout

```
terraform/
├── Makefile                    # make plan|apply|destroy ENV=<dev|prod> [OS=arm|x86] [CONCURRENT=1]
├── versions.tf providers.tf main.tf
├── vpc.tf  eks.tf  karpenter.tf
├── demo.tf                     # optional demo workload, driven by OS=arm|x86
├── variables.tf  outputs.tf
├── environments/
│   ├── dev.tfvars              # region / cluster name / CIDR for dev
│   └── prod.tfvars             # ... for prod
└── examples/
    ├── amd64-deployment.yaml   # runs on x86 Spot
    └── arm64-deployment.yaml   # runs on Graviton Spot
```

---

## Prerequisites

- **Terraform** ≥ 1.5
- **AWS CLI** v2, authenticated to an account allowed to create VPC/EKS/IAM
  (`aws sts get-caller-identity` should succeed)
- **kubectl** ≥ 1.30
- **GNU Make** — for the `make` workflow below (optional; raw Terraform works too)

The identity you run Terraform with becomes cluster-admin automatically
(`enable_cluster_creator_admin_permissions = true`).

**One-time account bootstrap (Spot).** Launching Spot instances requires the
account-level `AWSServiceRoleForEC2Spot` service-linked role. In an account that
has never used Spot it doesn't exist yet, and Karpenter's Spot launches fail
until it does. `make apply` creates it automatically if missing; if you use raw
Terraform instead, run this once per account:

```bash
aws iam create-service-linked-role --aws-service-name spot.amazonaws.com
```

This lives in the bootstrap step (not Terraform) because it's a
create-once-per-account resource — owning it in per-environment state would
break the second environment deployed into the same account.

---

## Environments

Each environment is a `tfvars` file under `environments/` plus its own **Terraform
workspace**, so state is isolated per environment. Add one by dropping in
`environments/<name>.tfvars`.

| ENV    | Cluster name    | Region      | VPC CIDR       |
| ------ | --------------- | ----------- | -------------- |
| `dev`  | `opsfleet-dev`  | `us-east-1` | `10.10.0.0/16` |
| `prod` | `opsfleet-prod` | `us-east-1` | `10.20.0.0/16` |

---

## Usage

```bash
cd terraform

make plan       ENV=dev     # review the execution plan
make apply      ENV=dev     # create the cluster (~15–20 min)
make kubeconfig ENV=dev     # point kubectl at the cluster
```

Once the cluster is up, a developer picks an architecture the same way:

```bash
make plan  ENV=dev OS=arm         # preview: adds a demo Deployment pinned to Graviton Spot
make apply ENV=dev OS=arm         # Karpenter launches an arm64 Spot node for it
make apply ENV=dev OS=x86         # switch the demo workload to x86 (amd64)
make apply ENV=dev CONCURRENT=1   # run BOTH architectures at the same time
make apply ENV=dev                # omit OS/CONCURRENT to remove the demo workload
```

`plan` / `apply` / `destroy` **require you to be authenticated to the AWS CLI** —
the Makefile checks with `aws sts get-caller-identity` and stops early with a
clear message if you're not.

Available targets: `init`, `plan`, `apply`, `destroy`, `kubeconfig`, `output`,
`fmt`, `validate`. Run `make help` for the list.

<details>
<summary>Prefer raw Terraform? Same thing underneath.</summary>

```bash
terraform init
terraform workspace select dev || terraform workspace new dev
terraform apply -var-file=environments/dev.tfvars
```
</details>

---

## Verify the cluster

```bash
kubectl get nodes -L kubernetes.io/arch,karpenter.sh/capacity-type
# 2 system nodes, ARCH=arm64, no capacity-type label (managed group, not Karpenter).

kubectl get pods -n kube-system | grep karpenter   # controller Running
```

---

## Run a workload on x86 or Graviton (the demo)

This is the whole point: **the same cluster serves both architectures, and the
developer chooses per-workload.** Architecture is selected with
`nodeSelector: kubernetes.io/arch`; capacity type with
`nodeSelector: karpenter.sh/capacity-type`.

Two equivalent ways to run the demo:

1. **`make` (no kubectl needed):** `make apply ENV=dev OS=arm` or `OS=x86`, or
   `CONCURRENT=1` for both architectures side by side — see [Usage](#usage). It
   applies the same Deployment shape as the manifests below.
2. **`kubectl` with the example manifests** — what the rest of this section walks
   through.

> **Spot pinning vs. fallback:** the demo workloads pin
> `karpenter.sh/capacity-type: spot` so the scale-up is guaranteed and visibly
> Spot. The trade-off: if Spot capacity were unavailable, those pods would stay
> `Pending` rather than fall back. Production workloads should **omit** the
> capacity-type selector — the NodePool allows both, and Karpenter then picks
> Spot first and falls back to On-Demand automatically.

**Graviton + Spot:**

```bash
kubectl apply -f examples/arm64-deployment.yaml
kubectl get nodeclaims -w        # watch Karpenter create a node; Ctrl-C once Ready
kubectl get nodes -L kubernetes.io/arch,karpenter.sh/capacity-type,node.kubernetes.io/instance-type,topology.kubernetes.io/zone
```

Expected — a brand-new node appears in seconds:

```
NAME                        ARCH    CAPACITY-TYPE   INSTANCE-TYPE   ZONE
ip-10-x-x-x.ec2.internal    arm64   spot            c7g.large       us-east-1a   ◄── Graviton, Spot
ip-10-x-y-y...(system)      arm64                   m7g.large       us-east-1b
```

**x86 + Spot:**

```bash
kubectl apply -f examples/amd64-deployment.yaml
kubectl get nodes -L kubernetes.io/arch,karpenter.sh/capacity-type,node.kubernetes.io/instance-type
# A second new node appears with ARCH=amd64, CAPACITY-TYPE=spot (e.g. c6i.large).
```

Confirm placement:

```bash
kubectl get pods -o wide -l app=hello-graviton
kubectl get pods -o wide -l app=hello-x86
```

> **Why a new node is guaranteed:** the system nodes are **arm64 On-Demand**, so
> they satisfy *neither* selector combination in the examples (x86 pods fail the
> arch check; arm64 pods fail the `spot` check). Karpenter therefore launches
> fresh Spot capacity of the requested architecture — exactly what we want to show.

---

## ⚠️ The multi-arch image gotcha

A container image is architecture-specific. Schedule an **amd64-only image onto a
Graviton (arm64) node** and the pod crashes with `exec format error`. The `nginx`
image in the examples is a **multi-arch manifest**, so it runs on both. For your
own apps, build multi-arch once and it runs anywhere:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/app:tag --push .
```

---

## How the price/performance win works

- **Graviton (arm64)** is typically **~20% cheaper** than comparable x86 for
  **~40% better price/performance** on many workloads.
- **Spot** is up to **~90% cheaper** than On-Demand.
- The `NodePool` allows the `c`/`m`/`r` families across generations ≥ 6 and both
  architectures, giving Karpenter a **wide, diverse pool** — lowering cost and the
  chance of Spot shortfalls.
- Karpenter **consolidates**: when pods are removed it bin-packs survivors and
  terminates empty nodes, and handles Spot interruptions via the SQS queue.

---

## Cleanup

**Order matters.** Delete the workloads first so Karpenter deprovisions the EC2
instances it created (those instances are *not* in Terraform state, and leftover
ENIs can block VPC deletion):

```bash
kubectl delete -f examples/           # Karpenter scales its nodes back to zero
make apply ENV=dev                    # no OS/CONCURRENT ⇒ removes the make-managed demo workload
sleep 60                              # give it a moment to terminate instances
make destroy ENV=dev
```

---

## Production hardening (intentionally out of scope for this POC)

- **State:** the Makefile uses **workspaces over local state** for simple per-env
  isolation. Production should use a **remote backend** (S3 + native state locking)
  with per-environment state.
- **API endpoint:** make it private-only, or restrict the public CIDRs.
- **NAT:** set `single_nat_gateway = false` for one NAT per AZ (HA).
- **Guardrails:** `PodDisruptionBudgets`, `LimitRange`/`ResourceQuota`, a policy
  engine (Kyverno/Gatekeeper), control-plane logging + GuardDuty.
- **Multi-tenancy:** split the single `NodePool` into several (per team/arch) with
  `limits` and `weight`.

---

## Version matrix

| Component                     | Version        | Notes                                             |
| ----------------------------- | -------------- | ------------------------------------------------- |
| Kubernetes (EKS)              | `1.36`         | Latest GA; override via `kubernetes_version`      |
| Karpenter                     | `1.13.0`       | Supports K8s 1.36 (v1 stable `NodePool` API)      |
| `terraform-aws-modules/eks`   | `~> 21.0`      | Karpenter submodule defaults to EKS Pod Identity  |
| `terraform-aws-modules/vpc`   | `~> 5.0`       |                                                   |
| Node OS (system group)        | Bottlerocket   | Minimal, security-hardened container host         |
| Node OS (Karpenter workloads) | AL2023         | `amiSelectorTerms: alias al2023@latest`           |
