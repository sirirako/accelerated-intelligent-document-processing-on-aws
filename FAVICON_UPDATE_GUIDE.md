# Adding Favicon Icons to Existing IDP Deployments

If you have an existing GenAI IDP stack deployment and want to add favicon icons to your web UI tabs, follow one of these methods:

## Method 1: Stack Update (Recommended)

This method updates your entire stack to the latest version, which includes favicon support:

### Steps:
1. **Log into AWS Console** and navigate to CloudFormation
2. **Find your IDP stack** (e.g., "IDP", "IDP-dev", "IDP-prod", etc.)
3. **Click "Update"** on your stack
4. **Select "Replace current template"**
5. **Enter the template URL** for your region:
   - **US East (N.Virginia)**: `https://s3.us-east-1.amazonaws.com/aws-ml-blog-us-east-1/artifacts/genai-idp/idp-main.yaml`
   - **US West (Oregon)**: `https://s3.us-west-2.amazonaws.com/aws-ml-blog-us-west-2/artifacts/genai-idp/idp-main.yaml`
6. **Review parameters** (keep existing values unless you want to change them)
7. **Complete the update**

### Result:
- Your stack will update to the latest version
- CodeBuild will automatically rebuild the web UI with favicon support
- Favicon icons will appear in browser tabs after completion (5-10 minutes)

## Method 2: Manual CodeBuild Trigger

If you prefer not to update your entire stack, you can manually trigger just the web UI rebuild:

### Using AWS CLI:
```bash
# Replace with your region and stack name
REGION="us-east-1"
STACK_NAME="IDP"

# Start the web UI build
aws codebuild start-build \
  --project-name "${STACK_NAME}-webui-build" \
  --region "$REGION"
```

### Using AWS Console:
1. **Navigate to CodeBuild** in AWS Console
2. **Find your project** (usually named `{StackName}-webui-build`)
3. **Click "Start build"**
4. **Wait for completion** (5-10 minutes)

## Method 3: Using the Helper Script

If you have AWS CLI configured, you can use this helper script:

```bash
# Download the script
curl -O https://raw.githubusercontent.com/your-repo/genaiic-idp-accelerator/main/trigger-favicon-update.sh
chmod +x trigger-favicon-update.sh

# Run for default stack (IDP in us-east-1)
./trigger-favicon-update.sh

# Run for specific stack and region
./trigger-favicon-update.sh us-west-2 IDP-prod
```

## What Gets Added

The favicon update includes:
- **Multiple icon formats**: .ico, 16x16, 32x32, 192x192, 512x512 PNG files
- **Apple touch icon**: For iOS devices
- **Browser compatibility**: Works with all modern browsers
- **Cache busting**: Ensures icons load properly

## Verification

After the update completes:
1. **Clear browser cache** (Ctrl+F5 or Cmd+Shift+R)
2. **Visit your web UI URL**
3. **Check the browser tab** - you should see the AWS/IDP icon
4. **Test on mobile** - icon should appear when bookmarked

## Troubleshooting

### Icons not appearing?
- **Clear browser cache** completely
- **Wait for CloudFront invalidation** (can take up to 15 minutes)
- **Check build logs** in CodeBuild console

### Build failed?
- **Check CodeBuild logs** for error details
- **Verify IAM permissions** for the CodeBuild service role
- **Try Method 1** (stack update) instead

### Need help?
- **Check CloudFormation Events** tab for any errors
- **Review CodeBuild build history** for failed builds
- **Contact your AWS administrator** if permissions issues occur

## Stack Names to Look For

Common IDP stack naming patterns:
- `IDP` (main stack)
- `IDP-dev` (development)
- `IDP-prod` (production)
- `IDP-test` (testing)
- `IDP-{custom-name}` (custom deployments)

The corresponding CodeBuild projects will be named:
- `IDP-webui-build`
- `IDP-dev-webui-build`
- `IDP-prod-webui-build`
- etc.
