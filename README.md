# GPT Image 2 → Seedance 2.5 Workflow

A storyboard-first production workflow for generating a still with **GPT Image 2** and animating it with **Seedance 2.5** through Argolink. The repository focuses on shot continuity, prompt handoff, and async video lifecycle rather than a provider comparison.

[Seedance 2.5 model page →](https://argolink.io/gh-gpt-image-2-seedance-2-5-workflow) · [GPT Image 2 model page](https://argolink.io/gh-gpt-image-2-seedance-2-5-workflow-gpt-image-2) · [Argolink API docs →](https://argolink.io/gh-unified-api-docs)

## Pipeline

1. Generate a storyboard image with `POST /v1/images/generations` and `model: "gpt-image-2"`.
2. If a reference image must be edited, use `POST /v1/images/edits` with one to sixteen `image[]` parts.
3. Pass the resulting HTTPS image URL to Seedance 2.5 with `POST /v1/videos/generations`.
4. Poll the request ID and download after `done`; do not resubmit when a poll or network call times out.

## Seedance 2.5 facts

- 4–30 seconds, 480p/720p/1080p, one output per request.
- Up to 30 images, 10 videos, and 10 audios; reference videos add their seconds to billed seconds.
- Video edits accept 4–30 second source video.

## Prompt handoff

Keep the storyboard prompt about composition and subject identity. Keep the video prompt about motion, camera, timing, and sound. See [`docs/pipeline.md`](docs/pipeline.md) for the handoff template.
