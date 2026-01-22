#!/bin/bash
# MinIO Policy Initialization Script
# This script creates MinIO policies that align with Keycloak roles

set -e

echo "Initializing MinIO policies..."

# Wait for MinIO to be ready
echo "Waiting for MinIO to be ready..."
until mc alias set local http://minio:9000 minioadmin minioadmin; do
  echo "MinIO not ready yet, retrying in 5 seconds..."
  sleep 5
done

echo "MinIO is ready!"

# Create buckets if they don't exist
echo "Creating buckets..."
mc mb local/user1 --ignore-existing
mc mb local/user2 --ignore-existing
mc mb local/common --ignore-existing

echo "Creating MinIO policies..."

# Create common-read policy
cat > /tmp/common-read-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::common",
        "arn:aws:s3:::common/*"
      ]
    }
  ]
}
EOF

mc admin policy create local common-read /tmp/common-read-policy.json || \
  mc admin policy update local common-read /tmp/common-read-policy.json

# Create common-write policy
cat > /tmp/common-write-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::common",
        "arn:aws:s3:::common/*"
      ]
    }
  ]
}
EOF

mc admin policy create local common-write /tmp/common-write-policy.json || \
  mc admin policy update local common-write /tmp/common-write-policy.json

# Create user-specific policies
for username in user1 user2; do
  cat > /tmp/user-${username}-full-access.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::${username}",
        "arn:aws:s3:::${username}/*"
      ]
    }
  ]
}
EOF

  mc admin policy create local "user-${username}-full-access" "/tmp/user-${username}-full-access.json" || \
    mc admin policy update local "user-${username}-full-access" "/tmp/user-${username}-full-access.json"
done

# Create admin policies
cat > /tmp/consoleAdmin.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "admin:*"
      ]
    }
  ]
}
EOF

mc admin policy create local consoleAdmin /tmp/consoleAdmin.json || \
  mc admin policy update local consoleAdmin /tmp/consoleAdmin.json

cat > /tmp/readwrite.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::*"
      ]
    }
  ]
}
EOF

mc admin policy create local readwrite /tmp/readwrite.json || \
  mc admin policy update local readwrite /tmp/readwrite.json

# Create readonly policy
cat > /tmp/readonly.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::*"
      ]
    }
  ]
}
EOF

mc admin policy create local readonly /tmp/readonly.json || \
  mc admin policy update local readonly /tmp/readonly.json

echo "MinIO policies created successfully!"

# List all policies
echo -e "\nAvailable policies:"
mc admin policy list local

# Clean up temporary files
rm -f /tmp/*.json

echo "Policy initialization complete!"
