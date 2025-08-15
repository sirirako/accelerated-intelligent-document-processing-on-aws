# GenAI-IDP Project Structure

## Key Directories

### Frontend (React UI)
```
src/ui/
├── src/
│   ├── components/          # React components
│   │   ├── document-list/   # Document listing page
│   │   ├── upload-document/ # File upload functionality
│   │   ├── document-viewer/ # Document display
│   │   └── genaiidp-layout/ # Main app layout
│   ├── contexts/           # React context providers
│   ├── hooks/              # Custom React hooks
│   └── routes/             # Application routing
├── public/                 # Static assets
└── package.json           # Dependencies and scripts
```

### Backend (Lambda Functions)
```
src/lambda/
├── document-processor/     # Main document processing
├── classification/         # Document classification
├── extraction/            # Data extraction
├── assessment/            # Quality assessment
└── api/                   # GraphQL API handlers
```

### Configuration
```
config_library/            # Processing configurations
patterns/                  # Document processing patterns
lib/idp_common_pkg/       # Shared Python library
```

### Infrastructure
```
template.yaml             # SAM CloudFormation template
options/                  # Deployment options
scripts/                  # Build and deployment scripts
```

## Important Files
- `src/ui/.env` - Frontend environment variables
- `template.yaml` - Infrastructure as code
- `Makefile` - Build automation
- `ruff.toml` - Python linting configuration
