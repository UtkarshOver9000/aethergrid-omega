"""Combines viewer_template.html + viewer.js + the 4 scenario JSON files
into one self-contained artifact-ready HTML file (no external requests
except Google Fonts, which the Artifact CSP allows)."""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent


def build(out_path: str = "viz/dist/index.html") -> None:
    template = (HERE / "viewer_template.html").read_text(encoding="utf-8")
    viewer_js = (HERE / "viewer.js").read_text(encoding="utf-8")

    html = template.replace(
        '<script src="viewer.js"></script>',
        f"<script>\n{viewer_js}\n</script>",
    )

    for key in ["normal", "heatwave", "high_ev", "outage"]:
        data = (HERE / "data" / f"{key}.json").read_text(encoding="utf-8")
        placeholder = f"__DATA_{key.upper()}__"
        assert placeholder in html, f"missing placeholder {placeholder}"
        html = html.replace(placeholder, data)

    out = HERE.parent / out_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    build()
