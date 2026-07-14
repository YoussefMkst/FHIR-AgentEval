"""
Bake the per-experiment dashboard JSONs into a single self-contained index.html.

Reads results/dashboard/exp*.json, inlines them into template.html (replacing
the __DATA__ placeholder), and writes dashboard/index.html. The result needs no
server or fetch — open locally or host on GitHub Pages as-is.

Rerun whenever results/dashboard/exp*.json change.
"""

import json
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
DATA_DIR = DASHBOARD_DIR.parent / "results" / "dashboard"


def main() -> None:
    exp_files = sorted(DATA_DIR.glob("exp*.json"))
    if not exp_files:
        raise SystemExit(f"No exp*.json found in {DATA_DIR}. Run build_dashboard_summaries.py first.")

    data = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in exp_files}
    template = (DASHBOARD_DIR / "template.html").read_text(encoding="utf-8")
    html = template.replace("__DATA__", json.dumps(data, ensure_ascii=False))

    out = DASHBOARD_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB) from {len(exp_files)} experiments: {[f.stem for f in exp_files]}")


if __name__ == "__main__":
    main()
