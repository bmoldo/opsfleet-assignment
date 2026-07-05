TF := terraform
ENV ?=
TFVARS := environments/$(ENV).tfvars

# OS=arm|x86 deploys the demo workload on that architecture; CONCURRENT=1
# deploys both architectures at once. Omit both to remove the demo workload.
OS ?=
CONCURRENT ?=
override CONCURRENT := $(filter-out 0 false no,$(CONCURRENT))
_ARCH.arm := arm64
_ARCH.arm64 := arm64
_ARCH.x86 := amd64
_ARCH.amd64 := amd64
ARCH := $(_ARCH.$(OS))
comma := ,
DEMO_ARCHS := $(if $(CONCURRENT),["amd64"$(comma)"arm64"],$(if $(ARCH),["$(ARCH)"]))
TF_VARS := -var-file=$(TFVARS)$(if $(DEMO_ARCHS), -var='demo_archs=$(DEMO_ARCHS)')

# destroy-demo removes only the demo workload (all arches, or one via OS=);
# it never touches the cluster itself.
DEMO_TARGET := kubectl_manifest.demo_workload$(if $(ARCH),["$(ARCH)"])

.DEFAULT_GOAL := help
.PHONY: help init plan apply destroy destroy-demo kubeconfig output fmt validate _guard-env _guard-os _check-auth _workspace _bootstrap

help:
	@echo "Usage: make <target> ENV=<dev|prod> [OS=arm|x86] [CONCURRENT=1]"
	@echo ""
	@echo "  init        Initialize Terraform for ENV"
	@echo "  plan        Show the execution plan for ENV"
	@echo "  apply       Create or update the ENV cluster"
	@echo "  destroy     Tear down the ENV cluster (everything)"
	@echo "  destroy-demo  Remove only the demo workload you deployed"
	@echo "                (all arches, or a single one with OS=arm|x86)"
	@echo "  kubeconfig  Point kubectl at the ENV cluster"
	@echo "  output      Show Terraform outputs for ENV"
	@echo "  fmt         Format Terraform files"
	@echo "  validate    Validate the configuration"
	@echo ""
	@echo "OS=arm|x86 (plan/apply) deploys the demo workload on Graviton or x86"
	@echo "Spot capacity via Karpenter; CONCURRENT=1 deploys both architectures"
	@echo "at once. Omit both to remove the demo workload."
	@echo ""
	@echo "Examples: make apply ENV=dev"
	@echo "          make apply ENV=dev OS=arm"
	@echo "          make apply ENV=dev CONCURRENT=1"
	@echo "          make destroy-demo ENV=dev"
	@echo "          make destroy-demo ENV=dev OS=arm"

_guard-env:
	@test -n "$(ENV)" || { echo "ENV is required (e.g. make plan ENV=dev)"; exit 1; }
	@test -f "$(TFVARS)" || { echo "$(TFVARS) not found"; exit 1; }

_guard-os:
	@test -z "$(OS)" -o -n "$(ARCH)" || { echo "Invalid OS '$(OS)' (use arm or x86)"; exit 1; }

_check-auth:
	@aws sts get-caller-identity >/dev/null 2>&1 || { echo "Not authenticated to AWS; run 'aws sso login' or configure credentials"; exit 1; }

init: _guard-env
	@$(TF) init -input=false

_workspace: init
	@$(TF) workspace select $(ENV) 2>/dev/null || $(TF) workspace new $(ENV)

# Account-level, one-time setup Karpenter depends on but Terraform can't own
# (create-once-per-account; a second env in the same account would conflict).
_bootstrap: _check-auth
	@aws iam get-role --role-name AWSServiceRoleForEC2Spot >/dev/null 2>&1 || { \
		echo "Creating EC2 Spot service-linked role (one-time per account)..."; \
		aws iam create-service-linked-role --aws-service-name spot.amazonaws.com >/dev/null; }

# The helm/kubectl providers are configured from module.eks outputs, which are
# unknown until the cluster exists — a plan/apply from empty state fails with
# "invalid provider configuration". Standard fix: target module.eks first,
# then run the full plan/apply once its outputs are in state.
_cluster-in-state = $(TF) state list -no-color module.eks 2>/dev/null | grep -q '\.aws_eks_cluster\.'

plan: _guard-env _guard-os _check-auth _workspace
	@if $(_cluster-in-state); then \
		echo "$(TF) plan $(TF_VARS)"; \
		$(TF) plan $(TF_VARS); \
	else \
		echo "Cluster not in state yet — planning the infra phase (VPC + EKS) only."; \
		echo "Kubernetes-level resources (Karpenter, demo) plan after the first apply."; \
		$(TF) plan -target=module.eks $(TF_VARS); \
	fi

apply: _guard-env _guard-os _check-auth _bootstrap _workspace
	@if ! $(_cluster-in-state); then \
		echo "First apply for this env: creating VPC + EKS before the Kubernetes add-ons (two-phase bootstrap)..."; \
		$(TF) apply -target=module.eks $(TF_VARS) || exit 1; \
	fi
	$(TF) apply $(TF_VARS)

destroy: _guard-env _check-auth _workspace
	$(TF) destroy -var-file=$(TFVARS)

destroy-demo: _guard-env _guard-os _check-auth _workspace
	$(TF) destroy -target='$(DEMO_TARGET)' -var-file=$(TFVARS)

kubeconfig: _guard-env _check-auth _workspace
	@aws eks update-kubeconfig --region $$($(TF) output -raw region) --name $$($(TF) output -raw cluster_name)

output: _guard-env _workspace
	@$(TF) output

fmt:
	@$(TF) fmt -recursive

validate:
	@$(TF) init -backend=false -input=false >/dev/null
	@$(TF) validate
