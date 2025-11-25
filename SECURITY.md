# Security Policy

## Security Features

The Sanctions Screening System implements multiple layers of security to protect against common attack vectors:

### 1. XML External Entity (XXE) Prevention

All XML parsing uses secure defaults that disable:
- DTD (Document Type Definition) processing
- External entity resolution
- Network access during parsing
- Entity expansion (prevents billion laughs attack)

```python
# Secure parser configuration (lxml)
parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False
)
```

### 2. Input Validation

All user inputs are validated before processing:

| Field | Validation Rules |
|-------|------------------|
| Name | 2-200 characters, blocks `<>{}[]|\\;`$` |
| DOB | ISO 8601 format (YYYY-MM-DD) |
| Document | 1-50 alphanumeric characters |

**Unicode Support**: International names (Chinese, Arabic, Cyrillic, etc.) are supported by default. Control characters are always blocked.

### 3. Log Injection Prevention

All user input is sanitized before logging:
- Newline characters removed
- Control characters stripped
- ANSI escape sequences blocked
- Input truncated to prevent log flooding

### 4. SQL Injection Protection

While this system uses XML files rather than SQL databases, the input validation layer blocks common SQL injection patterns as defense-in-depth.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | :white_check_mark: |
| 1.x.x   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in this project:

1. **Do NOT** open a public GitHub issue
2. Email the security team at [security contact to be configured]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested fixes

### Response Timeline

- **24 hours**: Initial acknowledgment
- **72 hours**: Preliminary assessment
- **7 days**: Detailed response with remediation plan
- **30 days**: Target for fix deployment

## Security Best Practices for Deployment

### Network Security
- Deploy behind a Web Application Firewall (WAF)
- Use HTTPS for all communications
- Implement rate limiting to prevent DoS attacks

### Access Control
- Restrict API access to authorized users
- Use strong authentication mechanisms
- Log all access attempts

### Data Protection
- Encrypt sanctions data at rest
- Limit log retention to required period
- Sanitize logs before sharing

### Monitoring
- Monitor for unusual screening patterns
- Alert on validation failures spike
- Review security logs regularly

## Security Test Coverage

The test suite includes security-specific tests:

- XXE attack prevention
- Input validation edge cases
- Log injection prevention
- Control character handling
- DoS protection (billion laughs, quadratic blowup)

Run security tests with:
```bash
python -m pytest tests/ -v -k "security"
```

## Known Limitations

1. **No Rate Limiting**: The library does not implement rate limiting. Deploy behind a WAF or implement at the application layer.

2. **No Authentication**: Access control must be implemented at the deployment layer.

3. **Log File Security**: Log files may contain sanitized input data. Ensure proper file permissions and retention policies.

## CodeQL Security Scanning

This project uses GitHub CodeQL for automated security scanning. All PRs must pass security checks before merging.

Current status: ✅ 0 alerts

## Changelog

### v2.0.0 (Current)
- Added XXE prevention in XML parsing
- Implemented input validation with Unicode support
- Added log injection prevention
- Security event logging
- Configuration-based validation rules
