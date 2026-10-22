"""Turn a pytest log into GitHub Actions annotations, so failures are readable via the
check-runs API (job logs are not always reachable from where this repo is maintained)."""
import sys
from pathlib import Path

log = Path(sys.argv[1]).read_text(errors="replace")
blocks = []
if "= FAILURES =" in log:
    body = log.split("= FAILURES =", 1)[1]
    body = body.split("short test summary", 1)[0]
    blocks = [b for b in body.split("\n___") if b.strip()]
summary = log.split("short test summary info", 1)[1] if "short test summary info" in log else log[-3000:]


def enc(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


print(f"::error title=pytest summary::{enc(summary.strip()[:3800])}")
for b in blocks[:6]:
    print(f"::error title=pytest failure::{enc(b.strip()[:3800])}")
