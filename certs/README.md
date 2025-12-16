# TLS Certificates Directory

This directory contains TLS/SSL certificates for HTTPS connections with Traefik.

## Required Files

Place your certificate files in this directory:

- `fullchain.pem` - Full certificate chain (certificate + intermediate certificates)
- `privkey.pem` - Private key file

## For Development/Testing

You can generate self-signed certificates for testing using the provided script:

```bash
./generate-self-signed-cert.sh
```

This will create self-signed certificates valid for 365 days for `localhost` and `*.localhost` domains.

⚠️ **Warning**: Self-signed certificates will show security warnings in browsers. Only use them for development/testing!

## For Production

For production deployments, you should use certificates from a trusted Certificate Authority (CA):

### Option 1: Let's Encrypt (Recommended)

Let's Encrypt provides free SSL/TLS certificates. You can obtain them using:

- **Certbot**: https://certbot.eff.org/
- **acme.sh**: https://github.com/acmesh-official/acme.sh

Example with certbot:

```bash
# Install certbot
sudo apt-get install certbot

# Obtain certificate for your domain
sudo certbot certonly --standalone -d your-domain.com

# Copy certificates to this directory
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./fullchain.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ./privkey.pem
sudo chown $USER:$USER fullchain.pem privkey.pem
```

### Option 2: Commercial CA

Purchase a certificate from a commercial Certificate Authority (e.g., DigiCert, Sectigo, etc.) and place the files in this directory following the naming convention above.

## Security Best Practices

1. **Never commit certificates to version control**
   - The `.gitignore` file should exclude `*.pem` files
   - Keep your private keys secure
   
2. **Set proper file permissions**
   ```bash
   chmod 644 fullchain.pem
   chmod 600 privkey.pem
   ```

3. **Rotate certificates before expiry**
   - Let's Encrypt certificates expire after 90 days
   - Set up automatic renewal (certbot does this by default)

4. **Use strong key sizes**
   - Minimum 2048-bit RSA keys (4096-bit recommended)
   - Or use ECDSA with P-256 or P-384 curves
