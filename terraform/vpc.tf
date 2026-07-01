module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr

  azs = local.azs
  # /20 private subnets (large IP space for pods via the VPC CNI),
  # /24 public subnets for load balancers + NAT, /24 intra subnets for the
  # EKS control-plane ENIs (no route to the internet).
  private_subnets = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 4, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k + 48)]
  intra_subnets   = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k + 52)]

  enable_nat_gateway = true
  # Single NAT keeps the POC cheap. For production set this to false to get one
  # NAT gateway per AZ (removes the cross-AZ SPOF and data-transfer hop).
  single_nat_gateway   = true
  enable_dns_hostnames = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
    # Karpenter discovers which subnets to launch nodes into via this tag
    # (referenced by the EC2NodeClass subnetSelectorTerms).
    "karpenter.sh/discovery" = local.name
  }

  tags = local.tags
}
