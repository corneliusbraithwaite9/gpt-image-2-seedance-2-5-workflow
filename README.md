# GPT Image 2 + Seedance 2.5 workflow — storyboard to video in eight runnable cases

GPT Image 2 decides what the frame looks like; Seedance 2.5 decides how it moves. This repo is the bridge: a pipeline script that paints keyframes, uploads them, submits the video job, polls it and downloads the clip, plus eight case files with the exact prompts, settings and cost of each.

Both models are on [ArgoLink](https://argolink.io/gh-gpt-image-2-seedance-2-5-workflow) behind one key: [GPT Image 2](https://argolink.io/gh-gpt-image-2-seedance-2-5-workflow-gpt-image-2) at $0.015 per image (1K/2K, $0.02 at 4K) and Seedance 2.5 at $0.0874/s (480p), $0.196/s (720p) and $0.483/s (1080p), which the model page puts at 15% below the official BytePlus list price.

[Pipeline](#the-pipeline) · [Quick start](#quick-start) · [Cases](#cases) · [Techniques](#techniques-that-matter) · [Costs](#costs) · [FAQ](#faq)

<sub>Last checked: 2026-10-07. Endpoints, limits and prices come from the model pages and API docs linked above.</sub>

## The pipeline

| Step | Call | What happens | Cost |
|---|---|---|---|
| 1. Keyframe | `POST /v1/images/generations` (`gpt-image-2`) | paints the frame from your prompt; `size` in pixels, ratio also in words | $0.015 per image up to 2K |
| 1b. Matching frame | `POST /v1/images/edits` | for an end frame: edits the first keyframe so subject and layout stay put | $0.015 |
| 2. Upload | `POST /v1/media/uploads` → `PUT upload_url` | Seedance only takes HTTPS media, so each keyframe gets a `media_url` (valid 7 days) | free |
| 3. Submit | `POST /v1/videos/generations` (`seedance-2.5`) | first frame, first + last frame, or reference images; returns `request_id` | per output second |
| 4. Poll | `GET /v1/videos/{request_id}` | `pending` (with `progress` 0–99) until `done`, `failed` or `expired` | — |
| 5. Download | `GET /v1/videos/{request_id}/content` | the MP4; `409` before it's ready, `424` for a failed job | — |

`storyboard.py` does all of it and writes `runs/<case>/state.json` after every step, so a rerun picks up a pending job instead of paying for a new one. Failed and expired jobs are not billed; a failure the API marks as not retryable is left alone until you change the plan and pass `--retry-failed`.

## Quick start

```bash
git clone https://github.com/corneliusbraithwaite9/gpt-image-2-seedance-2-5-workflow
cd gpt-image-2-seedance-2-5-workflow
export MEDIA_API_KEY=your-key                   # one key for both models; MEDIA_BASE_URL to override

python storyboard.py cases/01-product-orbit.json --dry-run    # prints $1.58
python storyboard.py cases/01-product-orbit.json              # keyframe, upload, video, MP4 in runs/
```

A plan file is plain JSON: a `style` line shared by every keyframe, a `resolution`, and one entry per shot with its `mode` (`first_frame`, `first_last`, `reference` or `text`), `keyframes` (prompt, `size`, optional `edit_of`), `video_prompt` and `duration` (4–30 s). Copy a case and edit it.

## Cases

No sample renders are committed: every case runs with `python storyboard.py cases/<file>`, and the cost column is what it bills at today's prices.

| # | Case | Technique | Clip | Cost |
|---|---|---|---|---:|
| 1 | [Product hero orbit](./cases/01-product-orbit.json) | first frame | 8 s, 720p | $1.58 |
| 2 | [Day into night, same street](./cases/02-day-to-night.json) | first + last frame, last one edited from the first | 10 s, 720p | $1.99 |
| 3 | [Nine-panel grid trailer](./cases/03-grid-trailer.json) | one 3×3 storyboard sheet as reference | 15 s, 720p | $2.96 |
| 4 | [Turnaround to dance](./cases/04-turnaround-to-motion.json) | character sheet as reference, 9:16 | 10 s, 720p | $1.98 |
| 5 | [Ramen macro](./cases/05-food-macro.json) | first frame at the top tier | 6 s, 1080p | $2.91 |
| 6 | [App demo](./cases/06-app-demo.json) | three generated UI screens as references | 10 s, 720p | $2.01 |
| 7 | [Anime opening draft](./cases/07-anime-opening-draft.json) | three first-frame shots, drafted at 480p | 3 × 5 s, 480p | $1.36 |
| 8 | [Virtual staging](./cases/08-virtual-staging.json) | empty room → furnished room as first + last | 8 s, 720p | $1.60 |

### 1. Product hero orbit

Keyframe, `2048x1152`, high: *"A brushed-steel wireless earbud case, lid half open, standing on a low black acrylic plinth, centered with empty space on both sides. 16:9 composition."* (after the shared style line: matte black backdrop, soft key light from the upper left, thin rim light).

Video, `first_frame`, 8 s: *"The camera orbits slowly a quarter turn to the right around the earbud case, keeping it centered. The lid opens the rest of the way at the halfway point and a soft blue status light comes on. Reflections slide across the steel. Quiet ambient hum, one soft click when the lid stops."*

Leave empty space around the product in the still: an orbit needs room, and in frame modes the clip keeps the keyframe's shape.

### 2. Day into night on one street

Keyframe 1: a cobbled street at midday with cafe tables, flower boxes and a bicycle against a lamppost. Keyframe 2 is an **edit of keyframe 1**: *"The same street, same framing and every object in the same place, now at blue hour: warm lights on in the windows and the lamppost, cafe tables lit by string lights, wet cobbles reflecting the lights."*

Video, `first_last`, 10 s: *"Time-lapse from midday to blue hour on a fixed camera. Shadows stretch and cross the street, the sky cools, windows and the lamppost light up one by one…"*

Two independent generations would move the bicycle and the tables; editing the first frame keeps them, so Seedance only has to animate the light.

### 3. Nine-panel grid trailer

One `2048x1152` keyframe: *"A storyboard sheet: a 3 by 3 grid of nine equal cinematic panels, thin white gutters, no text or numbers. A lone lighthouse keeper on a stormy island. Panels in reading order: 1 wide shot of the lighthouse in a storm; 2 the keeper climbing the spiral stairs with a lantern; … 9 dawn, calm sea, the boat moored below the lighthouse."*

Video, `reference`, 15 s, 16:9: *"Follow the nine panels of @Image 1 in order as nine quick shots with hard cuts, keeping the keeper, the lighthouse and the teal and amber palette consistent…"*

The grid is planning, not a frame: it goes in `reference_images`, so it never appears in the output. Expect to steer: some panels merge or get skipped, and 15 s across nine shots is fast; cut the grid to four or six panels for longer shots.

### 4. From a turnaround to motion

Keyframe, `2048x878` (21:9): a turnaround sheet of a street dancer, front / three-quarter / side / back, with the outfit spelled out (orange windbreaker, black cargo pants, white high-tops, silver headphones).

Video, `reference`, 10 s, 9:16: *"The dancer from @Image 1, same face and outfit, performs a confident hip-hop routine on a night city rooftop: a few groove steps, a spin, then freezes and points at the camera…"*

A reference image steers identity without pinning the first frame, so the clip can have its own framing (9:16 here) while the character stays on model.

### 5. Ramen macro at 1080p

Keyframe, `2048x1152`: a low-angle bowl of tonkotsu ramen with chashu, a halved soft egg, scallions and nori. Video, `first_frame`, 6 s at 1080p: *"Slow push-in toward the egg as chopsticks lift a strand of noodles that drips broth back into the bowl. Steam curls through the light. Gentle bubbling and a soft slurp."*

1080p costs about 2.5 times 720p ($0.483 vs $0.196 per second); short, detail-heavy shots like food and product macro are where it pays.

### 6. App demo from generated screens

Three `1152x2048` keyframes of one habit-tracking app (habit list, calendar heatmap, streak celebration), all sharing a style line with the accent color `#2E7D5B`. Video, `reference`, 10 s, 9:16: *"A hand holds a phone… it starts on the screen in @Image 1, swipes to @Image 2, then taps to reveal @Image 3 as confetti bursts…"*

Name each reference in the order you want it to appear; the images are numbered in the order they are sent.

### 7. Three-shot anime opening, drafted cheap

Three `first_frame` shots of the same girl (rooftop at sunset, running beside a train, a close-up with paper lanterns), 5 s each at 480p: $1.36 for the whole draft. When the cut works:

```bash
python storyboard.py cases/07-anime-opening-draft.json --resolution 720p   # same keyframes, new clips: $2.94
ffmpeg -f concat -safe 0 -i <(for f in runs/07-anime-opening-draft/op-*-720p.mp4; do echo "file '$PWD/$f'"; done) -c copy opening.mp4
```

Keyframes and uploads are kept per shot and clips per resolution, so the re-render pays only for video seconds.

### 8. Virtual staging

Keyframe 1: an empty living room with oak floors, a window and a fireplace. Keyframe 2, an edit of 1: the same room furnished in Scandinavian style. Video, `first_last`, 8 s: *"Slow dolly forward into the room while the furniture appears piece by piece: the rug unrolls, the sofa and table settle into place, plants and the lamp fade in…"*

Generated furniture in a real listing must be disclosed as virtual staging wherever you publish it.

## Techniques that matter

- **Frame modes are `adaptive`.** On Seedance 2.5, `start_image` and `start_image` + `end_image` take `aspect_ratio: "adaptive"` only: the clip follows the first frame. Decide the shape when you paint the keyframe. Reference and text shots take 21:9, 16:9, 4:3, 1:1, 3:4 or 9:16.
- **Make end frames as edits.** For `first_last`, generate frame 2 with `/images/edits` from frame 1 (`"edit_of": 1` in a plan) and say what must not move.
- **Frames vs references.** A frame is pinned in the clip; a reference only steers subject, style or layout. Frames can't be mixed with reference lists in one request.
- **Name references in the prompt.** `@Image 1`, `@Image 2`… in the order sent; Seedance 2.5 takes up to 30 images, 10 videos and 10 audio clips per request (50 in total).
- **Keyframe limits.** Seedance 2.5 reads JPEG or PNG up to 20 MiB, 300–6000 px per side, width/height between 0.4 and 2.5. Every size in the cases fits; `storyboard.py` checks before spending.
- **Write motion, not looks, in the video prompt.** The keyframe already carries subject, light and palette; the video prompt should say camera move, action, timing and sound.
- **Draft at 480p.** It's 45% of the 720p rate. Re-render the shots you keep with `--resolution`.

## Costs

| Seedance 2.5, per second | 480p | 720p | 1080p |
|---|---:|---:|---:|
| **[ArgoLink](https://argolink.io/en/models/seedance-2.5)** | **$0.0874** | **$0.196** | **$0.483** |
| Official list price, as stated on that page | $0.1028 | $0.2311 | $0.5686 |
| [fal.ai](https://fal.ai/models/bytedance/seedance-2.5/text-to-video) ("roughly", token-based) | $0.2205 | $0.473 | $1.164 |

<sub>Checked 2026-10-07. Billed seconds = output seconds + seconds of any reference videos; reference images and audio, uploads and failed or expired jobs cost nothing. GPT Image 2 keyframes: $0.015 each up to 2K by the returned image's longest edge, $0.02 above.</sub>

A 60-second spot built from twelve 5-second first-frame shots costs 12 × $0.015 + 60 × $0.196 = **$11.94** at 720p, or 12 × $0.015 + 60 × $0.0874 = **$5.42** as a 480p draft.

## FAQ

**Can I pass the GPT Image 2 output URL straight to Seedance?**
The image endpoint can return a temporary URL, but Seedance needs a public HTTPS URL that is still readable when the job starts. Uploading the bytes through `/v1/media/uploads` gives a `media_url` that lasts seven days, which is what the script does.

**Why was my first-frame request rejected with an aspect-ratio error?**
On Seedance 2.5, frame modes accept only `adaptive`. Leave `aspect_ratio` out or send `adaptive`, and paint the keyframe in the shape you want.

**How long does a clip take?**
Several minutes is normal, and longer when the queue is busy. Poll every 10–15 seconds; `progress` and `estimated_seconds_remaining` show how far along it is.

**Do I need GPT Image 2 for this, or can I use another image model?**
Any image works as long as it ends up as an HTTPS JPEG or PNG within Seedance's limits. The plan's `image_model` can be `gpt-image-2.5-flare` or `gpt-image-2.5-sunburst`, which take the same fields.

**Can Seedance 2.5 add the soundtrack?**
Yes, clips come with generated audio by default. Set `"generate_audio": false` on a shot for a silent clip you score yourself.

## Tests

```bash
pip install pytest
pytest tests/
```

A fake API answers every call, so the tests need no key and spend nothing.

## License

MIT. Independent example code; not affiliated with OpenAI or ByteDance.
