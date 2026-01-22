#!/usr/bin/env python3
"""
Test script for authorization proxy
Demonstrates the PEP/PDP pattern in action
"""

import requests
import json
import sys
from typing import Dict, Any


class AuthzTester:
    """Test authorization policies"""
    
    def __init__(
        self,
        keycloak_url: str = "http://localhost:8180",
        authz_url: str = "http://localhost:8300"
    ):
        self.keycloak_url = keycloak_url
        self.authz_url = authz_url
        self.realm = "workspace"
        self.client_id = "workspace-frontend"
        
    def get_token(self, username: str, password: str) -> str:
        """Get JWT token from Keycloak"""
        url = f"{self.keycloak_url}/realms/{self.realm}/protocol/openid-connect/token"
        
        data = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "client_id": self.client_id
        }
        
        try:
            response = requests.post(url, data=data, timeout=10)
            print(f"🔍 Token request to: {url}")
            print(f"🔍 Response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ Keycloak error: {response.text}")
                sys.exit(1)
            
            response.raise_for_status()
            token_data = response.json()
            
            if "access_token" not in token_data:
                print(f"❌ No access_token in response: {token_data}")
                sys.exit(1)
            
            print(f"✅ Token retrieved successfully (length: {len(token_data['access_token'])})")
            return token_data["access_token"]
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get token (network error): {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Failed to get token (unexpected error): {e}")
            sys.exit(1)
    
    def check_authorization(
        self,
        token: str,
        resource_path: str,
        action: str = "read"
    ) -> Dict[str, Any]:
        """Check authorization for a resource"""
        url = f"{self.authz_url}/authorize"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "resource_path": resource_path,
            "action": action
        }
        
        try:
            print(f"🔍 Authorization request to: {url}")
            print(f"🔍 Resource: {resource_path}, Action: {action}")
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            print(f"🔍 Authorization response status: {response.status_code}")
            
            if response.status_code == 200:
                return {"granted": True, "data": response.json()}
            elif response.status_code == 403:
                print(f"🔍 Access denied response: {response.text}")
                return {"granted": False, "reason": "Access denied"}
            else:
                print(f"🔍 Unexpected response: {response.text}")
                return {"granted": False, "reason": response.text}
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
            return {"granted": False, "reason": str(e)}
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return {"granted": False, "reason": str(e)}
    
    def get_permissions(self, token: str) -> Dict[str, Any]:
        """Get user's permissions"""
        url = f"{self.authz_url}/user/permissions"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get permissions: {e}")
            return {}
    
    def simulate_authorization(
        self,
        token: str,
        resource_path: str,
        action: str = "read"
    ) -> Dict[str, Any]:
        """Simulate authorization with detailed debug info"""
        url = f"{self.authz_url}/test/simulate"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "resource_path": resource_path,
            "action": action
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Simulation failed: {e}")
            return {}
    
    def batch_test(self, token: str, tests: list) -> Dict[str, Any]:
        """Run batch authorization tests"""
        url = f"{self.authz_url}/test/batch"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        data = {"tests": tests}
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Batch test failed: {e}")
            return {}
    
    def get_test_scenarios(self) -> Dict[str, Any]:
        """Get predefined test scenarios"""
        url = f"{self.authz_url}/test/scenarios"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get scenarios: {e}")
            return {}
    
    def get_policy_info(self) -> Dict[str, Any]:
        """Get policy implementation details"""
        url = f"{self.authz_url}/test/policy-info"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get policy info: {e}")
            return {}
    
    def get_debug_info(self, token: str) -> Dict[str, Any]:
        """Get debug information"""
        url = f"{self.authz_url}/test/debug"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get debug info: {e}")
            return {}
    
    def run_test_suite(self):
        """Run comprehensive authorization tests"""
        print("=" * 60)
        print("  Authorization Policy Test Suite")
        print("=" * 60)
        print()
        
        # Test scenarios
        scenarios = [
            {
                "name": "User1: Read own resources",
                "user": "user1",
                "password": "user1password",
                "resource": "/user1/data/file.txt",
                "action": "read",
                "expected": True
            },
            {
                "name": "User1: Write own resources",
                "user": "user1",
                "password": "user1password",
                "resource": "/user1/data/file.txt",
                "action": "write",
                "expected": True
            },
            {
                "name": "User1: Read User2's resources",
                "user": "user1",
                "password": "user1password",
                "resource": "/user2/data/file.txt",
                "action": "read",
                "expected": False
            },
            {
                "name": "User1: Read common resources",
                "user": "user1",
                "password": "user1password",
                "resource": "/common/data/file.txt",
                "action": "read",
                "expected": True
            },
            {
                "name": "User1: Write common resources",
                "user": "user1",
                "password": "user1password",
                "resource": "/common/data/file.txt",
                "action": "write",
                "expected": True
            },
            {
                "name": "User2: Read common resources",
                "user": "user2",
                "password": "user2password",
                "resource": "/common/data/file.txt",
                "action": "read",
                "expected": True
            },
            {
                "name": "User2: Write common resources",
                "user": "user2",
                "password": "user2password",
                "resource": "/common/data/file.txt",
                "action": "write",
                "expected": False
            },
            {
                "name": "Admin: Read User1's resources",
                "user": "admin",
                "password": "adminpassword",
                "resource": "/user1/data/file.txt",
                "action": "read",
                "expected": True
            },
            {
                "name": "Admin: Write User2's resources",
                "user": "admin",
                "password": "adminpassword",
                "resource": "/user2/data/file.txt",
                "action": "write",
                "expected": True
            }
        ]
        
        passed = 0
        failed = 0
        
        for scenario in scenarios:
            print(f"Testing: {scenario['name']}")
            
            # Get token
            token = self.get_token(scenario['user'], scenario['password'])
            
            # Check authorization
            result = self.check_authorization(
                token,
                scenario['resource'],
                scenario['action']
            )
            
            # Verify result
            if result['granted'] == scenario['expected']:
                print(f"  ✅ PASS - Access {'granted' if result['granted'] else 'denied'}")
                passed += 1
            else:
                print(f"  ❌ FAIL - Expected {'grant' if scenario['expected'] else 'deny'}, "
                      f"got {'grant' if result['granted'] else 'deny'}")
                if not result['granted'] and 'reason' in result:
                    print(f"     Reason: {result['reason']}")
                failed += 1
            
            print()
        
        # Summary
        print("=" * 60)
        print(f"  Test Results: {passed} passed, {failed} failed")
        print("=" * 60)
        print()
        
        # Show user permissions
        print("User Permissions:")
        print("-" * 60)
        
        for user, password in [("user1", "user1password"), 
                               ("user2", "user2password"), 
                               ("admin", "adminpassword")]:
            token = self.get_token(user, password)
            perms = self.get_permissions(token)
            
            print(f"\n{user}:")
            print(f"  Roles: {', '.join(perms.get('roles', []))}")
            print(f"  Permissions:")
            for perm, value in perms.get('permissions', {}).items():
                print(f"    • {perm}: {'✓' if value else '✗'}")
        
        print()
        return failed == 0


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test authorization policies")
    parser.add_argument(
        "--keycloak-url",
        default="http://localhost:8180",
        help="Keycloak URL"
    )
    parser.add_argument(
        "--authz-url",
        default="http://localhost:8300",
        help="Authorization proxy URL"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run full test suite"
    )
    parser.add_argument(
        "--user",
        help="Username for single test"
    )
    parser.add_argument(
        "--password",
        help="Password for single test"
    )
    parser.add_argument(
        "--resource",
        help="Resource path to check"
    )
    parser.add_argument(
        "--action",
        default="read",
        choices=["read", "write", "delete"],
        help="Action to perform"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simulate authorization with detailed debug info"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run batch tests from scenarios"
    )
    parser.add_argument(
        "--scenarios",
        action="store_true",
        help="Show available test scenarios"
    )
    parser.add_argument(
        "--policy-info",
        action="store_true",
        help="Show policy implementation details"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug information for current user"
    )
    parser.add_argument(
        "--permissions",
        action="store_true",
        help="Show user permissions"
    )
    
    args = parser.parse_args()
    
    tester = AuthzTester(args.keycloak_url, args.authz_url)
    
    # Handle different modes
    if args.test:
        # Run full test suite
        success = tester.run_test_suite()
        sys.exit(0 if success else 1)
    
    elif args.scenarios:
        # Show test scenarios
        print("=" * 60)
        print("  Available Test Scenarios")
        print("=" * 60)
        print()
        
        scenarios = tester.get_test_scenarios()
        for scenario in scenarios.get('scenarios', []):
            print(f"\n📋 {scenario['name']} (User: {scenario['user']})")
            for test in scenario['tests']:
                expected_icon = "✓" if test['expected'] == "GRANT" else "✗"
                print(f"  {expected_icon} {test['action'].upper():6s} {test['resource_path']}")
        
        print(f"\n{scenarios.get('usage', '')}\n")
        sys.exit(0)
    
    elif args.policy_info:
        # Show policy information
        print("=" * 60)
        print("  Policy Implementation Details")
        print("=" * 60)
        print()
        
        info = tester.get_policy_info()
        print(json.dumps(info, indent=2))
        sys.exit(0)
    
    elif args.batch and args.user and args.password:
        # Run batch tests
        print(f"🔄 Running batch tests for user: {args.user}")
        print()
        
        token = tester.get_token(args.user, args.password)
        
        # Get scenarios for this user
        scenarios = tester.get_test_scenarios()
        user_scenarios = [s for s in scenarios.get('scenarios', []) if s['user'] == args.user]
        
        if user_scenarios:
            tests = []
            for scenario in user_scenarios:
                tests.extend([{"resource_path": t['resource_path'], "action": t['action']} 
                             for t in scenario['tests']])
            
            result = tester.batch_test(token, tests)
            
            print(f"📊 Results Summary:")
            print(f"   Total: {result.get('total_tests', 0)}")
            print(f"   ✅ Granted: {result['summary']['granted']}")
            print(f"   ❌ Denied: {result['summary']['denied']}")
            print(f"   ⚠️  Errors: {result['summary']['errors']}")
            print()
            
            print("📝 Detailed Results:")
            for r in result.get('results', []):
                icon = "✅" if r['decision'] == "GRANT" else "❌" if r['decision'] == "DENY" else "⚠️"
                print(f"   {icon} {r['action'].upper():6s} {r['resource_path']} - {r['decision']}")
        else:
            print(f"❌ No scenarios found for user: {args.user}")
            sys.exit(1)
        
        sys.exit(0)
    
    elif args.debug and args.user and args.password:
        # Show debug information
        print("=" * 60)
        print(f"  Debug Information for {args.user}")
        print("=" * 60)
        print()
        
        token = tester.get_token(args.user, args.password)
        debug_info = tester.get_debug_info(token)
        print(json.dumps(debug_info, indent=2))
        sys.exit(0)
    
    elif args.permissions and args.user and args.password:
        # Show permissions
        print(f"🔐 Permissions for {args.user}:")
        print()
        
        token = tester.get_token(args.user, args.password)
        perms = tester.get_permissions(token)
        
        print(f"👤 User: {perms.get('username')}")
        print(f"🏷️  Roles: {', '.join(perms.get('roles', []))}")
        print()
        print("📋 Permissions:")
        for perm, value in perms.get('permissions', {}).items():
            icon = "✓" if value else "✗"
            print(f"   {icon} {perm}")
        sys.exit(0)
    
    elif args.simulate and args.user and args.password and args.resource:
        # Simulate authorization with debug info
        print(f"🔍 Simulating authorization for {args.user}")
        print()
        
        token = tester.get_token(args.user, args.password)
        result = tester.simulate_authorization(token, args.resource, args.action)
        
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get('decision') == "GRANT" else 1)
    
    elif args.user and args.password and args.resource:
        # Single authorization check
        token = tester.get_token(args.user, args.password)
        result = tester.check_authorization(token, args.resource, args.action)
        
        if result['granted']:
            print(f"✅ Access GRANTED: {args.user} -> {args.resource} ({args.action})")
            if 'data' in result:
                print(json.dumps(result['data'], indent=2))
            sys.exit(0)
        else:
            print(f"❌ Access DENIED: {args.user} -> {args.resource} ({args.action})")
            if 'reason' in result:
                print(f"Reason: {result['reason']}")
            sys.exit(1)
    
    else:
        parser.print_help()
        print("\nExamples:")
        print("  # Run full test suite")
        print("  python test-authz.py --test")
        print()
        print("  # Show available scenarios")
        print("  python test-authz.py --scenarios")
        print()
        print("  # Single authorization check")
        print("  python test-authz.py --user user1 --password user1password --resource /user1/data/file.txt --action read")
        print()
        print("  # Simulate with debug info")
        print("  python test-authz.py --user user1 --password user1password --resource /common/data/file.txt --simulate")
        print()
        print("  # Run batch tests")
        print("  python test-authz.py --user user2 --password user2password --batch")
        print()
        print("  # Show user permissions")
        print("  python test-authz.py --user user1 --password user1password --permissions")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
