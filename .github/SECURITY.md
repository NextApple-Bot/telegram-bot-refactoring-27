mkdir -p .github
cat > .github/SECURITY.md << 'EOF'
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x     | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities by email to **admin@nextapple.com** or via GitHub Issues with label `security`. 

We will respond within 48 hours and release a patch as soon as possible.
EOF
