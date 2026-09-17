# Proto-Mind — challenge launch kit

## Product description

**Proto-Mind: a floating AI workspace for your Mac.**

Bring a browser page into a task, work by text or voice, keep results beside the
conversation, and carry project decisions into the next chat. Hover over the
cube for a quick look; pin it when you want to work. Independent task conversations
retain their own model, context and execution.

GPT-6 Astra can execute tasks through the user's Codex subscription. The voice
channel uses GPT Live 1 with a separate command dispatcher; API/local routes have
different tool capabilities. Describe these accurately in the submission.

## Product Hunt copy — saved for the scheduled launch

**Name:** Proto-Mind

**Tagline (36 characters):** A floating AI workspace for your Mac

**Description (230 characters; limit 260):**

Bring AI chats, websites and documents into one Mac workspace. Run tasks in
parallel, choose models and accounts per chat, and fold everything into a cube
while work continues. Includes voice control and editable long-term memory.

**Website:** https://virencore.com/

**Saved topics:** Mac, Productivity, Artificial Intelligence.

**Saved shoutouts:** OpenAI Codex CLI, ChatGPT by OpenAI, OpenAI. Each has a saved
explanation of its actual contribution; all three were checked on the product page.

### Maker's first comment

Hi Product Hunt! I built Proto-Mind because I wanted a Mac workspace where AI
tasks, browser pages and files could stay together without taking over my desktop.

The small cube is the part I use most: hover to check on your workspace, click to
keep it open, and move away to get your screen back. Tasks continue in the
background. You can detach the companion windows, run separate AI conversations
in parallel, and choose a different model or ChatGPT account for each chat.

For the GPT-6 Astra Challenge, the demo shows Astra reading a sample client brief
and saving a proposal while the workspace is folded away. Astra runs through
Codex using your own ChatGPT account. The app also has editable long-term memory
and voice control; live voice uses a separate OpenAI API connection and billing.

Proto-Mind is currently an early beta for Apple Silicon Macs running macOS 14 or
later. The beta is not Apple-notarized, and the download page explains installation
and its requirements. API and local-model connections have different capabilities
from the Codex task runner.

I would love feedback on the cube and the companion windows: where would this
workspace fit into your day, and what still gets in your way?

## Recorded media

- Final English demonstration: `../../хакатон/монтаж/Proto-Mind-demo-en.mp4`.
- Runtime: 1:29.5; 2560×1440; English narration and optional English subtitles.
- Subtitle source: `../../хакатон/монтаж/Proto-Mind-demo-en.srt`.
- Assembly and source evidence: `../../хакатон/монтаж/README.md`.

The recording shows real cube/window interactions and a real Northstar task
producing `proposal.md`. Waiting is shortened and labelled in the video.
The practical run reported missing saved preferences: do not describe this video
as proof that project-memory recall succeeded. The final narration was edited
accordingly. Memory remains a product capability, separate from evidence of that
specific run. A second-Mac trial is still outstanding.

Published unlisted on VIREN CORP: https://www.youtube.com/watch?v=nCSf04Z40yk.
The official video readback confirms processing succeeded, unlisted visibility,
embedding enabled, English captions and a custom thumbnail. Playback was checked
inside the actual Product Hunt embed. The synthetic narration is disclosed.

Three real frames were extracted from the recordings, with unrelated desktop
details cropped out: workspace, floating windows and the saved proposal. Product
Hunt uses 1270×760 gallery images and a 240×240 product icon; the website uses
separate 1800-pixel JPEGs. Sources, crops and outputs are recorded under
`../../хакатон/скриншоты/README.md`.

## Publication receipts — verified 17 September 2026

### Website and installer

- Live bilingual website: https://virencore.com/ and https://virencore.com/ru/.
- Install instructions and current beta: https://virencore.com/download/.
- Website commit: `c802d4d`; Cloudflare Pages production deployment:
  `94909ca3-3da6-44a3-bd04-721222d0ca9c` at `2026-09-17T17:17:38.808872Z`.
  Live checks returned HTTP 200 and matching local hashes for all 16 served files;
  the missing route returned 404 and the www redirect retained path/query.
- Public prerelease: https://github.com/iskillcapped-gif/proto-mind/releases/tag/v0.71.0-beta.
  Native **0.71.0 (99)**, source `2590fb7810568606867f39f4c7c26689b16718bb`.
- `Proto-Mind-0.71.0-arm64-beta.dmg`: **159,772,376 bytes**;
  SHA-256 `ca0c7ce0a15a8d87de3f6742b0d4948bf272a4a5a59b7ac5b2b82987b53781ee`.
  An anonymous download of the published asset matched both size and hash.
- Portable checks covered the bundled runtimes, signatures, relocation, disposable
  first launch, fresh-state persistence/backup and OAuth start/cancel. No live
  model turn was needed. This is an **ad-hoc-signed, non-notarized beta** for Apple
  Silicon / macOS 14+. A second physical Mac and its download-quarantine launch
  remain untested; the download page states the distribution limitations.

Local verification receipts: `../../dist/portable-0.71.0-public-download.json`,
`../../хакатон/монтаж/youtube-published.json` and, in the separate website repo,
`artifacts/launch-deployment-check.json`. No operator profile or credentials were
included in the installer.

### Product Hunt and challenge

- Maker: **Yurii Yaremenko** (`@yurii_yaremenko`). Google sign-in and onboarding
  completed with the maker's approval of the 16+ declaration and daily Leaderboard
  newsletter. The other two newsletter choices remained off.
- Product: https://www.producthunt.com/products/proto-mind?launch=proto-mind.
- Dashboard: https://www.producthunt.com/products/proto-mind/proto-mind/prelaunch.
- Saved and reviewed: copy above, three real screenshots, product icon, YouTube
  embed, maker comment, three shoutouts, Free pricing and the three product topics.
- The scheduling screen explicitly stated **September 18, 2026 at 12:01 AM PT
  (10:01 AM GMT+3 / Kyiv)** for 24 hours. **Yes, join the GPT-6 Astra Challenge**
  was selected and the required answer below submitted with the schedule.
- After **Confirm scheduled date**, the pre-launch dashboard showed **Launch
  status Scheduled**, a countdown of **13 hours : 28 minutes**, and completion
  marks for shoutouts, video and the first comment. This confirms scheduling;
  judging, featuring and any award outcome are not implied.

### Submitted challenge answer (735 characters)

Astra helped me expand an existing personal assistant into a floating Mac workspace I could actually use every day. Working through Codex, I could describe an interaction, test it in the app and iterate on the SwiftUI/AppKit and Python implementation: a hover-to-peek cube, detachable companion windows, parallel conversations, live task corrections, multiple ChatGPT accounts and voice control. That changed the ambition from a single chat window to a workspace around the user's desktop. Astra is also part of the product workflow: in the recorded demo, one request asks it to read a sample client brief and save a proposal while the interface is folded away. The result is a real project file to review, not just a generated answer.

### Official references

- [Contest and submission entry](https://www.producthunt.com/contests/gpt-6-astra-challenge)
- [Contest launch guide](https://app.notion.com/p/teamhome1431/GPT-6-Astra-Challenge-Product-Hunt-Launch-Guide-3d62e1256c9e80f39bccdd2ab93bb306)
- [Posting access for new accounts](https://help.producthunt.com/en/articles/481909-how-can-i-get-access-to-post)
- [Product fields and media](https://help.producthunt.com/en/articles/479557-how-to-post-a-product)
- [Drafts and scheduling](https://help.producthunt.com/en/articles/2724119-how-to-schedule-a-post)
