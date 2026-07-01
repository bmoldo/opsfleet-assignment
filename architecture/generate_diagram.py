#!/usr/bin/env python3
"""Generate the High-Level Diagram (HLD) for Innovate Inc.'s AWS architecture.

Usage:
    pip install diagrams   # also requires the system Graphviz `dot` binary
    python generate_diagram.py
Produces `diagram.png` next to this script.
"""
import os

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, EKS, EC2
from diagrams.aws.database import Aurora
from diagrams.aws.management import Cloudwatch
from diagrams.aws.network import ELB, CloudFront, NATGateway, Route53
from diagrams.aws.security import KMS, WAF, SecretsManager, Shield
from diagrams.aws.storage import S3
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.vcs import Github

OUTFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagram")

graph_attr = {
    "fontsize": "22",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "ortho",
    "nodesep": "0.6",
    "ranksep": "1.0",
}

with Diagram(
    "Innovate Inc. — Production AWS Architecture (single workload account)",
    filename=OUTFILE,
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
):
    users = Users("End users")

    with Cluster("Edge (global) — CloudFront + WAF + Shield"):
        dns = Route53("Route 53")
        cdn = CloudFront("CloudFront")
        waf = WAF("WAF")
        shield = Shield("Shield")
        spa = S3("React SPA\n(static assets)")
        cdn - Edge(style="dotted", color="firebrick") - waf
        cdn - Edge(style="dotted", color="firebrick") - shield

    with Cluster("Prod account — dedicated VPC (3 Availability Zones)"):
        with Cluster("Public subnets"):
            alb = ELB("Application\nLoad Balancer")
            nat = NATGateway("NAT")

        with Cluster("Private app subnets — Amazon EKS"):
            eks = EKS("EKS control plane")
            sys_ng = EC2("System node group\n(managed, on-demand)")
            karp = EC2("Karpenter nodes\nGraviton + Spot\n(Flask API pods)")
            eks >> Edge(style="dashed", label="provisions") >> karp

        with Cluster("Private data subnets"):
            db_w = Aurora("Aurora PostgreSQL\nwriter (Multi-AZ)")
            db_r = Aurora("Aurora\nread replica")
            db_w >> Edge(label="sync/async\nreplication") >> db_r

    with Cluster("Platform & security services"):
        ecr = ECR("ECR\n(container images)")
        secrets = SecretsManager("Secrets\nManager")
        kms = KMS("KMS")
        cw = Cloudwatch("CloudWatch\n+ Container Insights")

    with Cluster("CI/CD (GitOps)"):
        gh = Github("GitHub\n(app + manifests)")
        ga = GithubActions("GitHub Actions\nbuild + scan\n(multi-arch)")
        argo = ArgoCD("Argo CD")

    # Request path
    users >> dns >> cdn
    cdn >> Edge(label="static") >> spa
    cdn >> Edge(label="/api  (HTTPS)") >> alb
    alb >> Edge(label="app traffic") >> karp

    # Runtime dependencies
    karp >> Edge(label="SQL / TLS") >> db_w
    karp >> Edge(style="dotted") >> secrets
    karp >> Edge(style="dotted", label="pull") >> ecr
    karp >> Edge(style="dotted") >> cw
    db_w >> Edge(style="dotted", label="encrypt at rest") >> kms
    secrets >> Edge(style="dotted") >> kms

    # Delivery path
    gh >> ga >> Edge(label="push image") >> ecr
    ga >> Edge(label="bump tag") >> argo
    argo >> Edge(label="sync / deploy") >> eks
