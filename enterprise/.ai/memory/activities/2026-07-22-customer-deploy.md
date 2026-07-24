# 2026-07-22: Customer Deployment + Ping Auth

## What was done
- Customer pipeline deployed v0.6.1 successfully (after all fixes from 07-21)
- Renamed sample features to skip npm install of missing packages
- Changed `uuid` from `^11.1.0` to `^14.0.0` (11.1.1 not in JFrog, 14.0.0 available)
- Deployed SAML federation (Ping → Cognito) for UI auth — working
- Preparing to test Jobs API Ping authorizer (`EnableHeadless=true`)
- Created `Get-PingToken.ps1` for testing client-credentials flow
- Created `enterprise/docs/customer-repo-sync.md` for air-gapped repo maintenance

## Customer environment state
- Stack: `mf-aidp-2` deployed on v0.6.1
- WebUI accessible via VPC endpoint URL format
- SAML Ping federation for UI: working
- BDA VPC endpoints added (bedrock-data-automation + runtime)
- Permissions boundary blocks Anthropic models — must use Amazon Nova
- Jobs API (headless) not yet enabled — next step

## Next steps
- Enable `EnableHeadless=true` + Ping auth on Jobs API
- Test with real Ping JWT token using Get-PingToken.ps1
- Test completion hook when MQ broker is available
