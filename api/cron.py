from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys
import os

# Add parent directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        job_type = query.get('type', ['short'])[0]
        
        cfg = main.load_config()
        
        try:
            if job_type == 'long':
                result = main.cmd_run_surah(cfg)
            else:
                result = main.cmd_run(cfg)
                
            status_code = 200 if result == 0 else 500
            response_msg = b"Success" if result == 0 else b"Failed during execution"
        except Exception as exc:
            status_code = 500
            response_msg = f"Server Error: {exc}".encode('utf-8')
            
        self.send_response(status_code)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(response_msg)
