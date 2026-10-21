"""Read-only, explicitly allowlisted assets for the synthetic material demo."""
from __future__ import annotations

from pathlib import Path
import re

from flask import Response, abort, send_file


ROOT = Path(__file__).resolve().parents[1] / "tools" / "material_demo"
FILES = {
    "index.html": "text/html",
    "demo.css": "text/css",
    "demo.js": "text/javascript",
    **{f"assets/{name}.svg": "image/svg+xml" for name in (
        "cherry", "flower", "mint-cat", "orange-bear", "rocket", "source-sheet", "sunshine",
    )},
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; connect-src 'none'; font-src 'self'; "
       "object-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'")


def asset_response(filename: str):
    """Never serve the demo README, arbitrary project files, or linked targets."""
    mimetype = FILES.get(filename)
    if mimetype is None:
        abort(404)
    path = ROOT / filename
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            abort(404)
    if not path.is_file():
        abort(404)
    if filename == "index.html":
        # A static mode marker switches prototype navigation to real application
        # links. No application token, credential or task state enters the demo.
        html = re.sub(r"(<html\b)", r'\1 data-hosted="true"', path.read_text("utf-8"),
                      count=1, flags=re.IGNORECASE)
        return Response(html, mimetype=mimetype)
    return send_file(path, mimetype=mimetype, conditional=True)
