#!/bin/bash
# Generate self-signed certificates for development/testing
# DO NOT use these certificates in production!

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_FILE="${SCRIPT_DIR}/fullchain.pem"
KEY_FILE="${SCRIPT_DIR}/privkey.pem"

# Default domain
DOMAIN="${1:-localhost}"

echo "🔐 Generating self-signed TLS certificate for ${DOMAIN}..."
echo ""
echo "⚠️  WARNING: This is for DEVELOPMENT/TESTING ONLY!"
echo "    Self-signed certificates will show security warnings in browsers."
echo "    For production, use certificates from a trusted CA like Let's Encrypt."
echo ""

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    echo "❌ Error: openssl is not installed"
    echo "   Install it with: sudo apt-get install openssl"
    exit 1
fi

# Generate private key and certificate
openssl req -x509 -nodes -days 365 -newkey rsa:4096 \
    -keyout "${KEY_FILE}" \
    -out "${CERT_FILE}" \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=${DOMAIN}" \
    -addext "subjectAltName=DNS:${DOMAIN},DNS:*.${DOMAIN},DNS:localhost,DNS:*.localhost"

# Set proper permissions
chmod 644 "${CERT_FILE}"
chmod 600 "${KEY_FILE}"

echo ""
echo "✅ Certificate generation complete!"
echo ""
echo "   Certificate: ${CERT_FILE}"
echo "   Private Key: ${KEY_FILE}"
echo "   Valid for: 365 days"
echo "   Domain: ${DOMAIN} (including *.${DOMAIN} and localhost)"
echo ""
echo "📝 To use with Traefik:"
echo "   These files are already in the correct location for compose.traefik.secure.tls.yml"
echo ""
echo "🌐 Browser Trust Instructions:"
echo "   Chrome/Edge: chrome://settings/security → Manage certificates → Import"
echo "   Firefox: Settings → Privacy & Security → Certificates → View Certificates → Import"
echo ""
