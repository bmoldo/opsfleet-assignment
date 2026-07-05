# Remote state so CI (GitHub Actions OIDC) and developers share one state.
# Bucket is account bootstrap (versioned, public access blocked) — created
# once by DevOps, not managed here. Workspaces map to env:/<env>/ prefixes.
terraform {
  backend "s3" {
    bucket       = "opsfleet-tfstate-070503547773"
    key          = "opsfleet-poc/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true # native S3 locking (Terraform >= 1.10)
  }
}
