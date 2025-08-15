# GenAI-IDP Development Commands

## UI Development (React)
```bash
# Navigate to UI directory
cd /home/ec2-user/genaiic-idp-accelerator/src/ui

# Start development server (if not running)
npm start

# Check code quality
npm run lint

# Fix linting issues automatically
npm run lint -- --fix

# Run tests
npm test -- --watchAll=false

# Build for production
npm run build
```

## Backend Development (Python)
```bash
# Navigate to project root
cd /home/ec2-user/genaiic-idp-accelerator

# Run Python linting
make lint

# Run unit tests
make test -C lib/idp_common_pkg

# Build SAM application
sam build

# Deploy changes (requires AWS permissions)
sam deploy
```

## Git Workflow
```bash
# Check current status
git status

# Add changes
git add .

# Commit changes
git commit -m "feat: description of your changes"

# Push to your branch
git push origin feature/ui-improvements

# Switch branches
git checkout develop
git checkout feature/ui-improvements
```

## Useful Checks
```bash
# Check what's running on port 3000
netstat -tlnp | grep :3000

# View development server logs
cd /home/ec2-user/genaiic-idp-accelerator/src/ui
tail -f server.log

# Check AWS CLI configuration
aws sts get-caller-identity
```
