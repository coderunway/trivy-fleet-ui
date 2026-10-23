#Purpose: Lightweight HTTP API that parses report JSON files and triggers on-demand scans via the Docker socket.

import os
import glob
import json
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

BASE_DIR = os.environ.get("BASE_DIR", "/volume1/docker/trivy")
HOST_CACHE_DIR = os.environ.get("HOST_CACHE_DIR", f"{BASE_DIR}/cache")
HOST_REPORTS_DIR = os.environ.get("HOST_REPORTS_DIR", f"{BASE_DIR}/reports")

SCAN_STATE = {
    "status": "idle",
    "message": "Ready",
    "current": 0,
    "total": 0,
    "target": ""
}

def run_scan_worker(images):
    global SCAN_STATE
    SCAN_STATE["status"] = "scanning"
    SCAN_STATE["total"] = len(images)
    SCAN_STATE["current"] = 0

    for idx, img in enumerate(images):
        SCAN_STATE["current"] = idx + 1
        SCAN_STATE["target"] = img
        SCAN_STATE["message"] = f"Scanning ({idx + 1}/{len(images)}): {img}..."

        safe_name = img.replace("/", "__").replace(":", "--")
        tmp_path = f"/reports/{safe_name}.tmp"
        final_path = f"/reports/{safe_name}.json"

        cmd = [
            "docker", "run", "--rm",
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-v", f"{HOST_CACHE_DIR}:/root/.cache/",
            "-v", f"{HOST_REPORTS_DIR}:/reports",
            "aquasec/trivy:latest",
            "image",
            "--timeout", "30m",
            "--skip-db-update",
            "--quiet",
            "--format", "json",
            "--output", tmp_path,
            img
        ]

        try:
            subprocess.run(cmd, check=True, timeout=1800)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                os.replace(tmp_path, final_path)
        except Exception as e:
            print(f"Error scanning {img}: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    SCAN_STATE["status"] = "completed"
    SCAN_STATE["message"] = f"Scan complete! Scanned {len(images)} container(s)."


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/app/static", **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/host-images":
            try:
                out = subprocess.check_output(
                    ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                    stderr=subprocess.DEVNULL
                ).decode("utf-8")
                raw = [line.strip() for line in out.splitlines() if line.strip() and "<none>" not in line]
                images = sorted(list(set(raw)))
            except Exception:
                images = []

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(images).encode("utf-8"))
            return

        if parsed.path == "/api/scan-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(SCAN_STATE).encode("utf-8"))
            return

        if parsed.path == "/api/data":
            files = glob.glob("/reports/*.json")
            vulnerabilities = []
            images_set = set()

            for fpath in files:
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    raw_name = os.path.basename(fpath)[:-5]
                    img_name = raw_name.replace("__", "/").replace("--", ":")
                    images_set.add(img_name)

                    results = data.get("Results") or []
                    for res in results:
                        target = res.get("Target", "General")
                        vulns = res.get("Vulnerabilities") or []
                        for v in vulns:
                            vulnerabilities.append({
                                "image": img_name,
                                "target": target,
                                "severity": v.get("Severity", "UNKNOWN"),
                                "cve": v.get("VulnerabilityID", "N/A"),
                                "pkg": v.get("PkgName", "N/A"),
                                "installed": v.get("InstalledVersion", "N/A"),
                                "fixed": v.get("FixedVersion") or "None",
                                "title": v.get("Title") or v.get("Description") or "No description provided",
                                "url": v.get("PrimaryURL") or f"https://nvd.nist.gov/vuln/detail/{v.get('VulnerabilityID', '')}"
                            })
                except Exception:
                    continue

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "images": sorted(list(images_set)),
                "vulnerabilities": vulnerabilities
            }).encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/scan-start":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            images = data.get("images", [])

            if SCAN_STATE["status"] != "scanning" and images:
                t = threading.Thread(target=run_scan_worker, args=(images,))
                t.daemon = True
                t.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), DashboardHandler)
    print("Fleet Dashboard running on port 8080...")
    server.serve_forever()