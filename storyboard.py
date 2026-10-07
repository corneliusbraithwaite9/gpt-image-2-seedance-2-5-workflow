#!/usr/bin/env python3
"""Storyboard to video: GPT Image 2 paints the keyframes, Seedance 2.5 animates them.

One plan file (JSON) lists the shots. For each shot the script generates its keyframes, uploads them
to get HTTPS media URLs, submits the video job, polls it and downloads the MP4. State is written after
every step, so a rerun resumes instead of paying twice. Standard library only (Python 3.8+).

    export MEDIA_API_KEY=...                      # MEDIA_BASE_URL defaults to https://argolink.io/v1
    python storyboard.py cases/01-product-orbit.json --dry-run
    python storyboard.py cases/01-product-orbit.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://argolink.io/v1"
IMAGE_PRICE = {"1K": 0.015, "2K": 0.015, "4K": 0.02}            # per GPT Image 2 image, checked 2026-10-07
VIDEO_PRICE = {"480p": 0.0874, "720p": 0.196, "1080p": 0.483}  # per Seedance 2.5 second, checked 2026-10-07
MODES = ("text", "first_frame", "first_last", "reference")
KEYFRAMES_PER_MODE = {"text": (0, 0), "first_frame": (1, 1), "first_last": (2, 2), "reference": (1, 30)}
MEDIA_URL_LIFETIME = 6 * 24 * 3600   # media_url is readable for 7 days; refresh a day early
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# Some CDNs refuse the default "Python-urllib" agent with a 403, so every request names the client.
USER_AGENT = "storyboard-pipeline/1.0"


class PipelineError(RuntimeError):
    pass


def image_tier(size: str) -> str:
    edge = max(int(v) for v in size.lower().split("x"))
    return "1K" if edge <= 1024 else "2K" if edge <= 2048 else "4K"


def validate(plan: dict) -> None:
    resolution = plan.get("resolution", "720p")
    if resolution not in VIDEO_PRICE:
        raise PipelineError(f"resolution must be one of {', '.join(VIDEO_PRICE)}")
    ids = set()
    for shot in plan["shots"]:
        sid, mode = shot["id"], shot.get("mode", "first_frame")
        if sid in ids:
            raise PipelineError(f"duplicate shot id {sid}")
        ids.add(sid)
        if mode not in MODES:
            raise PipelineError(f"{sid}: mode must be one of {', '.join(MODES)}")
        low, high = KEYFRAMES_PER_MODE[mode]
        if not low <= len(shot.get("keyframes", [])) <= high:
            raise PipelineError(f"{sid}: {mode} takes {low}-{high} keyframes")
        if not 4 <= int(shot.get("duration", 5)) <= 30:
            raise PipelineError(f"{sid}: duration must be 4-30 seconds")
        for position, frame in enumerate(shot.get("keyframes", []), 1):
            if frame.get("edit_of") and not 1 <= int(frame["edit_of"]) < position:
                raise PipelineError(f"{sid}: keyframe {position} can only edit an earlier keyframe")
            width, height = (int(v) for v in frame.get("size", "2048x1152").lower().split("x"))
            if not (300 <= min(width, height) and max(width, height) <= 6000 and 0.4 <= width / height <= 2.5):
                raise PipelineError(f"{sid}: keyframe {width}x{height} is outside Seedance 2.5's 300-6000 px, 0.4-2.5 ratio")


def estimate(plan: dict) -> list:
    """(shot id, image cost, video cost) per shot. Reference videos would add their seconds."""
    rate = VIDEO_PRICE[plan.get("resolution", "720p")]
    rows = []
    for shot in plan["shots"]:
        images = sum(IMAGE_PRICE[image_tier(k.get("size", "2048x1152"))] for k in shot.get("keyframes", []))
        rows.append((shot["id"], images, rate * int(shot.get("duration", 5))))
    return rows


def video_body(plan: dict, shot: dict, media_urls: list) -> dict:
    """The /videos/generations body for one shot. Frame modes on Seedance 2.5 take aspect_ratio
    'adaptive' only: the video follows the first frame's shape."""
    mode = shot.get("mode", "first_frame")
    body = {"model": plan.get("video_model", "seedance-2.5"), "prompt": shot["video_prompt"],
            "duration": int(shot.get("duration", 5)), "resolution": plan.get("resolution", "720p")}
    if mode in ("first_frame", "first_last"):
        body["aspect_ratio"] = "adaptive"
        body["start_image"] = {"url": media_urls[0]}
        if mode == "first_last":
            body["end_image"] = {"url": media_urls[1]}
    else:
        body["aspect_ratio"] = shot.get("aspect_ratio", plan.get("aspect_ratio", "16:9"))
        extra = shot.get("extra_references", {})
        images = [{"url": u} for u in media_urls] + [{"url": u} for u in extra.get("images", [])]
        if images:
            body["reference_images"] = images
        for kind in ("videos", "audios"):
            if extra.get(kind):
                body[f"reference_{kind}"] = [{"url": u} for u in extra[kind]]
    if "generate_audio" in shot:
        body["generate_audio"] = bool(shot["generate_audio"])
    return body


