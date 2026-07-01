terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70"
    }
    # v2 of the Helm provider (stable block-style `kubernetes {}` config).
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.16, < 3.0"
    }
    # Maintained fork of gavinbunney/kubectl. Applies CRs (NodePool/EC2NodeClass)
    # server-side at apply time, so it tolerates CRDs that are created in the
    # same apply (unlike hashicorp/kubernetes_manifest, which needs them at plan).
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9"
    }
  }
}
