provider "aws" {
  region = var.region
}

# Amazon ECR Public (where the Karpenter Helm/OCI chart lives) only issues
# authorization tokens from us-east-1, so we keep a dedicated aliased provider.
provider "aws" {
  alias  = "virginia"
  region = "us-east-1"
}

# Authenticate the Helm and kubectl providers to the cluster using short-lived
# tokens from `aws eks get-token` (no long-lived kubeconfig on disk).
provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}

provider "kubectl" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  load_config_file       = false

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
  }
}
