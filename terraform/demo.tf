# Optional demo workload, driven by `make apply ENV=<env> OS=<arm|x86>`
# (or CONCURRENT=1 for both architectures at once). Deploying it makes
# Karpenter launch Spot capacity of the chosen architecture(s); running
# apply again without OS/CONCURRENT removes it.
resource "kubectl_manifest" "demo_workload" {
  for_each = toset(var.demo_archs)

  yaml_body = <<-YAML
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: demo-${each.value}
      labels:
        app: demo-${each.value}
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: demo-${each.value}
      template:
        metadata:
          labels:
            app: demo-${each.value}
        spec:
          nodeSelector:
            kubernetes.io/arch: ${each.value}
            karpenter.sh/capacity-type: spot
          containers:
            - name: app
              image: public.ecr.aws/nginx/nginx:latest
              ports:
                - containerPort: 80
              resources:
                requests:
                  cpu: 250m
                  memory: 256Mi
  YAML

  depends_on = [kubectl_manifest.karpenter_node_pool]
}
