"""Small stdlib-only HTTP probe used before project dependencies are available."""

import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=2) as response:
        if not 200 <= response.status < 300:
            raise SystemExit(1)
except Exception:
    raise SystemExit(1)
