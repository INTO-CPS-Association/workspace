# Injects a local mkcert root CA into the thomseddon/traefik-forward-auth
# image so that HTTPS redirects through a self-signed certificate are
# validated instead of rejected.
#
# Build (from workspaces/test/dtaas/ci/):
#   docker build -t traefik-forward-auth-local:latest ./certs/

# Stage 1: prepare the updated CA bundle on Alpine
FROM alpine:3.21 AS cert-builder
RUN apk add --no-cache ca-certificates=20241121-r1
COPY rootCA.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Stage 2: copy updated bundle into the forward-auth image
FROM thomseddon/traefik-forward-auth:fix-dont-require-self-middleware-test1
COPY --from=cert-builder /etc/ssl/certs/ca-certificates.crt \
     /etc/ssl/certs/ca-certificates.crt

CMD ["traefik-forward-auth"]
