# Two-to-three-minute viewer/SDK-first demo

This walkthrough uses deterministic repository fixtures and makes no operational claim. After one
successful bootstrap, run `make portfolio-demo` for the script. Use `make demo` for the containerized
local-release stack.

## Storyboard (target: 2:30)

|      Time | Show                                                           | Say / verify                                                                                  |
| --------: | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 0:00–0:20 | Safety banner and release evidence index                       | Educational decision support; gaps remain visible as `not_run`.                               |
| 0:20–1:15 | Viewer session library and synchronized stereo/sensor timeline | One canonical nanosecond clock drives media and sensor windows; gaps and drift are surfaced.  |
| 1:15–1:50 | Create an interval annotation and aligned export               | Mutations are versioned/idempotent; exported evidence retains the selected time range.        |
| 1:50–2:15 | Run the printed SDK request / inspect manifest                 | The UI consumes the same public `/v1` contract available to TypeScript and Python clients.    |
| 2:15–2:30 | Evidence index and limitations                                 | Retained viewer measurements are fixture-scoped; ML and broad RAG gates are explicitly unrun. |

## Capture checklist

- Record a release build or clearly label the dev build.
- Keep terminal/API logs visible only when useful; do not expose tokens or local paths.
- Show the safety classification at the start and end.
- Record exact commit, browser/version, OS/hardware, and capture date in `CAPTURE.md`.
- Do not call the storyboard or SVG a recorded video. A binary video is intentionally not committed.

The [architecture SVG](architecture.svg) is suitable for a slide or README. `CAPTURE.md` is a
truthful capture record: until a human records and reviews a video, its status remains `not_recorded`.
