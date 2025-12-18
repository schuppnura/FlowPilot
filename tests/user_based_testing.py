#!/usr/bin/env python3
"""Test script for anti-spoofing guardrail validation

This script tests the anti-spoofing security guardrail in the AuthZ API
by attempting to execute workflow items with mismatched principal_sub.

Prerequisites:
- FlowPilot stack must be running (docker compose up)
- Test users must be provisioned in Keycloak and ***REMOVED***
- Agent delegation must be set up

Test scenarios:
1. Valid request - principal_sub matches workflow owner (should allow or ReBAC deny)
2. Spoofed principal - principal_sub differs from workflow owner (should deny with security.principal_spoof)
"""

import base64
import hashlib
import json
import secrets
import ssl
import tempfile
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import subprocess
import os
import requests

# Configuration
SERVICES_API_BASE = "http://localhost:8003"
AUTHZ_API_BASE = "http://localhost:8002"
KEYCLOAK_BASE_URL = "https://localhost:8443"
KEYCLOAK_REALM = "flowpilot"
KEYCLOAK_CLIENT_ID = "flowpilot-testing"
TEST_AGENT_SUB = "agent-runner"

# Disable SSL warnings for local testing
requests.packages.urllib3.disable_warnings()
ssl._create_default_https_context = ssl._create_unverified_context


# Global variable to store authorization code from callback
auth_code_result = {"code": None, "error": None}


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback"""
    
    def do_GET(self):
        global auth_code_result
        
        # Parse query parameters
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        # Debug: print what we received
        print(f"  Callback received: {self.path}")
        
        if 'code' in params:
            auth_code_result["code"] = params['code'][0]
            print(f"  ✓ Authorization code received")
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            message = """
            <html>
            <head><title>Login Successful</title></head>
            <body>
                <h1>✓ Login Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                <script>window.close();</script>
            </body>
            </html>
            """
            self.wfile.write(message.encode())
        elif 'error' in params:
            auth_code_result["error"] = params.get('error_description', [params['error'][0]])[0]
            print(f"  ✗ Error received: {auth_code_result['error']}")
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            message = f"""
            <html>
            <head><title>Login Failed</title></head>
            <body>
                <h1>✗ Login Failed</h1>
                <p>{auth_code_result['error']}</p>
                <p>You can close this window and return to the terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(message.encode())
        else:
            print(f"  ✗ Invalid callback (no code or error)")
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Invalid callback")
    
    def log_message(self, format, *args):
        # Enable minimal logging for debugging
        pass


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


def create_self_signed_cert():
    """Create a temporary self-signed certificate for the callback server"""
    temp_dir = tempfile.mkdtemp()
    cert_file = os.path.join(temp_dir, "cert.pem")
    key_file = os.path.join(temp_dir, "key.pem")
    
    # Generate self-signed certificate using openssl
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", key_file, "-out", cert_file,
        "-days", "1", "-nodes",
        "-subj", "/CN=localhost"
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return cert_file, key_file, temp_dir
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to create self-signed certificate: {e.stderr.decode()}")
    except FileNotFoundError:
        raise Exception("openssl not found. Please install openssl or use Chrome/Firefox instead of Safari.")


