import http.client
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class ReviewUnavailable(Exception):
    """Review did not answer in time, or answered with something other than its own JSON."""


class ReviewRefused(Exception):
    """Review answered and said no, with a message meant for the founder."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def http_transport(method, url, body, timeout):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    try:
        # ReviewClient only accepts http(s) base URLs, so urlopen never sees file:// or a custom scheme.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            return response.status, _parse(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _parse(error.read())


def _parse(raw):
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


class ReviewClient:
    """Every call has a timeout. Calls that wait on Jev or Chef get the slow one."""

    def __init__(self, base_url, timeout, slow_timeout, transport=None):
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("REVIEW_URL must start with http:// or https://")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.slow_timeout = slow_timeout
        self.transport = transport or http_transport

    def call(self, method, path, body=None, slow=False):
        try:
            status, data = self.transport(method, self.base_url + path, body, self.slow_timeout if slow else self.timeout)
        except (OSError, http.client.HTTPException) as error:
            log.warning("review unreachable: %s %s: %s", method, path, error)
            raise ReviewUnavailable() from error
        if status < 300:
            return data
        message = data.get("error") if isinstance(data, dict) else None
        if message and (status < 500 or status == 503):
            raise ReviewRefused(status, message)
        log.warning("review failed: %s %s answered %s", method, path, status)
        raise ReviewUnavailable()

    def round(self, idea_id, revision_ids, founder_text, tone, level):
        body = {"idea_id": idea_id, "revision_ids": revision_ids, "founder_text": founder_text, "tone": tone, "level": level}
        return self.call("POST", "/rounds", body, slow=True)

    def state(self, idea_id, revision_ids, evidence, level):
        body = {"revision_ids": revision_ids, "evidence": evidence, "level": level}
        return self.call("POST", "/ideas/%d/state" % idea_id, body)

    def sessions(self, idea_id):
        return self.call("GET", "/ideas/%d/sessions" % idea_id)["sessions"]

    def gate(self, idea_id, head_id, founder_text, level):
        body = {"idea_id": idea_id, "head_id": head_id, "founder_text": founder_text, "level": level}
        return self.call("POST", "/gates", body, slow=True)

    def serve(self, revision_ids, founder_text):
        return self.call("POST", "/serve", {"revision_ids": revision_ids, "founder_text": founder_text}, slow=True)

    def pack(self, revision_ids, founder_text, verified):
        body = {"revision_ids": revision_ids, "founder_text": founder_text, "verified": verified}
        return self.call("POST", "/packs", body, slow=True)

    def facts(self, one_liner, story):
        return self.call("POST", "/facts", {"one_liner": one_liner, "story": story}, slow=True)

    def forget(self, idea_id, revision_ids):
        self.call("DELETE", "/ideas/%d?revisions=%s" % (idea_id, ",".join(str(rid) for rid in revision_ids)))

    def summaries(self, ideas):
        return self.call("POST", "/summaries", {"ideas": ideas})["ideas"]
