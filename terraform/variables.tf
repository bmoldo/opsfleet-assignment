variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name. Also used for resource naming and the Karpenter discovery tag."
  type        = string
  default     = "opsfleet-poc"
}

variable "kubernetes_version" {
  description = "EKS control-plane Kubernetes version (latest GA at time of writing)."
  type        = string
  default     = "1.36"
}

variable "karpenter_version" {
  description = "Karpenter Helm chart version. Must support the chosen Kubernetes version."
  type        = string
  default     = "1.13.0"
}

variable "vpc_cidr" {
  description = "CIDR block for the dedicated VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "demo_archs" {
  description = "Architectures for the optional demo workload (set via `make ... OS=arm|x86` or `CONCURRENT=1` for both). Empty deploys no demo workload."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for a in var.demo_archs : contains(["amd64", "arm64"], a)])
    error_message = "demo_archs may only contain \"amd64\" and \"arm64\"."
  }
}
