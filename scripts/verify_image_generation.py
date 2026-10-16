"""Live acceptance: download and decode both text-to-image and image-to-image.

Run with CHATGPT2API_AUTH_KEY set; output files contain test images only.
"""
import argparse
import base64
import io
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="data/acceptance")
    args = parser.parse_args()
    key = os.environ["CHATGPT2API_AUTH_KEY"]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    reference = io.BytesIO()
    Image.new("RGB", (256, 256), "red").save(reference, format="PNG")
    tests = [
        ("text-to-image", "/v1/images/generations", {"prompt": "Generate an image of a blue ceramic cup on a plain white table."}),
        ("image-to-image", "/v1/images/edits", {
            "prompt": "Change the red background in the reference image to blue.",
            "images": [{"image_url": "data:image/png;base64," + base64.b64encode(reference.getvalue()).decode()}],
        }),
    ]
    report = []
    for name, endpoint, body in tests:
        try:
            body.update(model="gpt-image-2", n=1, response_format="url")
            req = Request(args.url.rstrip("/") + endpoint, data=json.dumps(body).encode(), headers={
                "Authorization": "Bearer " + key, "Content-Type": "application/json",
            })
            with urlopen(req, timeout=1500) as response:
                result = json.load(response)
            items = result.get("data") or []
            if not items:
                raise ValueError("no returned images")
            for index, item in enumerate(items):
                if item.get("url"):
                    # Do not forward the application key to external image hosts.
                    with urlopen(item["url"], timeout=120) as response:
                        payload = response.read()
                else:
                    payload = base64.b64decode(item["b64_json"], validate=True)
                with Image.open(io.BytesIO(payload)) as image:
                    image.load()
                    width, height = image.size
                    image.save(output / f"{name}-{index}.png", format="PNG")
                report.append({"test": name, "index": index, "ok": True,
                               "bytes": len(payload), "width": width, "height": height})
        except Exception as exc:
            report.append({"test": name, "ok": False, "error": str(exc)})
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if any(not item["ok"] for item in report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
