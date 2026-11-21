import re
import urllib.error


def verdict(revision_id, label):
    return {"revision_id": revision_id, "label": label, "rule": "below_cutoff", "explanation": "", "focus": None}


class StubReview:
    """Stands in for the review service behind the HTTP transport: canned answers per route,
    `replies` to override one route with (status, body), and `down` to refuse every connection."""

    def __init__(self):
        self.calls = []
        self.down = False
        self.slow = set()
        self.label = "PARTIAL"
        self.step = "open"
        self.sessions = 1
        self.pack = None
        self.facts = {"facts": [], "searches": []}
        self.replies = {}

    def __call__(self, method, url, body, timeout):
        path = "/" + url.split("://", 1)[1].split("/", 1)[1]
        self.calls.append({"method": method, "path": path, "body": body, "timeout": timeout})
        if self.down:
            raise urllib.error.URLError("connection refused")
        route = re.sub(r"/\d+", "/<id>", path.split("?")[0])
        if route in self.slow:
            raise TimeoutError("timed out")
        if (method, route) in self.replies:
            return self.replies[(method, route)]
        return 200, self.answer(method, route, body)

    def answer(self, method, route, body):
        if route == "/rounds":
            return {"verdict": verdict(body["revision_ids"][-1], self.label), "step": self.step, "paused": None}
        if route == "/ideas/<id>/state":
            ids = body["revision_ids"]
            return {
                "sessions": self.sessions,
                "step": self.step,
                "verdicts": {str(rid): verdict(rid, self.label) for rid in ids},
                "chef": {str(rid): {"turn": {"body": "Raw.", "question": "Who paid you?"}} for rid in ids},
                "homework": None,
                "pack": self.pack,
                "gate": {"session": self.sessions, "logs": body["evidence"], "ready": False, "latest": None},
                "answers_left": 5 - (len(ids) - 1),
                "session_answers": 5,
                "servable": False,
                "serve_min_logs": 3,
                "starter": body["level"] in ("new", "idea"),
                "starter_gate": False,
                "jev_used": len(ids),
                "jev_budget": 15,
            }
        if route == "/ideas/<id>/sessions":
            return {"sessions": self.sessions}
        if route == "/gates":
            return {"label": "PASSED"}
        if route == "/serve":
            return {"pitch": "We help students sell textbooks.", "next_steps": []}
        if route == "/packs":
            return {}
        if route == "/facts":
            return self.facts
        if route == "/summaries":
            return {"ideas": {str(item["id"]): {"labels": [self.label] * len(item["revision_ids"]), "gates_passed": 0} for item in body["ideas"]}}
        if method == "DELETE":
            return None
        raise AssertionError("StubReview has no route for %s %s" % (method, route))

    def paths(self):
        return [call["method"] + " " + call["path"] for call in self.calls]


PACK = {
    "problem": "Students lose money selling textbooks back to the campus store.",
    "first_customer": "BBA students who sell books at the end of each term",
    "assumptions": ["Buyers will pay a small listing fee"],
    "mvp": [{"feature": "List a book", "why": "Marta waited three weeks to sell hers"}],
    "not_yet": ["Payments in the app"],
    "user_stories": ["As a seller, I want to list a book, so that a buyer finds it before term"],
    "screens": ["Listing form"],
    "data_model": [{"table": "books", "fields": "id, title, course, price"}],
    "stack": "Flask and SQLite",
    "tasks": ["Create the Flask app", "Add the books table"],
    "claude_prompt": "Build a small Flask app where students list textbooks for next term's courses.",
}
