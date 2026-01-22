#!/usr/bin/env python3
"""
Test script to verify Keycloak claim mapping to MinIO policies.
This script validates that the policy claim is correctly generated and can be used by MinIO.
"""

import requests
import jwt
import json
import sys
from typing import Dict, Any


class KeycloakMinIOTester:
    def __init__(self, keycloak_url: str, minio_console_url: str):
        self.keycloak_url = keycloak_url
        self.minio_console_url = minio_console_url
        self.realm = "workspace"
        self.client_id = "minio"
        self.client_secret = "minio-client-secret"
    
    def get_token(self, username: str, password: str) -> Dict[str, Any]:
        """Get an access token from Keycloak."""
        token_url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        
        data = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "openid profile email"
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get token: {e}")
            return {}
    
    def decode_token(self, access_token: str) -> Dict[str, Any]:
        """Decode JWT token without verification to inspect claims."""
        try:
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            return decoded
        except Exception as e:
            print(f"❌ Failed to decode token: {e}")
            return {}
    
    def test_user_policy_mapping(self, username: str, password: str, expected_policies: list):
        """Test that a user gets the expected policy claim."""
        print(f"\n{'='*70}")
        print(f"Testing user: {username}")
        print(f"{'='*70}")
        
        # Get token
        token_response = self.get_token(username, password)
        if not token_response:
            return False
        
        access_token = token_response.get("access_token")
        if not access_token:
            print("❌ No access token in response")
            return False
        
        print("✅ Successfully obtained access token")
        
        # Decode token
        decoded = self.decode_token(access_token)
        if not decoded:
            return False
        
        # Extract claims
        preferred_username = decoded.get("preferred_username", "N/A")
        roles = decoded.get("roles", [])
        policy_claim = decoded.get("policy", "N/A")
        email = decoded.get("email", "N/A")
        
        print(f"\n📋 Token Claims:")
        print(f"   Username: {preferred_username}")
        print(f"   Email: {email}")
        print(f"   Roles: {json.dumps(roles, indent=6)}")
        print(f"   Policy Claim: {policy_claim}")
        
        # Validate policy claim
        print(f"\n🔍 Policy Validation:")
        if isinstance(policy_claim, str):
            # Try to parse if it's a string representation of a list
            try:
                if policy_claim.startswith('['):
                    policies = [p.strip() for p in policy_claim.strip('[]').split(',')]
                else:
                    policies = [policy_claim]
            except:
                policies = [policy_claim]
        elif isinstance(policy_claim, list):
            policies = policy_claim
        else:
            policies = []
        
        print(f"   Extracted policies: {policies}")
        print(f"   Expected policies: {expected_policies}")
        
        # Check if all expected policies are present
        missing_policies = [p for p in expected_policies if p not in str(policy_claim)]
        unexpected_policies = [p for p in policies if p not in expected_policies and p != 'N/A']
        
        if missing_policies:
            print(f"   ❌ Missing policies: {missing_policies}")
            return False
        
        if unexpected_policies:
            print(f"   ⚠️  Unexpected policies: {unexpected_policies}")
        
        print(f"   ✅ All expected policies found!")
        
        # Display token expiration
        exp = decoded.get("exp")
        iat = decoded.get("iat")
        if exp and iat:
            validity = exp - iat
            print(f"\n⏰ Token Validity: {validity} seconds ({validity/60:.1f} minutes)")
        
        return True
    
    def run_all_tests(self):
        """Run tests for all users."""
        print("\n" + "="*70)
        print("KEYCLOAK → MinIO POLICY MAPPING TESTS")
        print("="*70)
        
        test_cases = [
            {
                "username": "user1",
                "password": "user1password",
                "expected_policies": ["common-read", "user-full-access"]
            },
            {
                "username": "user2",
                "password": "user2password",
                "expected_policies": ["common-read", "user-full-access"]
            },
            {
                "username": "admin",
                "password": "adminpassword",
                "expected_policies": ["consoleAdmin", "readwrite"]
            }
        ]
        
        results = []
        for test in test_cases:
            success = self.test_user_policy_mapping(
                test["username"],
                test["password"],
                test["expected_policies"]
            )
            results.append({
                "user": test["username"],
                "success": success
            })
        
        # Summary
        print(f"\n{'='*70}")
        print("TEST SUMMARY")
        print(f"{'='*70}")
        
        passed = sum(1 for r in results if r["success"])
        total = len(results)
        
        for result in results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"   {status}: {result['user']}")
        
        print(f"\n   Total: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n   🎉 All tests passed! Keycloak-MinIO mapping is working correctly.")
            return 0
        else:
            print(f"\n   ⚠️  {total - passed} test(s) failed. Please check the configuration.")
            return 1


def main():
    keycloak_url = "http://localhost:8180"
    minio_console = "http://localhost:9001"
    
    tester = KeycloakMinIOTester(keycloak_url, minio_console)
    exit_code = tester.run_all_tests()
    
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("1. Test MinIO Console access:")
    print("   - Open http://localhost:9001")
    print("   - Click 'Login with SSO'")
    print("   - Login as user1/user1password")
    print("   - Verify access to common/ (read-only) and user1/ (full access)")
    print()
    print("2. Test with user2:")
    print("   - Same as above but login as user2/user2password")
    print("   - Verify access to common/ (read-only) and user2/ (full access)")
    print()
    print("3. Test with admin:")
    print("   - Login as admin/adminpassword")
    print("   - Verify admin console access and full bucket access")
    print("="*70)
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
