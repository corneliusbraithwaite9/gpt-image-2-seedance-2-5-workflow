# Storyboard to video

## Stage 1: still

Use a precise subject, composition, lighting, and aspect-ratio phrase. For GPT Image 2, request a pixel `size` such as `1024x1024` or `2048x1152`; put the desired ratio in the prompt. The image model page defines the live size and billing rules.

## Stage 2: motion

```text
Subject continuity: keep the subject, wardrobe, and layout from image 1.
Camera: ...
Action: ...
Timing: beginning ... middle ... ending ...
Sound: ...
Avoid: ...
```

Set `duration` from 4 to 30, choose 480p, 720p, or 1080p, and make one request. Store the returned request ID before polling.

## Failure boundaries

A rejected or failed job is not a reason to alter the prompt and submit automatically. Record the error and decide whether the user wants a new shot. A transport timeout is ambiguous; inspect status before any new chargeable request.
