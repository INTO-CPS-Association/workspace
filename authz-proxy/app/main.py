
"""
Authorization Proxy Service - PEP/PDP Implementation

This service implements both Policy Enforcement Point (PEP) and Policy Decision Point (PDP)
for HTTP-based access control in the workspace environment.

Architecture:
- PEP: Intercepts HTTP requests and enforces access decisions before reaching protected resources
- PDP: Evaluates JWT token claims (roles, policy) against path-based rules and returns decisions
- Integration: Works with Keycloak (authentication/tokens) and MinIO (S3 storage/policies)

Policy Model:
- Keycloak issues JWT tokens with 'policy' and 'roles' claims
- This service evaluates HTTP access (path-based rules)
- MinIO evaluates S3 access (bucket policies based on JWT claims)
- s3fs-fuse mounts translate filesystem operations to S3 calls (enforced by MinIO)

Key Roles:
- admin: Full access to all resources
- common-writer: Read/write access to /common/ resources
- common-reader: Read-only access to /common/ resources
- user: Access to own private resources (/username/)
"""
import os
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings
from keycloak import KeycloakOpenID, KeycloakAdmin
from minio import Minio
from cachetools import TTLCache
import httpx
import jose
from jose import jwt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""
    keycloak_url: str = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
    keycloak_realm: str = os.getenv("KEYCLOAK_REALM", "workspace")
    keycloak_client_id: str = os.getenv("KEYCLOAK_CLIENT_ID", "authz-proxy")
    keycloak_client_secret: str = os.getenv("KEYCLOAK_CLIENT_SECRET", "authz-proxy-secret")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    policy_decision_cache_ttl: int = int(os.getenv("POLICY_DECISION_CACHE_TTL", "300"))


settings = Settings()
app = FastAPI(
    title="Authorization Proxy Service",
    version="1.0.0",
    description="PEP/PDP Authorization service for workspace access control",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/authz"  # Support reverse proxy with path prefix
)

# Initialize Keycloak clients
# python-keycloak library constructs URLs as: {server_url}/realms/{realm_name}/...
# Our Keycloak runs without /auth context path, so we use the base URL directly
keycloak_server_url = settings.keycloak_url.rstrip('/')
keycloak_openid = KeycloakOpenID(
    server_url=keycloak_server_url,
    client_id=settings.keycloak_client_id,
    realm_name=settings.keycloak_realm,
    client_secret_key=settings.keycloak_client_secret
)

# Policy decision cache
policy_cache = TTLCache(maxsize=1000, ttl=settings.policy_decision_cache_ttl)

# Public key cache
_public_key_cache: Optional[str] = None


def get_keycloak_public_key() -> str:
    """Get Keycloak public key from the realm"""
    global _public_key_cache

    if _public_key_cache:
        return _public_key_cache

    try:
        public_key = keycloak_openid.public_key()
        if not public_key:
            raise Exception("Empty public key from Keycloak")

        # Format the key in PEM format if it's not already
        if not public_key.startswith("-----BEGIN"):
            public_key = f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"

        _public_key_cache = public_key
        return public_key

    except Exception as e:
        logger.error(f"Failed to fetch Keycloak public key: {e}")
        raise


