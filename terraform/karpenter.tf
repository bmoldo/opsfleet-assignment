data "aws_ecrpublic_authorization_token" "token" {
  provider = aws.virginia
}

# Creates everything Karpenter needs on the AWS side:
#   - the controller IAM role + EKS Pod Identity association (v21 default),
#   - the node IAM role, instance profile permissions, and an EKS access entry
#     so Karpenter-launched nodes are allowed to join the cluster,
#   - the SQS queue + EventBridge rules for Spot interruption / rebalance events.
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 21.0"

  cluster_name = module.eks.cluster_name

  node_iam_role_use_name_prefix   = false
  node_iam_role_name              = "${local.name}-karpenter-node"
  create_pod_identity_association = true

  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }

  tags = local.tags
}

# Karpenter controller. Pinned to a version that supports the chosen Kubernetes
# version (see var.karpenter_version). Scheduled onto the system node group and
# uses dnsPolicy: Default so it does not depend on in-cluster CoreDNS to start.
resource "helm_release" "karpenter" {
  namespace  = "kube-system"
  name       = "karpenter"
  repository = "oci://public.ecr.aws/karpenter"
  chart      = "karpenter"
  version    = var.karpenter_version

  repository_username = data.aws_ecrpublic_authorization_token.token.user_name
  repository_password = data.aws_ecrpublic_authorization_token.token.password

  # CRDs are installed by the chart; we don't need to block on controller
  # readiness because the CRs below apply server-side and reconcile once it's up.
  wait = false

  values = [
    <<-EOT
    nodeSelector:
      karpenter.sh/controller: 'true'
    dnsPolicy: Default
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
    webhook:
      enabled: false
    EOT
  ]
}

# The chart installs Karpenter's CRDs on first install; give the API server a
# moment to register them before we apply the NodePool / EC2NodeClass CRs.
resource "time_sleep" "wait_for_karpenter_crds" {
  create_duration = "30s"
  depends_on      = [helm_release.karpenter]
}

# EC2NodeClass: the AWS-level launch template Karpenter uses for nodes.
# AL2023, node IAM role from the module, and subnet/SG discovery by tag.
resource "kubectl_manifest" "karpenter_node_class" {
  yaml_body = <<-YAML
    apiVersion: karpenter.k8s.aws/v1
    kind: EC2NodeClass
    metadata:
      name: default
    spec:
      amiSelectorTerms:
        - alias: al2023@latest
      role: ${module.karpenter.node_iam_role_name}
      subnetSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${local.name}
      securityGroupSelectorTerms:
        - tags:
            karpenter.sh/discovery: ${local.name}
      tags:
        karpenter.sh/discovery: ${local.name}
  YAML

  depends_on = [time_sleep.wait_for_karpenter_crds]
}

# A single, flexible NodePool that can launch BOTH x86 (amd64) and Graviton
# (arm64) nodes, on Spot with On-Demand as fallback. Developers steer workloads
# to an architecture / capacity type with pod nodeSelectors (see examples/).
# Karpenter picks the cheapest instance that satisfies a pod's constraints, so
# Spot + Graviton are chosen by default when a pod allows them.
resource "kubectl_manifest" "karpenter_node_pool" {
  yaml_body = <<-YAML
    apiVersion: karpenter.sh/v1
    kind: NodePool
    metadata:
      name: default
    spec:
      template:
        metadata:
          labels:
            provisioned-by: karpenter
        spec:
          nodeClassRef:
            group: karpenter.k8s.aws
            kind: EC2NodeClass
            name: default
          requirements:
            - key: kubernetes.io/arch
              operator: In
              values: ["amd64", "arm64"]
            - key: kubernetes.io/os
              operator: In
              values: ["linux"]
            - key: karpenter.sh/capacity-type
              operator: In
              values: ["spot", "on-demand"]
            - key: karpenter.k8s.aws/instance-category
              operator: In
              values: ["c", "m", "r"]
            - key: karpenter.k8s.aws/instance-generation
              operator: Gt
              values: ["5"]
          expireAfter: 720h
      limits:
        cpu: "1000"
      disruption:
        consolidationPolicy: WhenEmptyOrUnderutilized
        consolidateAfter: 1m
  YAML

  depends_on = [kubectl_manifest.karpenter_node_class]
}
