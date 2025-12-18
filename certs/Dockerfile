# Injects a local certificate into the
# thomseddon/traefik-forward-auth image

# Stage 1: Use Alpine to prepare certificates
FROM alpine:3 AS cert-builder

# Install ca-certificates and prepare the certificate
RUN apk add --no-cache ca-certificates=20251003-r0
COPY rootCA.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Stage 2: Copy certificates to the final image
FROM thomseddon/traefik-forward-auth:fix-dont-require-self-middleware-test1
COPY --from=cert-builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

CMD ["traefik-forward-auth"]