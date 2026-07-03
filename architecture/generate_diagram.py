import os

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, EKS, EC2
from diagrams.aws.database import RDS, Aurora
from diagrams.aws.management import Cloudwatch
from diagrams.aws.network import ELB, CloudFront, NATGateway, Route53
from diagrams.aws.security import KMS, WAF, SecretsManager, Shield
from diagrams.aws.storage import S3
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.vcs import Github

OUTFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagram")

# Edge palette — one color per kind of traffic so the lines are readable:
USER_TRAFFIC = {"color": "#1f6feb", "penwidth": "2.2"}          # solid blue
DATA_PATH = {"color": "#8250df", "penwidth": "2.2"}             # solid purple
CICD = {"color": "#1a7f37", "penwidth": "2.0"}                  # solid green
PROVISION = {"color": "#d4a72c", "style": "dashed", "penwidth": "2.0"}
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

    with Cluster("Edge (global)"):
        dns = Route53("Route 53")
        cdn = CloudFront("CloudFront")
        waf = WAF("WAF")
        shield = Shield("Shield")
        spa = S3("React SPA\n(static assets)")
        # invisible edges pin WAF/Shield onto CloudFront's rank, right beside it
        dns >> Edge(style="invis") >> waf
        dns >> Edge(style="invis") >> shield
        cdn - Edge(constraint="false", **SUPPORT) - waf
        waf - Edge(constraint="false", **SUPPORT) - shield

    with Cluster("CI/CD (GitOps)"):
        gh = Github("GitHub\n(app + manifests)")
        ga = GithubActions("GitHub Actions\nbuild + scan\n(multi-arch)")
        argo = ArgoCD("Argo CD")

    with Cluster("Prod account — dedicated VPC (3 Availability Zones)"):
        with Cluster("Public subnets"):
            alb = ELB("Application\nLoad Balancer")
            nat = NATGateway("NAT gateway\n(egress for\nprivate subnets)")

        with Cluster("Private app subnets — Amazon EKS"):
            eks = EKS("EKS control plane")
            sys_ng = EC2("System node group\n(managed, on-demand)\nruns Karpenter")
            karp = EC2("Karpenter nodes\nGraviton + Spot\n(Flask API pods)")

        with Cluster("Private data subnets"):
            proxy = RDS("RDS Proxy\n(connection pooling)")
            db_w = Aurora("Aurora PostgreSQL\nwriter (Multi-AZ)")
            db_r = Aurora("Aurora\nread replica")

    with Cluster("Platform & security services"):
        ecr = ECR("ECR\n(container images)")
        secrets = SecretsManager("Secrets\nManager")
        kms = KMS("KMS")
        cw = Cloudwatch("CloudWatch\n+ Container Insights")

    # ---- User traffic (blue) ------------------------------------------------
    users >> Edge(**USER_TRAFFIC) >> dns >> Edge(**USER_TRAFFIC) >> cdn
    cdn >> Edge(label="static assets", **USER_TRAFFIC) >> spa
    cdn >> Edge(label="/api (HTTPS)", decorate="true", **USER_TRAFFIC) >> alb
    alb >> Edge(label="app traffic", **USER_TRAFFIC) >> karp

    # ---- Data path (purple) -------------------------------------------------
    karp >> Edge(label="SQL / TLS", **DATA_PATH) >> proxy
    proxy >> Edge(**DATA_PATH) >> db_w
    db_w >> Edge(label="replication", style="dashed", color="#8250df") >> db_r

    # ---- Node provisioning (dashed yellow) ----------------------------------
    sys_ng >> Edge(label="provisions", **PROVISION) >> karp

    # ---- Supporting services (dotted gray) ----------------------------------
    karp >> Edge(label="egress", constraint="false", **SUPPORT) >> nat
    karp >> Edge(label="secrets", **SUPPORT) >> secrets
    karp >> Edge(label="pull images", **SUPPORT) >> ecr
    karp >> Edge(label="metrics / logs", **SUPPORT) >> cw
    db_w >> Edge(label="encrypt at rest", constraint="false", **SUPPORT) >> kms
    secrets >> Edge(**SUPPORT) >> kms

    # ---- CI/CD (green) ------------------------------------------------------
    gh >> Edge(**CICD) >> ga
    ga >> Edge(label="push image", **CICD) >> ecr
    ga >> Edge(label="bump tag", **CICD) >> argo
    argo >> Edge(label="sync / deploy", **CICD) >> eks
