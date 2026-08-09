"""Records a real run to a time-indexed tape the browser can replay.

Enabled only when DEMO_RECORD=1. Writes after every /api/* response so a crashed
run still leaves a usable partial tape.

normalise_path must stay byte-identical in behaviour to normalisePath() in
frontend/src/demo/tape.js. If one changes, change the other.
"""

import json
import os
import re
import time

SCHEMA_VERSION = 1

# A path segment is an ID if it is a UUID, a demo id, an all-digit id, or a long
# opaque token. Recorder and replayer share this rule, so a false positive is
# symmetric — but two distinct endpoints collapsing to one key would silently
# serve the wrong response, so the opaque rule requires at least one digit.
# Without that, "/api/simulation/suggest-followups" (17 chars) becomes
# "/api/simulation/:id".
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_DEMO = re.compile(r"^demo[_-]")
_DIGITS = re.compile(r"^\d+$")
_OPAQUE = re.compile(r"^(?=.*\d)[A-Za-z0-9_-]{16,}$")


def normalise_path(path: str) -> str:
    path = path.split("?", 1)[0]
    segments = path.split("/")
    out = []
    for seg in segments:
        if seg and (
            _UUID.match(seg) or _DEMO.match(seg) or _DIGITS.match(seg) or _OPAQUE.match(seg)
        ):
            out.append(":id")
        else:
            out.append(seg)
    return "/".join(out)


def init_recorder(app, out_path: str, scenario: str) -> None:
    start = time.monotonic()
    entries: list[dict] = []

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    def flush() -> None:
        tmp = out_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(
                {
                    "schema_version": SCHEMA_VERSION,
                    "scenario": scenario,
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "entries": entries,
                },
                fh,
            )
        os.replace(tmp, out_path)

    @app.after_request
    def _record(response):
        from flask import request

        if not request.path.startswith("/api/"):
            return response
        if "json" not in (response.content_type or ""):
            return response

        try:
            body = json.loads(response.get_data(as_text=True))
        except (ValueError, UnicodeDecodeError):
            return response

        entries.append(
            {
                "t_ms": int((time.monotonic() - start) * 1000),
                "method": request.method,
                "path": normalise_path(request.path),
                "status": response.status_code,
                "body": body,
            }
        )
        flush()
        return response

    flush()
