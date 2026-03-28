#!/usr/bin/env python3
"""Generate and open the asset preview HTML from search results."""

import argparse
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description="Generate asset preview HTML")
    parser.add_argument("--context", required=True, help="Search context description")
    parser.add_argument("--project", required=True, help="Absolute path to user's project")
    parser.add_argument(
        "--assets",
        help="Asset JSON array as string. If omitted, reads from stdin.",
    )
    args = parser.parse_args()

    if args.assets:
        assets_json = args.assets
    else:
        assets_json = sys.stdin.read()

    # Validate JSON
    try:
        json.loads(assets_json)
    except json.JSONDecodeError as e:
        print(f"Error: invalid asset JSON: {e}", file=sys.stderr)
        sys.exit(1)

    session_id = secrets.token_hex(4)

    # Read template relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(
        script_dir, "..", "skills", "phaser-asset-finder", "assets", "asset-preview.html"
    )
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("__ASSET_DATA_PLACEHOLDER__", assets_json)
    html = html.replace("__SEARCH_CONTEXT_PLACEHOLDER__", args.context)
    html = html.replace("__PROJECT_PATH_PLACEHOLDER__", args.project)
    html = html.replace("__SESSION_ID_PLACEHOLDER__", session_id)

    # Write to temp directory
    out_path = os.path.join(tempfile.gettempdir(), f"asset-preview-{session_id}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Open in default browser
    system = platform.system()
    if system == "Windows":
        os.startfile(out_path)
    elif system == "Darwin":
        subprocess.run(["open", out_path])
    else:
        subprocess.run(["xdg-open", out_path])

    # Output session info for Claude to use
    print(json.dumps({"session_id": session_id, "preview_path": out_path}))


if __name__ == "__main__":
    main()
