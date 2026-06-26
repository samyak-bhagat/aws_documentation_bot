# Multi-Environment Terraform Guide

## Quick Start

All environments (dev, staging, prod) share the same Terraform code. Switch between environments using `-var-file` flag.

### Development
```powershell
cd environments
terraform init
terraform plan -var-file="terraform.dev.tfvars"
terraform apply -var-file="terraform.dev.tfvars"
```

### Staging
```powershell
terraform plan -var-file="terraform.staging.tfvars"
terraform apply -var-file="terraform.staging.tfvars"
```

### Production
```powershell
terraform plan -var-file="terraform.prod.tfvars"
terraform apply -var-file="terraform.prod.tfvars"
```

## File Structure

```
environments/
├── main.tf                      # Main infrastructure code
├── variables.tf                 # Variable definitions
├── outputs.tf                   # Output definitions
├── backend.tf                   # Backend configuration guide
├── terraform.dev.tfvars         # Dev environment config (committed)
├── terraform.staging.tfvars     # Staging environment config (committed)
├── terraform.prod.tfvars        # Production environment config (committed)
├── terraform.tfvars.example     # Example template for new environments
├── terraform.tfvars             # Local override (NOT committed - create from example)
└── .gitignore                   # Ignores local state & secrets
```

## Environment Differences

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| NAT Gateway | ❌ | ✅ | ✅ |
| RDS Instance | db.t4g.micro | db.t4g.micro | db.t3.small |
| RDS Multi-AZ | ❌ | ❌ | ✅ |
| OpenSearch Nodes | 1 | 2 | 3 |
| ECS Tasks | 1 | 1 | 2 |
| ECR Force Delete | ✅ | ❌ | ❌ |

## Managing State

### Local State (Development)
No additional setup needed. State stored in `.terraform/` and `*.tfstate` files.

### Remote State (Recommended for Staging/Prod)

1. **Bootstrap** (one-time):
   ```powershell
   cd ../bootstrap
   terraform init
   terraform apply
   # Note the outputs: bucket name, account ID
   ```

2. **Configure backend files**:
   Create `backend-dev.tfbackend`, `backend-prod.tfbackend`, etc. in environments/ with:
   ```hcl
   bucket         = "aws-docs-bot-terraform-state-ACCOUNT_ID"
   key            = "dev/terraform.tfstate"  # or prod/, staging/
   region         = "us-east-1"
   dynamodb_table = "aws-docs-bot-terraform-lock"
   encrypt        = true
   ```

3. **Initialize with backend**:
   ```powershell
   terraform init -backend-config="backend-dev.tfbackend"
   ```

4. **Migrate existing local state** (if switching from local to remote):
   ```powershell
   terraform init -migrate-state -backend-config="backend-dev.tfbackend"
   ```

## Customizing Variables

To override defaults for your specific environment:

1. **Using .tfvars files** (permanent for each env):
   Edit `terraform.{env}.tfvars` and commit to Git

2. **Using command-line** (temporary overrides):
   ```powershell
   terraform apply -var-file="terraform.dev.tfvars" -var="image_tag=v1.2.3"
   ```

3. **Using environment variables**:
   ```powershell
   $env:TF_VAR_image_tag = "v1.2.3"
   terraform apply -var-file="terraform.dev.tfvars"
   ```

## Common Tasks

### View outputs for an environment
```powershell
terraform output -var-file="terraform.dev.tfvars"
terraform output -var-file="terraform.dev.tfvars" alb_dns_name
```

### Destroy an environment
```powershell
terraform destroy -var-file="terraform.dev.tfvars"
```

### Plan a change across all environments
```powershell
terraform plan -var-file="terraform.dev.tfvars" > dev.plan
terraform plan -var-file="terraform.staging.tfvars" > staging.plan
terraform plan -var-file="terraform.prod.tfvars" > prod.plan
```

### Create new environment
1. Copy and customize `terraform.prod.tfvars` → `terraform.myenv.tfvars`
2. Create `backend-myenv.tfbackend` if using remote state
3. Run: `terraform init -backend-config="backend-myenv.tfbackend"`
4. Run: `terraform apply -var-file="terraform.myenv.tfvars"`

## Best Practices

✅ **DO:**
- Commit environment `.tfvars` files (except `terraform.tfvars`)
- Use remote state for production
- Use different AWS accounts for prod/staging
- Enable MFA for AWS credentials
- Review `terraform plan` output before `apply`

❌ **DON'T:**
- Commit `terraform.tfvars` (contains local overrides/secrets)
- Manually modify AWS resources (breaks state)
- Use `terraform.tfvars` for environment configs (use specific `.tfvars` files)
- Share AWS credentials in `.tfvars` files (use AWS IAM roles)

## Troubleshooting

**Q: Wrong state file used**
```powershell
# Verify which .tfvars is being used
terraform plan -var-file="terraform.dev.tfvars" -lock=false
```

**Q: State lock error**
```powershell
# Manually unlock (dangerous - use only if terraform crashed)
terraform force-unlock <LOCK_ID> -var-file="terraform.dev.tfvars"
```

**Q: Lost tfstate file**
```powershell
# If using remote state, can recover from S3
aws s3 cp s3://aws-docs-bot-terraform-state-ACCOUNT_ID/dev/terraform.tfstate .
```

## References
- [Terraform Workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)
- [Variable Files](https://developer.hashicorp.com/terraform/language/values/variables#variable-definitions-tfvars-files)
- [Backend Configuration](https://developer.hashicorp.com/terraform/language/settings/backends/configuration)
