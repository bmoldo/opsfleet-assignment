import os

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, EC2
from diagrams.aws.database import RDS, Aurora
from diagrams.aws.network import ELB, CloudFront, Endpoint, NATGateway, Route53
from diagrams.aws.storage import S3
from diagrams.generic.storage import Storage
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.vcs import Github

OUTFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagram")

# Edge palette — one color per kind of traffic so the lines are readable:
USER_TRAFFIC = {"color": "#1f6feb", "penwidth": "2.2"}          # solid blue
DATA_PATH = {"color": "#8250df", "penwidth": "2.2"}             # solid purple
CICD = {"color": "#1a7f37", "penwidth": "2.0"}                  # solid green
SUPPORT = {"color": "#57606a", "style": "dotted", "penwidth": "1.6"}

graph_attr = {
    "fontsize": "22",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "spline",
    "nodesep": "0.9",
    "ranksep": "1.2",
}

edge_attr = {
    "fontsize": "13",
    "fontcolor": "#24292f",
}

with Diagram(
    "Innovate Inc. — Production AWS Architecture (single workload account)",
    filename=OUTFILE,
    outformat="png",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
    edge_attr=edge_attr,
):
    users = Users("End users")
    dns = Route53("Route 53\n(DNS resolution only)")
    cdn = CloudFront("CloudFront\nWAF + Shield at edge")
    spa = S3("S3 bucket (regional)\nReact SPA static assets")

    with Cluster("CI/CD (GitOps, pull-based)"):
        dev = Users("Developer")
        gh = Github("GitHub\n(app + manifests repos)")
        ga = GithubActions("GitHub Actions\nbuild, test, scan\n(multi-arch)")
        ecr = ECR("ECR\nscan-on-push,\nimmutable tags")

    # EKS control plane lives in an AWS-managed VPC (ENIs attach into the
    # private subnets) — deliberately drawn outside the workload VPC.
    with Cluster("Prod VPC — 3 Availability Zones"):
        with Cluster("Public subnets"):
            alb = ELB("ALB\nSG: CloudFront\nprefix list only")
            nat = NATGateway("NAT gateways\none per AZ (x3)")

        with Cluster("Private app subnets — EKS data plane"):
            argo = ArgoCD("Argo CD\n(in-cluster)")
            pods = EC2("Flask API pods\nKarpenter:\nGraviton + Spot")
            sys_ng = EC2("System node group\n(managed, on-demand)\nruns Karpenter")
            vpce = Endpoint("VPC endpoints\nECR, S3, Secrets\nManager, logs")

        with Cluster("Private data subnets"):
            proxy = RDS("RDS Proxy\nr/w + read-only\nendpoints")
            db_w = Aurora("Aurora writer\n(AZ-a)")
            db_r = Aurora("Aurora reader (AZ-b)\nfailover target")
            storage = Storage("Shared storage\n6 copies / 3 AZs / KMS")

    # ---- User traffic (blue) ------------------------------------------------
    users >> Edge(label="DNS", style="dashed", color="#1f6feb") >> dns
    users >> Edge(**USER_TRAFFIC) >> cdn
    cdn >> Edge(label="static assets", **USER_TRAFFIC) >> spa
    cdn >> Edge(label="/api (HTTPS)", **USER_TRAFFIC) >> alb
    alb >> Edge(label="app traffic", **USER_TRAFFIC) >> pods

    # ---- Data path (purple) -------------------------------------------------
    pods >> Edge(label="reads + writes (TLS)", **DATA_PATH) >> proxy
    proxy >> Edge(label="writes", **DATA_PATH) >> db_w
    proxy >> Edge(label="reads", **DATA_PATH) >> db_r
    # No writer→reader replication stream: both instances share the storage volume.
    db_w - Edge(**SUPPORT) - storage
    db_r - Edge(**SUPPORT) - storage

    # ---- Node provisioning / egress (dotted gray) ---------------------------
    sys_ng >> Edge(label="provisions", style="dashed", color="#d4a72c",
                   penwidth="2.0") >> pods
    pods >> Edge(label="egress", constraint="false", **SUPPORT) >> nat
    pods >> Edge(label="pull images via\nVPC endpoint", constraint="false",
                 **SUPPORT) >> vpce
    vpce >> Edge(constraint="false", **SUPPORT) >> ecr

    # ---- CI/CD (green) — CI never talks to the cluster ----------------------
    dev >> Edge(label="push", **CICD) >> gh
    gh >> Edge(label="triggers", **CICD) >> ga
    ga >> Edge(label="push multi-arch image", **CICD) >> ecr
    ga >> Edge(label="commit new tag\nto manifests", **CICD) >> gh
    argo >> Edge(label="pull desired state", **CICD) >> gh
    argo >> Edge(label="sync", **CICD) >> pods
