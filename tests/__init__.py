# Test-suite-wide environment: keep the suite hermetic.
# - Disable the on-disk HTTP cache so mocked responses never write to
#   the developer's .cache/ directory.
# - Remove the per-run HTTP request budget (tests count mocked calls).
# - Empty the blocked-domain list and disable the Wayback fallback so
#   tests exercise the direct-fetch path; Wayback tests re-enable both.
import os

os.environ.setdefault("HTTP_CACHE_DISABLE", "1")
os.environ.setdefault("MAX_REQUESTS_PER_RUN", "0")
os.environ.setdefault("BLOCKED_DOMAINS", "")
os.environ.setdefault("WAYBACK_FALLBACK", "0")
