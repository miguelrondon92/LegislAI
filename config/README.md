# Configuration Directory

This directory contains configuration templates and environment-specific settings.

## Files

### `production.env.template`
Production environment configuration template with secure defaults.

**Usage:**
1. Copy to your production environment
2. Rename to `.env` or source directly
3. Replace all placeholder values with actual credentials
4. Ensure sensitive values are stored securely (environment variables, secrets manager)

**Key Configuration Areas:**
- **Logging**: Set to `WARNING` level for production
- **Database**: PostgreSQL connection string
- **Email**: Production email service (SendGrid/SES)
- **Security**: Secure session settings
- **API Keys**: External service credentials

### `production_email_config.env`
Email service configuration examples for different providers.

## Security Notes

⚠️ **Never commit actual credentials to version control**

- Use environment variables or secrets management systems
- Rotate API keys and passwords regularly
- Use strong, unique passwords for admin accounts
- Enable HTTPS and secure cookie settings in production

## Environment Variables Priority

1. System environment variables (highest priority)
2. `.env` file in project root
3. Default values in application code (lowest priority)