def get_user_token_via_browser() -> tuple[str, str, str]:
    """Get access token and user sub using browser-based OIDC login with PKCE"""
    global auth_code_result
    auth_code_result = {"code": None, "error": None}
    
    # Generate PKCE parameters
    code_verifier, code_challenge = generate_pkce_pair()
    
    # Start local callback server with HTTPS
    callback_port = 8765
    redirect_uri = f"https://localhost:{callback_port}/callback"
    
    print(f"\n  Creating temporary SSL certificate...")
    try:
        cert_file, key_file, temp_dir = create_self_signed_cert()
    except Exception as e:
        print(f"  Warning: {e}")
        print(f"  Falling back to HTTP (may not work with Safari)")
        redirect_uri = f"http://localhost:{callback_port}/callback"
        cert_file = None
    
    print(f"  Starting callback server on port {callback_port}...")
    try:
        server = HTTPServer(('localhost', callback_port), OAuthCallbackHandler)
        
        # Wrap with SSL if we have a certificate
        if cert_file:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_file, key_file)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            print(f"  ✓ HTTPS callback server started")
        else:
            print(f"  ✓ HTTP callback server started (fallback)")
    except OSError as e:
        raise Exception(f"Failed to start callback server on port {callback_port}. Is it already in use? {e}")
    
    # Use a more robust server approach - keep serving until we get the code
    def serve_until_code():
        while auth_code_result["code"] is None and auth_code_result["error"] is None:
            server.handle_request()
    
    server_thread = threading.Thread(target=serve_until_code, daemon=True)
    server_thread.start()
    
    # Build authorization URL
    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id": KEYCLOAK_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",  # Force re-authentication each time
    }
    auth_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth?{urllib.parse.urlencode(auth_params)}"
    
    print(f"  Opening browser for login...")
    print(f"  If browser doesn't open, visit: {auth_url}")
    
    # Give the server a moment to start
    import time
    time.sleep(0.5)
    
    webbrowser.open(auth_url)
    
    # Wait for callback (with timeout)
    print("  Waiting for login (this may take a minute)...")
    server_thread.join(timeout=120)
    
    # Clean up server
    try:
        server.server_close()
    except:
        pass
    
    # Clean up temp certificate files
    if cert_file:
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass
    
    if auth_code_result["error"]:
        raise Exception(f"Login failed: {auth_code_result['error']}")
    
    if not auth_code_result["code"]:
        raise Exception("Login timeout or no authorization code received. Did you complete the login in the browser?")
    
    # Exchange authorization code for token
    token_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    token_data = {
        "client_id": KEYCLOAK_CLIENT_ID,
        "grant_type": "authorization_code",
        "code": auth_code_result["code"],
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    
    try:
        response = requests.post(token_url, data=token_data, verify=False)
        response.raise_for_status()
        token_response = response.json()
        access_token = token_response["access_token"]
        
        # Decode token to get sub (user ID)
        payload_encoded = access_token.split('.')[1]
        # Add padding if needed
        payload_encoded += '=' * (4 - len(payload_encoded) % 4)
        payload_json = base64.b64decode(payload_encoded).decode('utf-8')
        payload = json.loads(payload_json)
        user_sub = payload['sub']
        username = payload.get('preferred_username', 'unknown')
        
        return access_token, user_sub, username
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to exchange code for token: {e}")


def create_trip_for_owner(owner_sub: str, access_token: str, template_id: str = "template_all_ok") -> dict:
    """Create a workflow owned by the specified user"""
    url = f"{SERVICES_API_BASE}/v1/workflows"
    payload = {
        "template_id": template_id,
        "principal_sub": owner_sub,  # API expects principal_sub, not owner_sub
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(url, json=payload, headers=headers, verify=False)
    
    if response.status_code != 200:
        try:
            error_detail = response.json()
            raise Exception(f"{response.status_code} {response.reason}: {error_detail}")
        except:
            raise Exception(f"{response.status_code} {response.reason}: {response.text}")
    
    return response.json()


def evaluate_auto_book(workflow_id: str, workflow_item_id: str, principal_sub: str, resource_properties: dict, access_token: str) -> dict:
    """Call AuthZ evaluate endpoint with specified principal_sub"""
    url = f"{AUTHZ_API_BASE}/v1/evaluate"
    payload = {
        "subject": {"type": "agent", "id": TEST_AGENT_SUB},
        "action": {"name": "auto-book"},
        "resource": {
            "type": "workflow",
            "id": workflow_id,
            "properties": {
                "domain": "flowpilot",
                "workflow_item_id": workflow_item_id,
                "workflow_item_kind": "flight",
                **resource_properties,
            },
        },
        "context": {"principal": {"type": "user", "id": principal_sub}},
        "options": {"dry_run": False, "explain": True},
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(url, json=payload, headers=headers, verify=False)
    response.raise_for_status()
    return response.json()


def run_tests():
    """Run anti-spoofing test scenarios"""
    print("\n" + "=" * 60)
    print("Anti-Spoofing Guardrail Test Suite")
    print("=" * 60)

    # Get token and user sub via browser login
    print(f"\n[Login] Starting browser-based authentication...")
    try:
        access_token, user_sub, username = get_user_token_via_browser()
        print(f"  ✓ Authenticated successfully")
        print(f"  Username: {username}")
        print(f"  User ID (sub): {user_sub}")
    except Exception as e:
        print(f"  ✗ Authentication failed: {e}")
        return

    # Setup: Create a workflow owned by the logged-in user
    print(f"\n[Setup] Creating trip owned by {user_sub}...")
    try:
        trip_result = create_trip_for_owner(owner_sub=user_sub, access_token=access_token)
        workflow_id = trip_result["workflow_id"]
        print(f"  Created trip: {workflow_id}")
    except Exception as e:
        print(f"  ✗ Failed to create workflow: {e}")
        return

    # Get the first item ID from the workflow
    # In a real test, you'd fetch this from the itinerary endpoint
    # For this test, we'll use a placeholder that matches template structure
    workflow_item_id = "i_placeholder"  # This would come from get_itinerary
    
    # Base resource properties for tests
    base_properties = {
        "planned_price": 1000,
        "departure_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
        "airline_risk_score": 3,
    }

    # Test 1: Valid request - principal matches owner
    print(f"\n[Test 1] Valid request - principal {user_sub} matches owner")
    try:
        result = evaluate_auto_book(
            workflow_id=workflow_id,
            workflow_item_id=workflow_item_id,
            principal_sub=user_sub,  # Matches owner
            resource_properties=base_properties,
            access_token=access_token,
        )
        print(f"  Decision: {result['decision']}")
        print(f"  Reason codes: {result.get('reason_codes', [])}")
        
        # Should NOT be denied due to spoofing
        if "security.principal_spoof" in result.get("reason_codes", []):
            print("  ✗ FAIL: Legitimate request was flagged as spoofing!")
        else:
            print("  ✓ PASS: No spoofing detected for legitimate request")
    except Exception as e:
        print(f"  ✗ FAIL: Exception occurred: {e}")

    # Test 2: Spoofed principal - simulate attacker trying to access this user's workflow
    # Generate a fake attacker sub
    attacker_sub = "fake-attacker-" + user_sub[:8]
    print(f"\n[Test 2] Spoofed principal - simulated attacker {attacker_sub} tries to access {user_sub}'s workflow")
    try:
        result = evaluate_auto_book(
            workflow_id=workflow_id,
            workflow_item_id=workflow_item_id,
            principal_sub=attacker_sub,  # Does NOT match owner
            resource_properties=base_properties,
            access_token=access_token,
        )
        print(f"  Decision: {result['decision']}")
        print(f"  Reason codes: {result.get('reason_codes', [])}")
        
        # MUST be denied with principal_spoof reason code
        if result["decision"] == "deny" and "security.principal_spoof" in result.get("reason_codes", []):
            # Check advice message
            advice = result.get("advice", [])
            spoof_advice = [a for a in advice if a.get("code") == "principal_spoof"]
            if spoof_advice:
                print(f"  Advice message: {spoof_advice[0].get('message', '')}")
            print("  ✓ PASS: Spoofing attempt correctly detected and denied")
        else:
            print(f"  ✗ FAIL: Expected deny with security.principal_spoof, got decision={result['decision']}, reason_codes={result.get('reason_codes', [])}")
    except Exception as e:
        print(f"  ✗ FAIL: Exception occurred: {e}")

    print("\n" + "=" * 60)
    print(f"Tests completed for user: {username} ({user_sub})")
    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("FlowPilot Anti-Spoofing Interactive Test")
    print("=" * 60)
    print("\nThis test will:")
    print("1. Open your browser to login with Keycloak")
    print("2. Create a workflow for that user")
    print("3. Test authorization with legitimate and spoofed principals")
    print("4. Wait for you to press Enter to test again with a different user")
    print("\nPress Ctrl+C to exit at any time.")
    
    while True:
        try:
            print("\n" + "=" * 60)
            response = input("\nPress Enter to start login (or type 'quit' to exit): ").strip()
            if response.lower() in ['quit', 'exit', 'q']:
                print("Exiting...")
                break
            
            run_tests()
            
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except requests.exceptions.ConnectionError:
            print("\nERROR: Could not connect to APIs. Is the stack running?")
            print("Run: docker compose up -d")
        except Exception as e:
            print(f"\nERROR: Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
