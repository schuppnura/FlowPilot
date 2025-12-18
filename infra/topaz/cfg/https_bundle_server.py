#!/usr/bin/env python3
"""HTTPS server for serving ***REMOVED*** policy bundles with TLS."""

import http.server
import ssl
import sys
from pathlib import Path

PORT = 8888
CERT_FILE = Path(__file__).parent.parent / "certs" / "cert.pem"
KEY_FILE = Path(__file__).parent.parent / "certs" / "key.pem"

def main():
    # Change to the directory containing bundles
    bundle_dir = Path(__file__).parent
    print(f"Serving bundles from: {bundle_dir}")
    print(f"Using certificate: {CERT_FILE}")
    print(f"Using key: {KEY_FILE}")
    
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        print(f"ERROR: TLS certificate or key not found!")
        print(f"  cert: {CERT_FILE}")
        print(f"  key: {KEY_FILE}")
        sys.exit(1)
    
    # Change to bundle directory
    import os
    os.chdir(str(bundle_dir))
    print(f"Current directory: {Path.cwd()}")
    
    # Create HTTPS server
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(('0.0.0.0', PORT), handler)
    
    # Wrap with SSL
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(CERT_FILE), keyfile=str(KEY_FILE))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    print(f"HTTPS server running on https://0.0.0.0:{PORT}")
    print(f"Bundle URL: https://host.docker.internal:{PORT}/bundle/flowpilot-policy.tar.gz")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()

if __name__ == "__main__":
    main()
