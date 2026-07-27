"""Small JSON-over-HTTP helper with retries and a polite user agent.

Both upstreams (the npm registry and deps.dev) are public and unauthenticated,
but they are also somebody else's infrastructure. Every request identifies
itself, backs off on failure, and gives up rather than hammering.
"""

import gzip
import json
import random
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "great-consolidation/1.0 "
    "(+https://github.com/shwetankg07/great-consolidation) "
    "daily npm ecosystem metrics"
)

RETRY_STATUS = {429, 500, 502, 503, 504}


class Unavailable(Exception):
    """Upstream did not return usable data after all retries."""


def get_json(url, accept="application/json", attempts=4, timeout=45):
    """GET a URL and parse JSON, retrying transient failures.

    Returns None for a 404, which callers treat as "this package or version is
    not known upstream" rather than as an error worth failing the run over.
    """
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": accept,
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    payload = gzip.decompress(payload)
                return json.loads(payload)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code not in RETRY_STATUS:
                raise
            last = error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last = error

        if attempt < attempts - 1:
            # Exponential backoff with jitter so parallel workers do not
            # retry in lockstep after a shared upstream hiccup.
            time.sleep(2**attempt + random.random())

    raise Unavailable(f"{url}: {last}")
