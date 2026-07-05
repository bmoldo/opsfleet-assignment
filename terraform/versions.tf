terraform {
  required_version = ">= 1.10" # backend use_lockfile needs 1.10+

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.16, < 3.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.0"
    }
  }
}