class Api:
    def __init__(self, api_key: str, base_url: str):
        self.api_key, self.base_url = api_key, base_url.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None, raw: bool = False, timeout: float = 120):
        request = urllib.request.Request(self.base_url + path, method=method,
                                         data=json.dumps(body).encode() if body is not None else None)
        request.add_header("Authorization", f"Bearer {self.api_key}")
        request.add_header("User-Agent", USER_AGENT)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as error:
            raise PipelineError(f"{method} {path} returned {error.code}: {error.read().decode(errors='replace')[:400]}") from None
        return payload if raw else json.loads(payload)

    def keyframe(self, model: str, prompt: str, size: str, quality: str) -> bytes:
        payload = self.call("POST", "/images/generations", {"model": model, "prompt": prompt, "size": size,
                                                            "quality": quality, "n": 1, "response_format": "b64_json"},
                            timeout=600)
        return base64.b64decode(payload["data"][0]["b64_json"])

    def keyframe_edit(self, model: str, prompt: str, size: str, quality: str, reference: bytes) -> bytes:
        """Edit an earlier keyframe (multipart, one image[] part) so two frames share subject and layout."""
        boundary = "storyboard-" + base64.b16encode(os.urandom(8)).decode()
        parts = [(name, str(value)) for name, value in (("model", model), ("prompt", prompt), ("size", size),
                                                        ("quality", quality), ("n", 1), ("response_format", "b64_json"))]
        body = bytearray()
        for name, value in parts:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        content_type = "image/png" if reference[:8] == PNG_MAGIC else "image/jpeg"
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="keyframe"\r\n'
                 f"Content-Type: {content_type}\r\n\r\n").encode() + reference + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(self.base_url + "/images/edits", data=bytes(body), method="POST")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        request.add_header("User-Agent", USER_AGENT)
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise PipelineError(f"POST /images/edits returned {error.code}: {error.read().decode(errors='replace')[:400]}") from None
        return base64.b64decode(payload["data"][0]["b64_json"])

    def upload(self, data: bytes, video_model: str) -> str:
        if data[:4] == b"RIFF":
            raise PipelineError("Seedance takes JPEG or PNG frames; convert the WebP keyframe first")
        if len(data) > 20 * 1024 * 1024:
            raise PipelineError("keyframe is over Seedance's 20 MiB image limit; use a smaller size or JPEG")
        content_type = "image/png" if data[:8] == PNG_MAGIC else "image/jpeg"
        ticket = self.call("POST", "/media/uploads", {"model": video_model, "type": "image",
                                                      "content_type": content_type, "size_bytes": len(data)})
        put = urllib.request.Request(ticket["upload_url"], data=data, method="PUT")
        put.add_header("Content-Type", content_type)   # must match the ticket exactly
        put.add_header("User-Agent", USER_AGENT)
        urllib.request.urlopen(put, timeout=300).close()
        return ticket["media_url"]


