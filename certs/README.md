# TLS Certificates Directory

This directory should contain your TLS certificates for HTTPS support.

## Required Files

Place your certificate files in this directory with the following structure:

```text
certs/
├── fullchain.pem  # Full certificate chain
└── privkey.pem    # Private key
```

## Certificate Generation

### For Production

Obtain certificates from a Certificate Authority (CA) like:

- [Let's Encrypt](https://letsencrypt.org/) (Free, automated)
- [ZeroSSL](https://zerossl.com/) (Free)
- Commercial CA (Paid)

### For Testing/Development

Generate self-signed certificates:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certs/privkey.pem \
  -out certs/fullchain.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

## Security Notes

⚠️ **Important Security Practices:**

- Never commit actual certificate files to version control
- Keep private keys secure and restrict file permissions
- Use strong encryption (RSA 2048+ bits or ECC)
- Rotate certificates before expiration
- For production, always use certificates from trusted CAs

## File Permissions

Set appropriate permissions for certificate files:

```bash
chmod 644 certs/fullchain.pem
chmod 600 certs/privkey.pem
```
