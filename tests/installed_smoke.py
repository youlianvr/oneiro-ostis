"""Run with the isolated installed-wheel interpreter, not pytest's source path.

All state stays under project .runtime/. No provider, graph, account or desktop
operation is performed. The child owns exactly one HTTP socket and is stopped.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / ".runtime" / "foundation-smoke-data"

# The application import and resources resolve from the installed distribution.
SERVER = """
import threading
import sys
import uvicorn
from oneiro.web import create_app
server = uvicorn.Server(uvicorn.Config(create_app(), host='127.0.0.1', port=9899,
                                      access_log=False, log_level='warning'))
def stop():
    sys.stdin.readline()
    server.should_exit = True
threading.Thread(target=stop, daemon=True).start()
server.run()
"""


class InstalledSmoke(unittest.TestCase):
    def test_installed_distribution_and_real_http(self):
        import oneiro
        import configparser  # stdlib, not the checkout compatibility module
        self.assertNotIn(str(PROJECT / "python"), str(oneiro.__file__))
        self.assertTrue(configparser.__file__)
        with socket.socket() as probe:
            probe.settimeout(0.2)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", 9899)), 0, "9899 is already owned; do not touch its process")
        DATA.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["ONEIRO_SETTINGS_FILE"] = str(DATA / "settings.json")
        env["ONEIRO_DATA_DIR"] = str(DATA / "owner")
        env.pop("ONEIRO_WEB_HOST", None)
        env.pop("ONEIRO_WEB_PORT", None)
        process = subprocess.Popen([sys.executable, "-c", SERVER], cwd=Path.home(),
                                   env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self.fail("Installed server exited: " + process.communicate()[1])
                try:
                    health = self.request("/api/health")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                self.fail("Server did not become reachable")
            self.assertFalse(json.loads(health[1])["assistant_ready"])
            for path in ("/", "/settings", "/setup", "/oneiro/", "/app.js", "/style.css"):
                headers, body = self.request(path)
                self.assertTrue(body)
                self.assertIsNone(headers.get("Access-Control-Allow-Origin"))
            token = json.loads(self.request("/api/session")[1])["csrf"]
            request = urllib.request.Request("http://127.0.0.1:9899/api/settings",
                data=json.dumps({"graph.port": 8090, "world.seed": "installed-smoke"}).encode(),
                headers={"Content-Type": "application/json", "X-Oneiro-CSRF": token})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/graph")
            self.assertEqual(error.exception.code, 503)
            error.exception.close()
            self.assertFalse(json.loads(self.request("/api/status")[1])["ready"])
            # Actual installed CLI reports missing integration without claiming ready.
            doctor = subprocess.run([sys.executable, "-m", "oneiro", "doctor"],
                                    cwd=Path.home(), env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(doctor.returncode, 1)
            self.assertFalse(json.loads(doctor.stdout)["ready"])
            conflict = subprocess.run([sys.executable, "-m", "oneiro", "serve"],
                                      cwd=Path.home(), env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(conflict.returncode, 2)
            self.assertIsNotNone(process.stdin)
            process.stdin.write("stop\n")
            process.stdin.flush()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout, "")
            print("LIVE_SMOKE: wheel outside workspace; 9899 routes/settings/503/doctor/port conflict; graceful stop OK")
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)
        with socket.socket() as probe:
            probe.settimeout(0.2)
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", 9899)), 0)
        # OS lease released on graceful close, persistent marker retained.
        from oneiro.ownership import FileLease
        with FileLease(DATA / "owner" / "runtime.lock"):
            pass
        print("CLEANUP: child exited; 9899 closed; ownership released; smoke files retained")

    @staticmethod
    def request(path):
        with urllib.request.urlopen("http://127.0.0.1:9899" + path, timeout=3) as response:
            return response.headers, response.read()


if __name__ == "__main__":
    unittest.main()