# Dependency for extracting and validating token
async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Extract and validate JWT token from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    try:
        # Extract Bearer token
        token = authorization.replace("Bearer ", "")
        
        # Get JWKS for verification
        try:
            public_key = get_keycloak_public_key()

            # Decode and verify token using Keycloak public key
            decoded_token = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )
        except jwt.ExpiredSignatureError:
            logger.error("Token has expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.JWTError as e:
            logger.error(f"Token decode error: {e}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
        
        # Extract username and roles from token
        username = decoded_token.get("preferred_username")
        email = decoded_token.get("email")
        sub = decoded_token.get("sub")
        
        # Extract roles from realm_access
        roles = []
        if "realm_access" in decoded_token:
            roles = decoded_token["realm_access"].get("roles", [])
        
        logger.info(f"User {username} authenticated with roles: {roles}")
        
        return {
            "token": token,
            "username": username,
            "email": email,
            "roles": roles,
            "sub": sub
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class PolicyEnforcementPoint:
    """
    PEP - Policy Enforcement Point
    
    The PEP intercepts access requests and enforces authorization decisions.
    It acts as the gatekeeper, consulting the PDP before allowing access to protected resources.
    
    Responsibilities:
    - Intercept HTTP requests for protected resources
    - Extract user identity and requested resource/action
    - Query the PDP for an access decision
    - Cache decisions for performance (TTL-based)
    - Block or allow access based on PDP decision
    """
    
    @staticmethod
    async def enforce(
        user: Dict[str, Any],
        resource_path: str,
        action: str
    ) -> bool:
        """
        Enforce access control policy by consulting the PDP
        
        Args:
            user: User information from validated JWT token (username, roles, etc.)
            resource_path: Path to the resource being accessed (e.g., /common/data/file.txt)
            action: Action to perform (read, write, delete)
        
        Returns:
            True if access is granted, False otherwise
        """
        # Create cache key
        cache_key = f"{user['username']}:{resource_path}:{action}"
        
        # Check cache first
        if cache_key in policy_cache:
            logger.info(f"Cache hit for {cache_key}")
            return policy_cache[cache_key]
        
        # Query Policy Decision Point
        pdp = PolicyDecisionPoint()
        decision = await pdp.evaluate(user, resource_path, action)
        
        # Cache the decision
        policy_cache[cache_key] = decision
        
        return decision


class PolicyDecisionPoint:
    """
    PDP - Policy Decision Point
    
    The PDP makes authorization decisions based on policy rules.
    It evaluates user attributes (roles, identity) against resource requirements.
    
    Responsibilities:
    - Evaluate user's roles and identity from JWT token
    - Apply path-based policy rules (common vs private resources)
    - Determine resource type and ownership
    - Return access decision (grant/deny)
    
    Policy Rules:
    1. Admin Role: Full access to all resources
    2. Private Resources (/username/*): Users can access only their own
    3. Common Resources (/common/*):
       - common-reader: read access only
       - common-writer: read, write, and delete access
    
    Note: This PDP handles HTTP access control. MinIO acts as PDP for S3 operations,
    evaluating the 'policy' claim from JWT tokens against bucket policies.
    """
    
    async def evaluate(
        self,
        user: Dict[str, Any],
        resource_path: str,
        action: str
    ) -> bool:
        """
        Evaluate access control policy based on roles and resource ownership
        
        Args:
            user: User information from JWT token (username, roles, email, sub)
            resource_path: Resource path (e.g., /common/data/file.txt or /user1/data/file.txt)
            action: Action to perform (read, write, delete)
        
        Returns:
            True if access is granted based on policy rules, False otherwise
        """
        try:
            # Determine resource type
            resource_type = self._determine_resource_type(resource_path, user['username'])
            
            # Check admin role
            if "admin" in user['roles']:
                logger.info(f"Admin access granted for {user['username']} to {resource_path}")
                return True
            
            # Apply policies based on resource type
            if resource_type == "common":
                return await self._evaluate_common_resource(user, action)
            elif resource_type == "user_private":
                return await self._evaluate_user_resource(user, resource_path, action)
            else:
                logger.warning(f"Unknown resource type for {resource_path}")
                return False
                
        except Exception as e:
            logger.error(f"Policy evaluation error: {e}")
            return False
    
    def _determine_resource_type(self, resource_path: str, username: str) -> str:
        """Determine the type of resource being accessed"""
        if resource_path.startswith("/common") or resource_path.startswith("common/"):
            return "common"
        elif username in resource_path or resource_path.startswith(f"/{username}"):
            return "user_private"
        return "unknown"
    
    async def _evaluate_common_resource(self, user: Dict[str, Any], action: str) -> bool:
        """Evaluate access to common shared resources"""
        if action == "read":
            # Anyone with common-reader or common-writer role can read
            has_access = "common-reader" in user['roles'] or "common-writer" in user['roles']
            logger.info(f"Common read access for {user['username']}: {has_access}")
            return has_access
        elif action in ["write", "delete"]:
            # Only common-writer role can write/delete
            has_access = "common-writer" in user['roles']
            logger.info(f"Common write access for {user['username']}: {has_access}")
            return has_access
        return False
    
    async def _evaluate_user_resource(
        self,
        user: Dict[str, Any],
        resource_path: str,
        action: str
    ) -> bool:
        """Evaluate access to user private resources"""
        # Extract owner from path
        path_parts = resource_path.strip('/').split('/')
        resource_owner = path_parts[0] if path_parts else None
        
        # User can access their own resources
        has_access = user['username'] == resource_owner
        logger.info(f"User resource access for {user['username']} to {resource_path}: {has_access}")
        return has_access


@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "service": "authz-proxy",
        "version": "1.0.0",
        "description": "Authorization Proxy Service - PEP/PDP for access control",
        "documentation": {
            "interactive_api_docs": "http://localhost/authz/docs",
            "alternative_docs": "http://localhost/authz/redoc"
        },
        "endpoints": {
            "production": {
                "/health": "GET - Health check",
                "/authorize": "POST - Authorize resource access",
                "/minio/presigned-url": "POST - Generate MinIO presigned URL",
                "/user/permissions": "GET - Get user permissions"
            },
            "testing": {
                "/test/simulate": "POST - Simulate authorization (detailed response)",
                "/test/batch": "POST - Test multiple scenarios at once",
                "/test/scenarios": "GET - Get predefined test scenarios",
                "/test/policy-info": "GET - Get policy implementation details",
                "/test/cache-stats": "GET - Get cache statistics",
                "/test/cache-clear": "POST - Clear policy cache (admin only)",
                "/test/debug": "GET - Get debug information"
            }
        },
        "quick_test": "Try: curl -X POST http://localhost/authz/test/scenarios"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "authz-proxy"}


@app.post("/authorize")
async def authorize(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Authorization endpoint - PEP entry point
    
    Expected request body:
    {
        "resource_path": "/common/data/file.txt",
        "action": "read"
    }
    """
    try:
        body = await request.json()
        resource_path = body.get("resource_path")
        action = body.get("action", "read")
        
        if not resource_path:
            raise HTTPException(status_code=400, detail="resource_path is required")
        
        # Enforce policy
        pep = PolicyEnforcementPoint()
        granted = await pep.enforce(user, resource_path, action)
        
        if granted:
            logger.info(f"Access GRANTED: {user['username']} -> {resource_path} ({action})")
            return {
                "decision": "GRANT",
                "user": user['username'],
                "resource": resource_path,
                "action": action
            }
        else:
            logger.warning(f"Access DENIED: {user['username']} -> {resource_path} ({action})")
            raise HTTPException(
                status_code=403,
                detail="Access denied by policy"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authorization error: {e}")
        raise HTTPException(status_code=500, detail="Internal authorization error")


@app.post("/minio/presigned-url")
async def get_presigned_url(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Generate presigned URL for MinIO access after authorization
    
    Expected request body:
    {
        "bucket": "user1",
        "object_path": "data/file.txt",
        "action": "read",
        "expires": 3600
    }
    """
    try:
        body = await request.json()
        bucket = body.get("bucket")
        object_path = body.get("object_path")
        action = body.get("action", "read")
        expires = body.get("expires", 3600)
        
        # Construct full resource path for authorization
        resource_path = f"/{bucket}/{object_path}"
        
        # Check authorization first
        pep = PolicyEnforcementPoint()
        granted = await pep.enforce(user, resource_path, action)
        
        if not granted:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Generate presigned URL
        minio_client = Minio(
            settings.minio_endpoint.replace("http://", ""),
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False
        )
        
        if action == "read":
            url = minio_client.presigned_get_object(bucket, object_path, expires=expires)
        elif action == "write":
            url = minio_client.presigned_put_object(bucket, object_path, expires=expires)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        return {
            "presigned_url": url,
            "expires_in": expires,
            "action": action
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Presigned URL generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate presigned URL")


@app.get("/user/permissions")
async def get_user_permissions(user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user's permissions"""
    return {
        "username": user['username'],
        "roles": user['roles'],
        "permissions": {
            "common_read": "common-reader" in user['roles'] or "common-writer" in user['roles'],
            "common_write": "common-writer" in user['roles'],
            "admin": "admin" in user['roles']
        }
    }


@app.post("/test/simulate")
async def simulate_authorization(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Simulate authorization without enforcing (for testing)
    
    Expected request body:
    {
        "resource_path": "/user1/data/file.txt",
        "action": "read"
    }
    
    Returns detailed decision information for debugging
    """
    try:
        body = await request.json()
        resource_path = body.get("resource_path")
        action = body.get("action", "read")
        
        if not resource_path:
            raise HTTPException(status_code=400, detail="resource_path is required")
        
        # Simulate policy evaluation
        pdp = PolicyDecisionPoint()
        resource_type = pdp._determine_resource_type(resource_path, user['username'])
        
        # Get decision
        granted = await pdp.evaluate(user, resource_path, action)
        
        # Build detailed response
        return {
            "decision": "GRANT" if granted else "DENY",
            "user": {
                "username": user['username'],
                "roles": user['roles'],
                "email": user.get('email')
            },
            "resource": {
                "path": resource_path,
                "type": resource_type,
                "action": action
            },
            "evaluation": {
                "is_admin": "admin" in user['roles'],
                "resource_owner_match": user['username'] in resource_path,
                "applicable_roles": [r for r in user['roles'] if r in ['common-reader', 'common-writer', 'admin']]
            },
            "timestamp": __import__('datetime').datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simulation error: {e}")
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")


@app.post("/test/batch")
async def batch_test_authorization(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Test multiple authorization scenarios at once
    
    Expected request body:
    {
        "tests": [
            {"resource_path": "/user1/data/file.txt", "action": "read"},
            {"resource_path": "/common/data/file.txt", "action": "write"}
        ]
    }
    """
    try:
        body = await request.json()
        tests = body.get("tests", [])
        
        if not tests:
            raise HTTPException(status_code=400, detail="tests array is required")
        
        results = []
        pdp = PolicyDecisionPoint()
        
        for test in tests:
            resource_path = test.get("resource_path")
            action = test.get("action", "read")
            
            if not resource_path:
                results.append({
                    "resource_path": None,
                    "action": action,
                    "decision": "ERROR",
                    "error": "resource_path is required"
                })
                continue
            
            try:
                granted = await pdp.evaluate(user, resource_path, action)
                resource_type = pdp._determine_resource_type(resource_path, user['username'])
                
                results.append({
                    "resource_path": resource_path,
                    "action": action,
                    "decision": "GRANT" if granted else "DENY",
                    "resource_type": resource_type
                })
            except Exception as e:
                results.append({
                    "resource_path": resource_path,
                    "action": action,
                    "decision": "ERROR",
                    "error": str(e)
                })
        
        # Summary
        granted_count = sum(1 for r in results if r.get("decision") == "GRANT")
        denied_count = sum(1 for r in results if r.get("decision") == "DENY")
        error_count = sum(1 for r in results if r.get("decision") == "ERROR")
        
        return {
            "user": user['username'],
            "total_tests": len(results),
            "summary": {
                "granted": granted_count,
                "denied": denied_count,
                "errors": error_count
            },
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch test error: {e}")
        raise HTTPException(status_code=500, detail=f"Batch test error: {str(e)}")


@app.get("/test/scenarios")
async def get_test_scenarios():
    """
    Get predefined test scenarios for different users
    Returns common test cases for validation
    """
    return {
        "scenarios": [
            {
                "name": "User1 - Own Resources",
                "user": "user1",
                "tests": [
                    {"resource_path": "/user1/data/file.txt", "action": "read", "expected": "GRANT"},
                    {"resource_path": "/user1/data/file.txt", "action": "write", "expected": "GRANT"},
                    {"resource_path": "/user1/models/model.py", "action": "delete", "expected": "GRANT"}
                ]
            },
            {
                "name": "User1 - Other User Resources",
                "user": "user1",
                "tests": [
                    {"resource_path": "/user2/data/file.txt", "action": "read", "expected": "DENY"},
                    {"resource_path": "/user2/data/file.txt", "action": "write", "expected": "DENY"}
                ]
            },
            {
                "name": "User1 - Common Resources (Writer)",
                "user": "user1",
                "tests": [
                    {"resource_path": "/common/data/shared.txt", "action": "read", "expected": "GRANT"},
                    {"resource_path": "/common/tools/script.sh", "action": "write", "expected": "GRANT"},
                    {"resource_path": "/common/data/file.txt", "action": "delete", "expected": "GRANT"}
                ]
            },
            {
                "name": "User2 - Common Resources (Reader)",
                "user": "user2",
                "tests": [
                    {"resource_path": "/common/data/shared.txt", "action": "read", "expected": "GRANT"},
                    {"resource_path": "/common/tools/script.sh", "action": "write", "expected": "DENY"}
                ]
            },
            {
                "name": "Admin - All Resources",
                "user": "admin",
                "tests": [
                    {"resource_path": "/user1/data/file.txt", "action": "read", "expected": "GRANT"},
                    {"resource_path": "/user2/data/file.txt", "action": "write", "expected": "GRANT"},
                    {"resource_path": "/common/data/file.txt", "action": "delete", "expected": "GRANT"}
                ]
            }
        ],
        "usage": "Use these scenarios with the /test/batch endpoint to validate policy enforcement"
    }


@app.get("/test/policy-info")
async def get_policy_info():
    """
    Get information about implemented policies
    Useful for understanding access control rules
    """
    return {
        "policies": {
            "user_private": {
                "description": "Users can access only their own private resources",
                "rules": [
                    "Resource path must contain username (e.g., /user1/data/file.txt)",
                    "All actions (read, write, delete) are allowed on own resources",
                    "Admin role bypasses this restriction"
                ],
                "examples": {
                    "allowed": [
                        "user1 -> /user1/data/file.txt (any action)",
                        "user2 -> /user2/models/model.py (any action)"
                    ],
                    "denied": [
                        "user1 -> /user2/data/file.txt (any action)",
                        "user2 -> /user1/data/file.txt (any action)"
                    ]
                }
            },
            "common_resources": {
                "description": "Shared resources accessible based on roles",
                "rules": [
                    "Resources under /common/ path",
                    "common-reader role: read access only",
                    "common-writer role: read, write, and delete access",
                    "Admin role bypasses all restrictions"
                ],
                "roles": {
                    "common-reader": ["read"],
                    "common-writer": ["read", "write", "delete"]
                },
                "examples": {
                    "user1_writer": {
                        "allowed": ["read /common/data/file.txt", "write /common/data/file.txt", "delete /common/data/file.txt"],
                        "denied": []
                    },
                    "user2_reader": {
                        "allowed": ["read /common/data/file.txt"],
                        "denied": ["write /common/data/file.txt", "delete /common/data/file.txt"]
                    }
                }
            },
            "admin": {
                "description": "Admin role has unrestricted access",
                "rules": [
                    "Admin role grants access to all resources",
                    "All actions are allowed",
                    "Bypasses all other policy checks"
                ]
            }
        },
        "cache": {
            "enabled": True,
            "ttl_seconds": settings.policy_decision_cache_ttl,
            "current_entries": len(policy_cache)
        }
    }


@app.get("/test/cache-stats")
async def get_cache_stats():
    """Get policy decision cache statistics"""
    return {
        "cache": {
            "max_size": policy_cache.maxsize,
            "ttl_seconds": policy_cache.ttl,
            "current_entries": len(policy_cache),
            "available_space": policy_cache.maxsize - len(policy_cache)
        }
    }


@app.post("/test/cache-clear")
async def clear_cache(user: Dict[str, Any] = Depends(get_current_user)):
    """Clear the policy decision cache (requires authentication)"""
    if "admin" not in user['roles']:
        raise HTTPException(status_code=403, detail="Admin role required")
    
    initial_size = len(policy_cache)
    policy_cache.clear()
    
    return {
        "message": "Cache cleared successfully",
        "cleared_entries": initial_size,
        "current_entries": len(policy_cache)
    }


@app.get("/test/debug")
async def debug_info(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get debug information about current session
    Useful for troubleshooting authorization issues
    """
    return {
        "user": {
            "username": user['username'],
            "email": user.get('email'),
            "roles": user['roles'],
            "sub": user.get('sub')
        },
        "service": {
            "keycloak_url": settings.keycloak_url,
            "keycloak_realm": settings.keycloak_realm,
            "minio_endpoint": settings.minio_endpoint
        },
        "capabilities": {
            "can_read_common": "common-reader" in user['roles'] or "common-writer" in user['roles'] or "admin" in user['roles'],
            "can_write_common": "common-writer" in user['roles'] or "admin" in user['roles'],
            "is_admin": "admin" in user['roles']
        },
        "accessible_resources": {
            "private": f"/{user['username']}/*",
            "common_read": "/common/*" if ("common-reader" in user['roles'] or "common-writer" in user['roles'] or "admin" in user['roles']) else None,
            "common_write": "/common/*" if ("common-writer" in user['roles'] or "admin" in user['roles']) else None
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
