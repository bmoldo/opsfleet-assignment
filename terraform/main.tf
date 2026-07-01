data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  name = var.cluster_name
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)

  tags = {
    Project   = "opsfleet-eks-karpenter"
    ManagedBy = "terraform"
    Env       = terraform.workspace
  }
}
