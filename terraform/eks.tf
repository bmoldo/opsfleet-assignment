module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = local.name
  kubernetes_version = var.kubernetes_version

  # Grant the identity running Terraform cluster-admin via an EKS access entry,
  # so you can use kubectl immediately after apply (auth mode is API by default).
  enable_cluster_creator_admin_permissions = true

  # Public + private endpoint so a developer can reach the API from their laptop
  # to run the demo. Production: go private-only, or restrict the public CIDRs.
  endpoint_public_access  = true
  endpoint_private_access = true

  # EKS-managed add-ons. vpc-cni and the pod-identity-agent are installed
  # `before_compute` so networking and IAM-for-pods are ready before nodes join.
  addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
    eks-pod-identity-agent = {
      before_compute = true
    }
  }

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.intra_subnets

  # A small, on-demand Graviton node group that hosts system components and the
  # Karpenter controller itself. Karpenter cannot manage the nodes it runs on,
  # so this group bootstraps the cluster; all *workload* capacity comes from
  # Karpenter. Bottlerocket is a minimal, security-hardened container OS.
  eks_managed_node_groups = {
    system = {
      ami_type       = "BOTTLEROCKET_ARM_64"
      instance_types = ["m7g.large"]
      capacity_type  = "ON_DEMAND"

      min_size     = 2
      max_size     = 3
      desired_size = 2

      labels = {
        "karpenter.sh/controller" = "true"
      }
    }
  }

  # Tag the shared node security group so Karpenter can discover it
  # (referenced by the EC2NodeClass securityGroupSelectorTerms).
  node_security_group_tags = merge(local.tags, {
    "karpenter.sh/discovery" = local.name
  })

  tags = local.tags
}
