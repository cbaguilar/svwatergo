# AWS SPA Deployment Setup (GitHub Actions OIDC)

This repo uses `.github/workflows/deploy.yml` to deploy `frontend/svwaternet` when `main` is updated.

## 1) Create AWS OIDC provider (one-time per AWS account)

If not already created, add GitHub Actions as an IAM OIDC provider:

- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

## 2) Create deploy IAM role

1. Create an IAM role with trust policy from `deploy/aws-oidc-trust-policy.json`
2. Replace placeholders:
   - `<ACCOUNT_ID>`
   - `<GITHUB_ORG_OR_USER>`
   - `<GITHUB_REPO>`
3. Set branch to `main` (already configured in the file)

## 3) Attach least-privilege policy

1. Create an IAM policy from `deploy/aws-deploy-policy.json`
2. Replace placeholders:
   - `<S3_BUCKET_NAME>`
   - `<ACCOUNT_ID>`
   - `<DISTRIBUTION_ID>`
3. Attach policy to the deploy role

## 4) Configure GitHub repo settings

### GitHub Secret
- `AWS_ROLE_ARN` = ARN of the IAM deploy role

### GitHub Variables
- `AWS_REGION` = e.g. `us-east-1`
- `S3_BUCKET` = S3 bucket for built assets
- `CLOUDFRONT_DISTRIBUTION_ID` = CloudFront distribution ID (optional but recommended)

## 5) Deployment behavior

Workflow:
1. Build app from `frontend/svwaternet`
2. `aws s3 sync` uploads all assets except `index.html` with long cache headers
3. Uploads `index.html` with no-cache headers
4. Invalidates CloudFront for `/index.html` and `/assets/*` (if distribution ID is set)

## 6) Notes

- `main` is treated as production deploy branch.
- If CloudFront is not used, leave `CLOUDFRONT_DISTRIBUTION_ID` empty.
- For SPA routing, configure CloudFront custom error responses to return `/index.html` for 403/404.