def run(plan: dict, plan_name: str, api: Api, out_dir: str, poll_every: float = 10, max_wait: float = 3600,
        only: set | None = None, retry_failed: bool = False, log=print) -> dict:
    """Make every shot of the plan at plan["resolution"]. Keyframes and their uploads are kept per shot,
    video jobs per shot and resolution, so changing the resolution re-renders without new keyframes."""
    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, "state.json")
    state = {"plan": plan_name, "shots": {}}
    if os.path.exists(state_path):
        with open(state_path) as handle:
            state = json.load(handle)

    def save():
        with open(state_path, "w") as handle:
            json.dump(state, handle, indent=2)

    image_model = plan.get("image_model", "gpt-image-2")
    video_model = plan.get("video_model", "seedance-2.5")
    resolution = plan.get("resolution", "720p")
    for shot in plan["shots"]:
        sid = shot["id"]
        if only and sid not in only:
            continue
        record = state["shots"].setdefault(sid, {"keyframes": [], "media": [], "renders": {}})
        render = record.setdefault("renders", {}).setdefault(resolution, {})
        if render.get("status") == "done" and os.path.exists(render.get("video", "")):
            log(f"{sid}: {resolution} done earlier, skipping")
            continue
        if render.get("status") in ("failed", "expired"):
            retryable = render["status"] == "expired" or (render.get("error") or {}).get("retryable")
            if not (retryable or retry_failed):
                log(f"{sid}: failed earlier and the API says a plain retry cannot succeed; "
                    f"change the plan and pass --retry-failed")
                continue

        if "request_id" not in render or render.get("status") in ("failed", "expired"):
            for index, frame in enumerate(shot.get("keyframes", [])):
                if index < len(record["keyframes"]):
                    continue                      # made on an earlier run: not paid again
                prompt = "\n\n".join(p for p in (plan.get("style", ""), frame["prompt"]) if p)
                size, quality = frame.get("size", "2048x1152"), frame.get("quality", "high")
                if frame.get("edit_of"):          # 1-based index of an earlier keyframe of this shot
                    with open(record["keyframes"][int(frame["edit_of"]) - 1], "rb") as handle:
                        data = api.keyframe_edit(image_model, prompt, size, quality, handle.read())
                else:
                    data = api.keyframe(image_model, prompt, size, quality)
                extension = "png" if data[:8] == PNG_MAGIC else "jpg"
                path = os.path.join(out_dir, f"{sid}-k{index + 1}.{extension}")
                with open(path, "wb") as handle:
                    handle.write(data)
                record["keyframes"].append(path)
                record["media"] = []
                save()
                log(f"{sid}: keyframe {index + 1} -> {path}")
            fresh = record["media"] and time.time() - record.get("uploaded_at", 0) < MEDIA_URL_LIFETIME
            if not fresh:
                record["media"] = []
                for path in record["keyframes"]:
                    with open(path, "rb") as handle:
                        record["media"].append(api.upload(handle.read(), video_model))
                record["uploaded_at"] = time.time()
                save()
            job = api.call("POST", "/videos/generations", video_body(plan, shot, record["media"]))
            render.clear()
            render.update(request_id=job["request_id"], status="pending")
            save()
            log(f"{sid}: submitted {job['request_id']} at {resolution}")

        deadline = time.monotonic() + max_wait
        while True:
            status = api.call("GET", f"/videos/{render['request_id']}")
            render["status"] = status.get("status")
            if render["status"] == "done":
                render["usage"] = status.get("usage", {})
                break
            if render["status"] in ("failed", "expired"):
                render["error"] = status.get("error")
                save()
                log(f"{sid}: {render['status']} {json.dumps(status.get('error'))}")
                break
            if time.monotonic() > deadline:
                save()
                log(f"{sid}: still pending after {max_wait:.0f}s; run again later to keep polling")
                break
            log(f"{sid}: pending {status.get('progress', 0)}%")
            time.sleep(poll_every)
        if render["status"] != "done":
            continue
        video_path = os.path.join(out_dir, f"{sid}-{resolution}.mp4")
        with open(video_path, "wb") as handle:
            handle.write(api.call("GET", f"/videos/{render['request_id']}/content", raw=True, timeout=600))
        billed = render["usage"].get("billed_seconds", 0)
        render.update(video=video_path, video_cost=round(billed * VIDEO_PRICE[resolution], 4))
        save()
        log(f"{sid}: {video_path} ({billed} s billed, ${render['video_cost']:.3f})")
    return state


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="GPT Image 2 keyframes -> Seedance 2.5 clips.")
    parser.add_argument("plan", help="plan file, e.g. cases/01-product-orbit.json")
    parser.add_argument("--out", help="output folder (default runs/<plan name>)")
    parser.add_argument("--only", help="comma-separated shot ids")
    parser.add_argument("--resolution", choices=sorted(VIDEO_PRICE), help="override the plan, e.g. re-render a 480p draft at 720p")
    parser.add_argument("--retry-failed", action="store_true", help="resubmit failed shots even if not retryable")
    parser.add_argument("--dry-run", action="store_true", help="validate and print the estimate, send nothing")
    args = parser.parse_args(argv)

    with open(args.plan, encoding="utf-8") as handle:
        plan = json.load(handle)
    if args.resolution:
        plan["resolution"] = args.resolution
    validate(plan)
    name = os.path.splitext(os.path.basename(args.plan))[0]
    total = 0.0
    for sid, images, video in estimate(plan):
        total += images + video
        print(f"{sid:<16} keyframes ${images:.3f}  video ${video:.3f}")
    total = round(total + 1e-9, 2)   # round half up, so 1.975 prints as 1.98
    print(f"estimate ${total:.2f} at {plan.get('resolution', '720p')}; keyframes made on an earlier run are not paid again, "
          f"reference videos would add their seconds")
    if args.dry_run:
        return 0
    api_key = os.environ.get("MEDIA_API_KEY")
    if not api_key:
        raise SystemExit("set MEDIA_API_KEY")
    api = Api(api_key, os.environ.get("MEDIA_BASE_URL") or DEFAULT_BASE_URL)
    try:
        state = run(plan, name, api, args.out or os.path.join("runs", name),
                    only=set(args.only.split(",")) if args.only else None, retry_failed=args.retry_failed)
    except PipelineError as error:
        raise SystemExit(f"error: {error}")
    resolution = plan.get("resolution", "720p")
    failed = [sid for sid, record in state["shots"].items()
              if record.get("renders", {}).get(resolution, {}).get("status") != "done"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
