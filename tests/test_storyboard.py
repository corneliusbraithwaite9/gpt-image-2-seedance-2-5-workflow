"""Offline tests: a fake API answers every call, so no key, upload or video is real."""
import base64
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import storyboard  # noqa: E402

PNG = storyboard.PNG_MAGIC + b"fake-keyframe"
CASES = os.path.join(os.path.dirname(__file__), "..", "cases")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeApi:
    """Routes urlopen calls the way the media endpoints answer them."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def __call__(self, request, timeout=None):
        method, url = request.get_method(), request.full_url
        body = request.data
        assert request.get_header("User-agent") == storyboard.USER_AGENT, url
        self.calls.append((method, url, body))
        if url.endswith("/images/generations") or url.endswith("/images/edits"):
            return FakeResponse(json.dumps({"data": [{"b64_json": base64.b64encode(PNG).decode()}]}).encode())
        if url.endswith("/media/uploads"):
            n = sum(1 for c in self.calls if c[1].endswith("/media/uploads"))
            return FakeResponse(json.dumps({"upload_url": f"https://storage.test/put/{n}",
                                            "media_url": f"https://media.test/{n}.png"}).encode())
        if url.startswith("https://storage.test/"):
            return FakeResponse(b"")
        if url.endswith("/videos/generations"):
            return FakeResponse(json.dumps({"request_id": "req-1"}).encode())
        if url.endswith("/content"):
            return FakeResponse(b"MP4")
        if "/videos/req-1" in url:
            return FakeResponse(json.dumps(self.statuses.pop(0)).encode())
        raise AssertionError(url)

    def bodies(self, suffix):
        return [json.loads(body) for method, url, body in self.calls if url.endswith(suffix) and method == "POST"]


def load(name):
    with open(os.path.join(CASES, name)) as handle:
        return json.load(handle)


DONE = {"status": "done", "progress": 100, "usage": {"output_seconds": 8, "reference_video_seconds": 0, "billed_seconds": 8}}


@pytest.fixture
def api(monkeypatch):
    def make(statuses):
        fake = FakeApi(statuses)
        monkeypatch.setattr(storyboard.urllib.request, "urlopen", fake)
        monkeypatch.setattr(storyboard.time, "sleep", lambda s: None)
        return fake
    return make


def test_every_case_file_is_valid():
    for name in sorted(os.listdir(CASES)):
        storyboard.validate(load(name))


def test_first_frame_shot_runs_end_to_end(api, tmp_path):
    fake = api([{"status": "pending", "progress": 40}, DONE])
    state = storyboard.run(load("01-product-orbit.json"), "orbit", storyboard.Api("k", "https://api.test/v1"),
                           str(tmp_path), log=lambda *a: None)
    (ticket,) = fake.bodies("/media/uploads")
    assert ticket == {"model": "seedance-2.5", "type": "image", "content_type": "image/png", "size_bytes": len(PNG)}
    (job,) = fake.bodies("/videos/generations")
    assert job["start_image"] == {"url": "https://media.test/1.png"}
    assert job["aspect_ratio"] == "adaptive" and job["duration"] == 8 and job["resolution"] == "720p"
    render = state["shots"]["orbit"]["renders"]["720p"]
    assert render["status"] == "done" and render["video_cost"] == 1.568
    assert (tmp_path / "orbit-720p.mp4").read_bytes() == b"MP4"


def test_last_frame_is_an_edit_of_the_first(api, tmp_path):
    fake = api([DONE])
    storyboard.run(load("02-day-to-night.json"), "street", storyboard.Api("k", "https://api.test/v1"),
                   str(tmp_path), log=lambda *a: None)
    edits = [c for c in fake.calls if c[1].endswith("/images/edits")]
    assert len(edits) == 1 and b'name="image[]"' in edits[0][2] and PNG in edits[0][2]
    (job,) = fake.bodies("/videos/generations")
    assert job["start_image"]["url"] != job["end_image"]["url"]


def test_reference_shot_sends_images_and_keeps_the_ratio(api, tmp_path):
    fake = api([DONE])
    storyboard.run(load("06-app-demo.json"), "app", storyboard.Api("k", "https://api.test/v1"), str(tmp_path),
                   log=lambda *a: None)
    (job,) = fake.bodies("/videos/generations")
    assert job["aspect_ratio"] == "9:16" and len(job["reference_images"]) == 3 and "start_image" not in job


def test_a_rerun_polls_the_pending_job_instead_of_paying_again(api, tmp_path):
    plan = load("01-product-orbit.json")
    first = api([{"status": "pending", "progress": 10}])
    storyboard.run(plan, "orbit", storyboard.Api("k", "https://api.test/v1"), str(tmp_path), max_wait=0,
                   log=lambda *a: None)
    assert len(first.bodies("/videos/generations")) == 1
    second = api([DONE])
    storyboard.run(plan, "orbit", storyboard.Api("k", "https://api.test/v1"), str(tmp_path), log=lambda *a: None)
    assert second.bodies("/videos/generations") == [] and second.bodies("/images/generations") == []
    assert (tmp_path / "orbit-720p.mp4").exists()


def test_a_new_resolution_reuses_the_keyframes(api, tmp_path):
    plan = load("07-anime-opening-draft.json")
    api([DONE, DONE, DONE])
    storyboard.run(plan, "op", storyboard.Api("k", "https://api.test/v1"), str(tmp_path), log=lambda *a: None)
    plan["resolution"] = "720p"
    final = api([DONE, DONE, DONE])
    storyboard.run(plan, "op", storyboard.Api("k", "https://api.test/v1"), str(tmp_path), log=lambda *a: None)
    assert final.bodies("/images/generations") == []
    assert [job["resolution"] for job in final.bodies("/videos/generations")] == ["720p"] * 3
    assert (tmp_path / "op-1-480p.mp4").exists() and (tmp_path / "op-1-720p.mp4").exists()


def test_a_non_retryable_failure_is_not_resubmitted(api, tmp_path):
    plan = load("01-product-orbit.json")
    failed = {"status": "failed", "error": {"code": "content_policy_violation", "retryable": False, "field": "prompt"}}
    api([failed])
    storyboard.run(plan, "orbit", storyboard.Api("k", "https://api.test/v1"), str(tmp_path), log=lambda *a: None)
    again = api([])
    storyboard.run(plan, "orbit", storyboard.Api("k", "https://api.test/v1"), str(tmp_path), log=lambda *a: None)
    assert again.calls == []


@pytest.mark.parametrize("change, message", [
    ({"duration": 31}, "duration"),
    ({"mode": "first_last"}, "keyframes"),
    ({"keyframes": [{"prompt": "x", "size": "1024x300"}]}, "ratio"),
])
def test_validation_catches_what_the_api_would_refuse(change, message):
    plan = load("01-product-orbit.json")
    plan["shots"][0].update(change)
    with pytest.raises(storyboard.PipelineError, match=message):
        storyboard.validate(plan)
