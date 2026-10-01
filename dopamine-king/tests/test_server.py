import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from dopamine_king.lab import sample_size_per_arm
from dopamine_king.server import handle_api, make_handler, serve

BRIEF = {"brand": "Zorvia", "topic": "running shoes", "audience": "beginner runners", "cohort": "sport"}


class HandleApiTests(unittest.TestCase):
    def test_health(self):
        status, payload = handle_api("GET", "/api/health", None, {"writer": "offline"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["writer"], "offline")

    def test_score(self):
        status, payload = handle_api("POST", "/api/score", {"text": "7 mistakes every beginner runner makes"})
        self.assertEqual(status, 200)
        self.assertGreater(payload["total"], 40)
        self.assertEqual(handle_api("POST", "/api/score", {"text": 5})[0], 400)
        self.assertEqual(handle_api("POST", "/api/score", {})[0], 400)

    def test_compare(self):
        status, payload = handle_api("POST", "/api/compare", {"a": "Why most dashboards lie to you", "b": "Our update"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["winner"], "a")
        self.assertEqual(handle_api("POST", "/api/compare", {"a": "x"})[0], 400)

    def test_lab_ab(self):
        status, payload = handle_api("POST", "/api/lab/ab", {"a": [100, 1000], "b": [130, 1000]})
        self.assertEqual(status, 200)
        self.assertAlmostEqual(payload["frequentist"]["p_value"], 0.0355, places=3)
        self.assertEqual(payload["sample_size_per_arm_for_20pct_lift"], sample_size_per_arm(0.10, 0.2))
        self.assertEqual(handle_api("POST", "/api/lab/ab", {"a": [1, 0], "b": [1, 10]})[0], 400)
        self.assertEqual(handle_api("POST", "/api/lab/ab", {"a": "x"})[0], 400)

    def test_guru(self):
        status, payload = handle_api("POST", "/api/guru", {"brief": BRIEF, "options": {"weeks": 2, "posts_per_week": 3}})
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["calendar"]), 6)
        self.assertEqual(handle_api("POST", "/api/guru", {"brief": {"brand": "x"}})[0], 400)
        self.assertEqual(handle_api("POST", "/api/guru", {})[0], 400)

    def test_routing_errors(self):
        self.assertEqual(handle_api("GET", "/api/nope", None)[0], 405)
        self.assertEqual(handle_api("POST", "/api/nope", {})[0], 404)
        self.assertEqual(handle_api("POST", "/other", {})[0], 404)
        self.assertEqual(handle_api("POST", "/api/health", {})[0], 404)

    def test_forge_validation_errors(self):
        self.assertEqual(handle_api("POST", "/api/forge", {"brief": BRIEF, "writer": "gpt"})[0], 400)
        self.assertEqual(handle_api("POST", "/api/forge", {"brief": BRIEF, "formats": "linkedin_post"})[0], 400)
        self.assertEqual(handle_api("POST", "/api/forge", {})[0], 400)


class SocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = make_handler({"writer": "offline"}, lambda: b"<!doctype html><title>page</title>")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers, err.read()

    def test_page_and_health(self):
        status, headers, body = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>page</title>", body)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, _, body = self.call("GET", "/api/health")
        self.assertEqual(json.loads(body)["ok"], True)

    def test_post_score_and_bad_json(self):
        status, _, body = self.call("POST", "/api/score", {"text": "Why most dashboards lie to you"})
        self.assertEqual(status, 200)
        self.assertGreater(json.loads(body)["total"], 30)
        self.assertEqual(self.call("POST", "/api/score", raw=b"{not json")[0], 400)
        self.assertEqual(self.call("POST", "/api/score", raw=b"[1,2]")[0], 400)
        self.assertEqual(self.call("GET", "/nope")[0], 404)

    def test_oversized_body_is_rejected(self):
        status, _, _ = self.call("POST", "/api/score", raw=b"x", headers={"Content-Length": "5000000"})
        self.assertEqual(status, 413)


class ServeGuardTests(unittest.TestCase):
    def test_refuses_public_bind_without_flag(self):
        with self.assertRaises(SystemExit):
            serve("0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()
