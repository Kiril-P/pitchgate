from flask import request

METHODS = "GET, POST, DELETE, OPTIONS"
HEADERS = "Content-Type, X-Organizer-Key"
MAX_AGE = "600"


def allow_origin(app, origin):
    """The static UI lives on another origin, so the browser only lets it read our responses
    when they name its origin. Any other origin gets no CORS headers and the browser blocks it."""

    @app.after_request
    def add_headers(response):
        response.vary.add("Origin")
        if origin and request.headers.get("Origin") == origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = METHODS
            response.headers["Access-Control-Allow-Headers"] = HEADERS
            response.headers["Access-Control-Max-Age"] = MAX_AGE
        return response
