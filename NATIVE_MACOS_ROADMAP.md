# Proto-Mind Native: Personal macOS Direction

Decision date: 2026-08-31. This is post-contest work for the operator's personal use, not a change to the submitted Build Week baseline or a commercial product plan.

For the current priority map, see [Current Direction](PROTO_MIND_EVOLUTION_ROADMAP.md). This file preserves release contracts and historical evidence; a limitation or proposal in an older section is scoped to that release.

## Attachment Library — Native 0.74.25

The operator suggested that PM keep what is sent to chats, so a picture or a
document stays available after its original is deleted. Messages had only
referenced attachments by path and SHA-256: of the seven pictures sent from PM
so far, five were screenshots later deleted from the desktop, and the messages
showed placeholders instead.

- Every picture, PDF and project text file a sent message or task update
  carried is copied to `<state>/attachment_library/<sha256>/` (`entry.json` plus
  the file under its original name in `original/`) off the main thread, only
  while the source still has the recorded SHA-256 and never through a symlink.
  Sending the same file again adds the message to its entry; nothing is copied
  twice.
- Library → **Images** shows the pictures as a grid and Library → **Files** the
  PDFs and text files as a list, each with its date and conversation. An item
  opens (a picture with zoom, a document in Quick Look), shows the message that
  sent it, is attached again to the current draft, shown in Finder or deleted
  after a confirmation; nothing leaves the library by itself.
- A sent message's picture or PDF whose original was moved, changed or deleted
  shows and opens from the verified copy. A draft's attachment never does: if
  its file changed, the preview still says so, because sending would fail.
- The bridge never reads PM's own data as an attachment, so attaching a kept
  item again goes through a temporary copy and the usual checks.
- Like the original attachments, the library is outside private backups.
  Earlier sends were not imported; the operator chose to start from now.

Private backups had been failing since 2026-09-06: a native-check fixture had
once written `steering-rpc.jsonl` into the operator's data folder, and the
backup inventory refuses unknown sections by design. The stray file was moved to
the Trash, the fixture now refuses the real data folder, and the inventory knows
the library as a deliberately excluded section.

Verification on 2026-09-28: **2061 Native checks** and **2440 Python tests**
passed. The new checks cover candidates from messages, copies with private
modes, one copy per SHA-256 with every message recorded, the fallback for a
deleted original, a changed file and a symlink that are never kept, unsafe names,
deletion back to a placeholder, and a sent picture that opens as it was sent
while a changed draft picture is still reported. The gallery shows both library
sections and the sidebar. The 0.74.25 (129) bundle was staged, verified with the
same signing requirement and installed in place; 0.74.24 (128) is kept as
`dist/Proto-Mind Native 0.74.24 (128).previous`.

## Zoomable Pictures — Native 0.74.24

The operator noticed that a picture opened from the chat could not be magnified.
A message's picture opens in a side panel, and a draft's in a preview sheet; both
showed a thumbnail of at most 1440 pixels scaled to fit.

- Both viewers use `ZoomableImage` (`ImageZoom.swift`), AppKit magnification in
  the manner of Preview: pinch, a two-finger double tap or a double click (from
  the fitted picture to 100% around the pointer, and back), ⌘+/⌘−/⌘0 and ⌘ with
  the scroll wheel; scroll or drag to move around a magnified picture. The
  header shows the scale between zoom-out and zoom-in buttons; a click on the
  scale fits the picture again.
- A picture opens whole and centred, fitted to its view and never enlarged past
  100%, and follows the view while it resizes until the operator zooms. 100%
  follows the image's DPI, so a Retina screenshot shows its pixels at their
  original size; the limit is 800%.
- Past the thumbnail's resolution the view decodes the original from the bytes
  the preview has already verified (SHA-256, type and dimensions), so magnified
  text stays sharp; nothing is read from disk again.
- Hidden panel tabs stay mounted, so only the enabled picture takes ⌘ + − 0.
- The English text of the Claude resume-point notice from the core update below
  ships with this build.

Verification on 2026-09-28: **2046 Native checks passed**, 14 of them new for
zooming: fitting and centring, steps and limits, a double click around the
clicked point, dragging, resizing with and without the operator's zoom, the
original past the thumbnail, a small picture and a hidden tab. The gallery shows
a panel with a Retina screenshot fitted (36%) and at 100%. The 0.74.24 (128)
bundle was staged, verified with the same signing requirement and installed in
place; 0.74.23 (127) is kept as `dist/Proto-Mind Native 0.74.23 (127).previous`.

## Core Update After Native 0.74.23 — Claude Resume Point Pinned

Twice on 2026-09-27 a Claude turn failed within two seconds, before any model
request, with "Claude did not confirm a completed response", and the next message
began a fresh session from local history, without the session's tool history.
Both turns resumed at the saved answer (`--resume-session-at`, from the core
update after 0.74.8). Claude Code 2.1.281 had written that answer's parent, a
`deferred_tools_record` attachment, after the answer and recorded the parent as
the session's leaf. On resume it follows its recorded leaf, moves down to the last
written entry only when that entry descends from it, and then up to the nearest
message; the chain therefore ended at the tool result before the answer, and it
refused the point with "No message found with message.uuid of: …". PM saw an
unknown failure without output and did not offer the session again. The same
ordering, which had caused the synthetic "No response requested." before, ended
about one turn in twenty; turns whose recorded parent had been written before the
answer resumed normally.

Before resuming at an answer, the worker now reads the transcript's recent tail
(`native_claude_transcripts.pin_resume_point`). If the transcript does not
already end at the answer, it appends the explicit `last-prompt` record that
Claude Code writes itself for rewinds and forks, naming the answer. A missing
answer, a torn last line, a linked file or two transcripts with the session's ID
leave the file untouched, and the session resumes plainly. A refusal that still
happens (the SDK's `ResultError` with `error_during_execution`, no turns and that
message) is `resume_point`: PM says that no request reached the model, and the
next message continues the same session instead of a fresh one.

Verification on 2026-09-28: **2439 Python tests passed**. The offline SDK fixture
now models Claude Code's leaf choice, and the new regression test fails on the
previous code with the operator's exact error. On a copy of the failed session,
with the API pointed at a closed local port, the real CLI refused the answer
without the record; with it, the fixed worker loaded the session and Claude Code
attached the new prompt directly to the answer. The real SDK's refusal maps to
`resume_point`. The worker loads with every turn, so the fix applies from the next
turn; the refusal text needs a bridge restart, and its English translation ships
with the next Native build.

## Smaller Cube Controls and Compact Menus — Native 0.74.23

The operator liked the fixed sidebar and asked for neater controls around the
desktop cube, a slimmer menu row at the bottom of the sidebar and less space
between menu items.

- The controls that appear when the cube is hovered are smaller: the companion
  toggles "1"/"2" are 22 pt (34), the voice and window buttons in the capsule
  26x22 pt (34x32), with smaller glyphs and gaps. Their groups keep the former
  slots, so the cube itself does not move. The shared hover button style gains a
  small variant (`nativeHover(minSize:cornerRadius:)`).
- The sidebar's menu row is about 46 pt instead of about 70: 12/10 pt text, a
  13 pt icon and tighter padding; the voice and tools buttons are 28 pt.
- In the menu, the limits block uses 9 pt gaps (14) and less padding; menu rows
  are about 28 pt (33) with no gaps. The composer's attachment and tools menus
  share the row and are tighter too.

Verification on 2026-09-28: **2032 Native checks passed** (no Python
changes); the menu row was reviewed in the gallery; the cube controls were not
rendered offscreen (they appear only while the real cube is hovered). The
0.74.23 (127) bundle was staged and installed in place; 0.74.22 (126) is kept as
`dist/Proto-Mind Native 0.74.22 (126).previous`.

## Sidebar Title Glide Fix — Native 0.74.22

The operator liked the compact sidebar, but the gliding titles misbehaved:
some did not move, one kept going back and forth, and the text travelled too
far and came back short. While a title glided, 0.74.21 swapped the truncated
text for a fixed-size one. That widened the row and changed the measurement
that decided whether to glide, so the glide switched itself off and on. Rows
passing under a still pointer while the list scrolled could also stay
"hovered" without an exit event.

As the operator described it, a title now moves while the pointer rests on its
row and snaps back to its start when the pointer leaves. It glides left like
a ticker at 36 pt/s, followed by a second copy after a gap, rests a second at
the start and repeats. The truncated title always sets the layout, and the
moving copy is an overlay that never changes the row. One AppKit tracking
area drives both the title and the hover card; scrolling, a hidden window or a
removed row release it.

Verification on 2026-09-28: **2032 Native checks passed** (no Python
changes). A new check films a row in a transparent, click-through window: the
title moves while hovered, the icon beside it never shifts, and the frame after
leaving equals the one before. It fails on the 0.74.21 version. The 0.74.22
(126) bundle was staged and installed in place; 0.74.21 (125) is kept as
`dist/Proto-Mind Native 0.74.21 (125).previous`.

## Compact Sidebar With Hover Cards — Native 0.74.21

The operator asked to tidy the sidebar: it felt spread out, long chat titles
were cut off, the hover popup appeared near the pointer instead of beside the
chat, and the text looked heavy on the glass.

- Rows are denser: navigation and chat rows use 13 pt text and are about
  28 pt tall (before: 14 pt, about 38 pt with 3 pt gaps); project headings are
  28 pt (36), the header and the "Диалоги" heading have less padding.
- Unselected chat titles are slightly softer than the selected one.
- A title that does not fit glides to show its end and back while its row is
  hovered, after a short rest, with faded edges; at rest it is truncated as
  before. Reduce Motion turns the motion off.
- The system tooltip is replaced by a card that stands just right of the
  sidebar, centred on the hovered row: the whole title, the model and the last
  activity, and the chat's state (task running, new response, draft). One
  nonactivating panel serves the whole sidebar. It appears after 0.45 s, moves
  at once to the next row the pointer reaches, never takes focus or clicks, and
  hides on exit, click, key press or scroll; rows passing under a still pointer
  while the list scrolls wait for the scrolling to stop. When the screen has no
  room on the right, the card stands left of the row.

Verification on 2026-09-27: **2029 Native checks passed** (no Python changes).
The 0.74.21 (125) bundle was staged and installed in place; 0.74.20 (124) is kept
as `dist/Proto-Mind Native 0.74.20 (124).previous`. A new check places the card
beside, left of and inside the screen. The gallery has new frames of the
sidebar at the cube's width and of a hover card.

## Line Totals for Long Turns — Native 0.74.20

The operator asked for the total of added and removed lines under an answer:
the changed-files card listed counts per file but no sum. The card already
shows a total in its header, but only when the receipt holds every edit. A
Claude receipt kept only the latest 64 actions, and most working turns are
longer, so the card counted as partial: the total was hidden, and edits made
earlier in the turn were missing from the list. A rewritten file (`Write`) also
had no removed-line count, which hides any total.

The receipt now keeps the latest 64 actions whole and every earlier file edit
without its diff preview (up to 400), marked `file_changes_complete`; the card
then shows its total. Line counts come from Claude Code's structured patch for
each edit, reported with the tool result: exactly the changed lines, all lines
of a created file, and the real removals of a rewrite. Before, they were
estimated from the edit arguments, which counted the unchanged lines of a
replaced block too. Edits made by shell commands (scripts, `sed`) are not file
edit actions and are not counted, as with Codex.

Two operator-approved fixes came with it. The Observer took "продолжим, когда
обновятся" (we'll continue when the limits reset) as a continuity follow-up and
selected unrelated memory; pauses with "когда/после …", times of day and "через
N часов" are now deferrals in Russian, Ukrainian and English. A task prompt about
a Northstar proposal, captured on 2026-09-17 as a "decision" with importance
0.95, kept being selected as relevant memory; it was soft-forgotten in working
and persistent memory after a backup in `proto_mind/data/backups/`.

Verification on 2026-09-27: **2431 Python tests and 2028 Native checks
passed**. The 0.74.20 (124) bundle was staged and installed in place; 0.74.19
(123) is kept as `dist/Proto-Mind Native 0.74.19 (123).previous`. A new Python
test fails on the old code (earlier edits were dropped) and checks exact counts for an edit, a
created file and a rewrite in a 73-action turn; a new Native check confirms the
total for a long turn that kept every edit.

## Pictures in the Composer — Native 0.74.19

After the 0.74.18 restart, the operator confirmed that sent images appear as
pictures, but the composer still showed an attached image as a row: a tiny
thumbnail, the file name and "2 872 × 1 712". Under it stood a note that
images work only through Codex, although Claude has received them since the
Claude connection shipped.

The composer now shows each attached image as the picture itself, 64 points
high with its own proportions (0.75–2 times as wide as high), and a round
remove button in its corner, the way other chat apps show a draft's images. A
click opens the checked local preview.

The destination note names Claude. It appears under the pictures, in orange,
only when an image would not reach the model: no cloud permission, a local,
Mock or API model, or a Codex model whose catalog does not confirm images.
Otherwise it lives in each picture's tooltip. The bridge's refusal text for
other providers names Codex and Claude as well. Images attached to a task
update now show as pictures too; files and PDF pages keep their lines.

Verification on 2026-09-27: **2430 Python tests and 2027 Native checks
passed**. A new check confirms that
Claude is named as the destination and that a draft's image is a bare picture
when it will be sent, with the reason below it otherwise. The gallery has new
frames of a draft with an attached screenshot (dark, light, and without cloud
permission).

## Attached Images as Pictures — Native 0.74.18

After the 0.74.17 restart, `pm_screen_zoom` worked live. A Safari capture
(1400x1052) was followed by a zoom on one tab title (250x32 pixels of the
capture). It came back at the display's full resolution, enlarged to
1400x178, with the text crisp. The operator found the hover and attachment
changes good.

The operator asked for attachments to show like the screenshot itself.
Attached images now appear as pictures above the text of the message that
carried them, as other chat apps show them, instead of a "name · width ×
height" line; a click opens the checked local preview. An answer no longer
repeats the same image line under itself.

A picture comes from the attach-time thumbnail or from the original file. The
file is read only while its size and SHA-256 match the recorded ones, it is a
PNG or JPEG of at most 4 MiB, and it is not a symbolic link. Pictures are
kept in memory (up to 40), and the recorded dimensions reserve their space,
so the transcript does not jump while one loads. Changed or missing files
show a neutral placeholder. Files and PDF pages keep their lines.

The core-dwell desktop check could fail on a busy machine, because the
preview timer (180 ms) ran past the check's fixed 260 ms wait. The check now
waits for the preview for up to a second.

Verification on 2026-09-27: **2430 Python tests and 2025 Native checks
passed**, including a check that a picture is produced only for a matching
hash. The gallery has a new frame of a message with an attached screenshot.
The 0.74.18 (122) bundle was staged and installed in place; 0.74.17 (121) is
kept as `dist/Proto-Mind Native 0.74.17 (121).previous`.

## Text-Only Status Toggles, Direct Attachments and Stable Tool Schemas — Native 0.74.17

After the 0.74.16 restart, a live batch (pointer position, a one-second wait,
then `capture: true`) worked: the pointer was correctly reported as outside
any capture, and a full-display capture came back attached. Zoom could not be
tried, however. This long-lived Claude session had kept a cached copy of
`pm_screen_capture` and `pm_computer_action` from before 0.74.16: new fields
arrived as strings while calls were validated against the new schema, so a
zoom `region` could not be passed at all. PM sessions persist across updates,
so this would recur with every change to a tool. Zoom is now its own tool,
`pm_screen_zoom(region)`; `pm_screen_capture` has its original `app`-only
schema again. Fields added to an existing tool are optional (`direction` and
`capture` on `pm_computer_action`, `direction` in batch steps), and
`validate_arguments` passes omitted optional fields to Native as null.

At the operator's request, two interface changes:

- Work-status and tool-group lines ("Работаю", "Ответ получен · …",
  "Команды в терминале…") open their details only from their words, not from
  the whole row. Hovering gently brightens the letters (secondary to
  primary at 85%; orange lines brighten to full orange) instead of drawing a
  row highlight (`NativeTextButtonStyle`).
- Dropped, pasted or chosen images and text files attach at once. There is
  no confirmation sheet; the composer shows them, and nothing is sent before
  Send. PDFs keep their page picker, which is a choice rather than a
  confirmation. The read-only drop preview remains available to code and
  checks through `previewDroppedAttachments`.

Verification on 2026-09-27: **2430 Python tests and 2024 Native checks
passed**. They include older-schema calls, the zoom gate, a chosen image
attaching at once and drops attaching without a sheet. The gallery shows the
status lines unchanged at rest. The 0.74.17 (121) bundle was staged and
installed in place; 0.74.16 (120) is kept as
`dist/Proto-Mind Native 0.74.16 (120).previous`.

## Computer Use Aligned With Anthropic's Toolset — Native 0.74.16

At the operator's suggestion, Claude now checks the official Anthropic sources
for work on Claude's own features, as Astra does with OpenAI's docs for Codex.
The `claude-api` skill and the computer-use documentation describe the
toolset Claude Opus 5.5 uses in the API, `computer_toolset_20260801`. Its 17
members include `zoom`, batch actions, `wait`, modifier clicks and
xdotool-style key names, all of which PM's own tools lacked. The official
guidance also recommends ending each group of actions with a screenshot.
Current models accept images up to a 2576 px long edge; about 1024x768 to
1366x768 is recommended. PM's 1400 px captures stay within that.

PM's tools now follow it while keeping their own schema:

- `pm_screen_capture` took `region` [x0, y0, x1, y1] (moved to `pm_screen_zoom` in 0.74.17) in pixels of the latest
  capture. It captures that area at the display's full resolution and
  enlarges it to a normal capture size (up to 4x). Actions keep using the full
  capture's coordinates, and the capture mapping is unchanged.
- `pm_computer_action` adds triple and middle clicks, `mouse_down` and
  `mouse_up`, `hold_key`, `wait`, `cursor_position`, and modifiers for clicks,
  drags and scrolls (`text` such as `cmd` or `shift+cmd`). It also adds four
  scroll directions, key repeat, and xdotool-style names such as `Page_Down`,
  `super` and `KP_Enter`. A click without x/y acts at the pointer. With
  `capture: true`, a fresh capture of the same target is attached after the
  action and becomes the latest one.
- `pm_computer_batch` runs 1–16 steps. Every step is checked before the first
  one runs. Steps execute in order and stop at the first failure, reporting
  what ran and how many were skipped; `capture` is optional.

Work-log rows show zoom, wait, pointer position and action series by action
name only, without typed text or coordinates.

Verification on 2026-09-27: **2430 Python tests and 2022 Native checks
passed**. They cover the new schemas and validation, the planning and
rejection of batches, key names and modifiers, the inverse pixel mapping and
the enlargement of zoomed regions. The live checks follow the operator's
restart. The 0.74.16 (120) bundle was staged and installed in place; 0.74.15
(119) is kept as `dist/Proto-Mind Native 0.74.15 (119).previous`.

## Label Shimmer Returns in Black — Native 0.74.15

The operator watches the moving beam over "Работаю" and the running tool
labels while Claude works; static text is not an acceptable replacement. The
0.74.13 and 0.74.14 profiles also corrected the reason for removing it: the
scroll cost comes from SwiftUI hit tests over every rendered message whether
or not Core Animation views are present (0.74.12 with them and 0.74.13 without
them both measured about 80% busy while scrolling). The Core Animation shimmer
therefore returns to transcript labels. At the operator's request the beam is
black in both appearances, so it darkens the letters it crosses. The spinner
stays on the composer's send button; transcript rows keep the static mark.
The operator also allowed a 20-message window if scrolling needs it; it stays
at 30 until a profile shows the need.

Verification on 2026-09-27: **2016 Native checks passed**, including Core
Animation checks for the spinner and the shimmer. Captures of a real window
showed the black beam crossing the text in dark and light appearances. The
0.74.15 (119) bundle was staged and installed in place; 0.74.14 (118) is kept
as `dist/Proto-Mind Native 0.74.14 (118).previous`.

## Shorter Rendered Transcript — Native 0.74.14

Scrolling cost scales with the rendered messages (see 0.74.13): each wheel step
asks SwiftUI several times what is under the pointer, and each answer walks
every rendered view. Apple's guidance on performant scrollable stacks is to
keep regular stacks unless profiling shows that lazy loading pays off. The
profiles do show that, but PM's September layout loop with a lazy stack of
selectable rows (0.40.1) still rules one out. The existing page window is
therefore smaller: a conversation renders its latest 30 messages instead of
80, earlier ones load 30 at a time with the existing button, and a jump to a
message mounts a 30-message neighbourhood. The history itself is unchanged.
A tested AppKit-backed virtualized transcript remains the long-term option.

Verification on 2026-09-27: **2016 Native checks passed**; the paging checks
now derive their numbers from the policy constants. The 0.74.14 (118) bundle
was staged and installed in place; 0.74.13 (117) is kept as
`dist/Proto-Mind Native 0.74.13 (117).previous`.

Live profiles after the restart, with a task running. The same synthetic test
as for 0.74.13 (280 wheel steps over the conversation) kept the main thread
busy 41% of the time instead of 81%. Hit tests took 16% instead of 42%,
layout 21% instead of 40%, and a step cost about 6 ms instead of 11. The
operator's own scrolling during the turn measured 40%.

## Static Transcript Indicators — Native 0.74.13

After the 0.74.12 restart, a live profile of scrolling showed a new cost: about
40% of the main thread went to cursor updates. On every scrolled frame AppKit
recomputed its tracking regions (`_NSTrackingAreaAKManager`) and hit-tested
the whole transcript through SwiftUI. The 0.74.10 profile had none of this.
The trigger was the Core Animation spinner and shimmer from 0.74.11: they were
the first AppKit views inside the scrolling transcript. The benchmark does not
show it, because AppKit updates the cursor only for the active app. SF Symbol
effects are no alternative either: SwiftUI animates them frame by frame, and
in a benchmark they caused 122–126 renders a second, as a TimelineView did.

Rows inside a transcript now show a static in-progress mark (`circle.dotted`)
and plain status text; the elapsed-time label still updates once a second. The
one moving spinner is a Core Animation ring around the composer's send/stop
button while the conversation runs, outside the scrolling content; the sidebar
keeps its spinner for running conversations. The shimmer was removed.

Verification on 2026-09-27: **2016 Native checks passed**. The gallery shows
the static marks in the live work timeline, and a benchmark capture shows the
ring around the stop button. Python code did not change. The 0.74.13 (117)
bundle was staged and installed in place; 0.74.12 (116) is kept as
`dist/Proto-Mind Native 0.74.12 (116).previous`.

Live profiles after the restart, with a task running: idle, the main thread
is busy 9% of the time (0.74.10: 39%) and Core Animation's animation
collection fell from 4% to 0.8%. Scrolling did not change, and a correction is
due. The 0.74.10 "scrolling" profile contained no scroll-wheel handling at
all: the synthetic events never reached PM, so it measured the animations
alone. The benchmark's scrolling phase has the same flaw. Its profiles
contain no scroll-wheel events, so its scrolling figures in 0.74.11–0.74.12
reflect only the streamed updates during that phase. In the running app, each
wheel step asks SwiftUI three times what is under the pointer: for scroll
routing (`_routeScrollWheelEvent`), cursor updates (`_NSTrackingAreaAKManager`)
and the system's text-input cursor indicator (`TUINSCursorUIController`).
Each answer walks the responders of every rendered message. Together with
layout, this costs about 10 ms per step (the main thread busy about 80% during
continuous scrolling). That fits a 60 Hz frame but leaves little headroom. The
cost grows with the rendered messages; fewer rendered messages or a
virtualized transcript are the remaining levers.

## Live Updates Without Re-rendering the Conversation — Native 0.74.12

With 0.74.11 installed, the operator saw the stutter return as soon as Claude
started working. Every live update still cost the whole conversation: a
streamed batch, a work-log row or a tool status. Executions forward each
change to `AppModel`; every message view observes `AppModel`, so every message
was re-evaluated and re-parsed its Markdown. In the running app, Core Animation
commits then also spent time collecting animations across the large layer tree.

A new benchmark mode, `scripts/test_native.sh --perf-bench <messages>`, hosts
the real `WorkspaceView` in a visible window. It shows a conversation of long
Markdown answers with work logs and changed files while a task runs, and
measures main-thread CPU while idle, while text streams (ten batches and two
work-log updates a second) and while scrolling. `--perf-sample <dir>` also
records `sample` profiles and a capture of the window.

The running turn's stream, work log and tool rows now live in
`LiveTurnOutput`, which only the live section at the end of the transcript
observes. A repeated status no longer notifies the app. The Markdown, work
timeline and changed-files views are Equatable, so unchanged messages are
skipped. With 80 messages the benchmark measured:

| Main-thread share | 0.74.11 | 0.74.12 |
| :--- | ---: | ---: |
| Idle while a task runs | 1.4–2.6% | 1.0–1.4% |
| Streaming | 61–65% | about 33% |
| Scrolling while a task runs | 28–39% | 14–18% |

Runs vary by about ten points on the operator's busy Mac. The remaining
streaming cost barely depends on the conversation's length (31–33% for 20,
40 and 80 messages): it is SwiftUI's own per-update graph and layout work.

Verification on 2026-09-27: **2016 Native checks passed**, including a check
that live output does not notify the app; Python code did not change. A window
capture from the benchmark showed the live section following new text. The
0.74.12 (116) bundle was staged and installed in place; 0.74.11 (115) is kept
as `dist/Proto-Mind Native 0.74.11 (115).previous`.

## Smooth Scrolling While Tasks Run — Native 0.74.11

On 2026-09-27 the operator noticed small freezes while scrolling the long
development conversation. `sample` profiles of the running app found the cause.
During a Claude turn, even without scrolling, about 23% of the main thread went
to SwiftUI rendering. The working spinner and the shimmer over its status were
TimelineViews animating at 30 fps, and SwiftUI re-rendered the whole
transcript, up to 80 messages, for each of their frames. Scroll frames competed
with that work. While an answer streamed, every text delta re-rendered the
transcript as well. Markdown parsing was only about 1.5% of the main thread.

Both indicators are now Core Animation layers: a conic-gradient arc turned by
a `CABasicAnimation`, and a gradient beam masked by the SwiftUI text. They move
without main-thread work; reduced motion or an inactive scene stops them, as
before. Streamed text reaches the transcript at most ten times a second.

A benchmark window with 400 selectable text rows measured the change. The old
indicator caused 126 outer renders per second and 15-17% main-thread time; the
Core Animation one caused none and 0%. A first attempt that moved the SwiftUI
indicators into nested hosting views did not help (126 renders, 28%). Scrolling
itself still lays out the whole non-lazy transcript on each step. Per-row text
selection doubled that cost in the benchmark, and a lazy stack halved it, but
PM keeps the non-lazy stack because of the layout loop recorded in
`WorkspaceView`.

Verification on 2026-09-27: **2015 Native checks passed**, including new checks
for batched stream text and Core Animation indicators; Python code did not
change. The gallery's live work timeline renders as before. The 0.74.11 (115)
bundle was staged and installed in place; 0.74.10 (114) is kept as
`dist/Proto-Mind Native 0.74.10 (114).previous`. After the restart the operator
found scrolling much smoother. A live profile without events showed rendering
at 2.6% of the main thread instead of 23%, but the stutter returned while
Claude worked (see 0.74.12).

## Computer Use Targeting and Compaction Rows — Native 0.74.10

The first live test of 0.74.9 through PM, on 2026-09-27, found a targeting
error. `pm_screen_capture` returned Safari's window, but a click on the playing
video did not reach it: when PM hid its windows, macOS activated ChatGPT, whose
window lay over Safari at that point. A window capture shows the window even
where another covers it, so the image did not reveal this. Capturing one app now
brings it to the front first. Before each action PM checks that the captured app
owns the topmost ordinary window at the target point (or is frontmost for keys);
otherwise it activates the app once more, and if the point is still covered it
refuses and asks for a new capture. PM's windows now return ten seconds after
the last action instead of six. Done by hand, the same sequence (hide PM,
activate Safari, click) paused the video.

Claude Code compacts a long session by itself at the model's threshold. On
2026-09-27 the development conversation compacted at 968,276 tokens: the summary
took 93 seconds, the next request carried 34,902 tokens (a 14,805-token summary
plus the system prompt, tools and re-read files), and work continued within the
same turn. PM showed nothing during those 93 seconds. The Claude worker now turns
the CLI's compacting status into one work-log row, "Context compaction…", and
completes it at the compact boundary with the tokens before and after and the
duration. It reuses the entry Codex compaction already had; Codex rows are
unchanged.

Verification on 2026-09-27: **2430 Python tests and 2010 Native checks
passed**. They cover the compaction row (with the synthetic SDK) and its display.
Window activation and the covered-point check need a live desktop and were not
part of them. The 0.74.10 (114) bundle was staged and installed in place;
0.74.9 (113) is kept as `dist/Proto-Mind Native 0.74.9 (113).previous`.

Live check through PM after the operator's restart on 2026-09-27, with ChatGPT
and PM deliberately in front of Safari: `pm_screen_capture` brought Safari
forward. A click on the player's play button started the paused video (46:04,
then 46:05 and a new scene). The key `k` paused it at 46:24 and a second `k`
resumed it (46:26). A new capture verified each result. The refusal for a still
covered point was not triggered.

## Claude Computer Use — Native 0.74.9

The operator's view is that Full Mac means full access, including computer use.
A live test on 2026-09-26 showed what that needs: with Screen Recording and
Accessibility granted to the stably signed PM, a model's shell could capture
windows and post mouse and keyboard events, and a click started a YouTube video
in Safari. In cube mode, though, PM's floating windows covered Safari, PM kept
keyboard focus, and the covered page stopped redrawing, so the first click and
key press went to PM and window captures were stale.

Claude with Full Mac now has two PM tools. `pm_screen_capture` returns the main
display or one app's front window as a JPEG of at most 300 KB (1400 px on the
long side, stepping down if needed). `pm_computer_action` clicks, double- or
right-clicks, moves, drags, scrolls, types Unicode text or presses a key with
modifiers; its coordinates are pixels of the turn's latest capture. PM runs them
itself with its own grants and hides its windows while Claude operates other
apps, restoring them six seconds after the last action or when the turn ends.
Missing grants produce an explicit request to enable them. Codex keeps OpenAI
Computer Use and API chats never receive these tools; Native also refuses them
for any other provider. They sit outside the workspace catalog hash, so the
session-stable Claude prompt and running sessions are unchanged. Work-log rows
use the existing app-control kind and record only the action, never typed text
or coordinates. The Full Mac confirmation for Claude now names the screen and
app control.

Verification on 2026-09-26: **2429 Python tests and 2009 Native checks
passed**. Checks cover the provider gate, pixel-to-point mapping, key parsing and
fitting a Retina capture into the reply bound; they do not capture the screen
or post events. The tools were not yet exercised live through PM. The 0.74.9
(113) bundle was staged and installed in place; 0.74.8 (112) is kept as
`dist/Proto-Mind Native 0.74.8 (112).previous`.

## Core Update After Native 0.74.8 — Exact Claude Resume

On 2026-09-26 the model resumed a session and saw "No response requested." where
its previous answer should have been, although PM had shown the operator the
full answer. The transcript explained it: Claude Code had recorded a
`deferred_tools_record` attachment, which is the parent of the answer but was
written after it, as the session's resume point. On resume it closed that
user-side entry with a synthetic `No response requested.` and attached the new
prompt there, leaving the real answer on a side branch outside the model's
context. It happened once in about twenty turns.

The worker now reports the transcript UUID of the turn's last answer, PM saves
it next to the session binding in `claude_sessions/<conversation>.leaf` (a
separate file that older bridges ignore), and the next turn resumes with
`--resume-session-at` at exactly that answer. The leaf is used only when its
session and answer hash match the binding; an interrupted turn resumes plainly
so the model sees what it had already done. Verified on 2026-09-26: 2428 Python
tests passed, and a live two-turn Haiku session through PM's transport attached
the second prompt directly to the first answer with no synthetic entry, and the
model recalled the first turn. This is a Python change; it reaches a
conversation when its bridge starts.

## Relative Changed Files — Native 0.74.8

After the operator re-granted Screen Recording to the 0.74.7 bundle and
restarted PM, `CGPreflightScreenCaptureAccess()` returned true in a model's
shell and `screencapture -l` captured the real cube-mode windows. macOS
attributes that process chain to PM; the earlier failures came only from ad-hoc
signatures changing with every build.

The first real capture showed the changed-files summary under a Claude answer
with an absolute path. Paths inside the task's folder now read relative to it
(`scripts/build_native_app.sh`), other paths use `~`, and the tooltip keeps the
full path. The Claude action receipt carries `workspace_root` like the Codex
receipt. This was also the first update signed with the stable local identity:
after installing it and restarting PM at 19:13 with no new grant,
`CGPreflightScreenCaptureAccess()` still returned true and window capture
worked, so macOS permissions now survive updates.

Verification on 2026-09-26: **2427 Python tests and 2005 Native checks
passed**. The 0.74.8 (112) bundle was staged and installed in place; 0.74.7
(111) is kept as `dist/Proto-Mind Native 0.74.7 (111).previous`.

## Stable Local Signing — Native 0.74.7

The operator noticed that PM lost Screen Recording after updates. The developer
bundle was ad-hoc signed, so its designated requirement was the build's code
hash (`cdhash H"…"`), different for every build. macOS stores privacy grants
with that requirement, so each in-place update made PM a new app and dropped
all of them: Screen Recording, Microphone, Speech Recognition and Apple Events.

With the operator's consent, a self-signed "Proto-Mind Local Signing"
code-signing identity (RSA-2048, ten years, code-signing use only) was created
on this Mac and imported into the login keychain with access for
`/usr/bin/codesign`; the temporary key files were deleted. It is not trusted as
a root and needs no password prompt. `scripts/build_native_app.sh` now signs
with it when present (or with `PROTO_MIND_CODESIGN_IDENTITY`) and falls back to
ad-hoc otherwise. The designated requirement becomes
`identifier "local.proto-mind.native" and certificate root = H"970a321c…"`,
which stays the same across builds. The portable package keeps its own signing.

The first launch of a bundle signed this way is a new identity for macOS, so
each permission has to be granted once more; later updates keep them. A test
copy signed with the identity passed `codesign --verify --strict`. The binary is
0.74.6 unchanged apart from the signature. The 0.74.7 (111) bundle was staged
and installed in place; 0.74.6 (110) is kept as
`dist/Proto-Mind Native 0.74.6 (110).previous`.

## Visible Claude Actions — Native 0.74.6

The operator saw Claude's work as repeated "PM tools" groups whose rows read
"bash" and were empty inside; after the turn, the saved answer kept no actions.
The worker had reported every tool call as a PM tool named after the built-in
tool, and the Claude route produced no action receipt.

Claude tool calls now use PM's shared item kinds. Bash is a terminal command
with the model's description, the command and an output preview that keeps the
start and the end. Edit and Write are file changes with a short diff and line
counts. Read is a file read whose contents are not repeated, Grep and Glob are
searches, WebSearch and WebFetch web searches, `mcp__pm__*` PM tools, and any
other tool shows its description. Every row has its duration. At the end of the
turn the transport returns a `proto_mind.claude_agent_run.v1` receipt, so the
saved answer, the work journal and the changed-files summary keep the actions.
Rows are titled by what they did (a command's description or first line,
"Read · AGENTS.md", "Edit · TaskUpdates.swift"); groups are summarized as
commands, edits, reads or searches; earlier Claude rows are no longer labeled
as PM tools.

The operator's screenshot of the real app in cube mode confirmed that the dark
sidebar title and footer in the 0.74.5 gallery were an offscreen-drawing
artifact. Screen capture from a model's shell still fails after granting PM
Screen Recording, because macOS attributes that process chain to Homebrew's
Python app rather than to PM.

Verification on 2026-09-26: **2427 Python tests and 2004 Native checks
passed**. A synthetic SDK turn with Bash, Edit, Read and Grep checks each row,
the absence of the read file's contents, the receipt, the saved work-session
tools and the work-log kinds; Native checks cover titles, icons and summaries,
and the gallery renders a sample Claude timeline. The Python side reaches a
conversation when its bridge starts; the Native side after a restart. The
0.74.6 (110) bundle was staged and installed in place; 0.74.5 (109) is kept as
`dist/Proto-Mind Native 0.74.5 (109).previous`.

## Interface Audit Fixes — Native 0.74.5

An interface audit on 2026-09-26 used a new offscreen gallery
(`scripts/test_native.sh --ui-gallery <dir>`): the main workspace in Russian
and English, light and dark, a small window, the new-chat screen, response
details, the composer and every Settings section. It uses a disposable profile,
never starts the bridge and never shows a window.

- **New chats keep the current model.** Cmd-N copied only the Codex account, so
  every new chat in the developer app started on local Ollama (four empty
  Ollama chats in the operator's list). It now keeps the provider, model,
  effort and API connection of the current chat, as panel conversations already
  did. Mac access and tool permissions are still never copied.
- **Agent-sent requests are readable.** The 0.74.3 origin header appeared raw in
  the user bubble. The transcript now shows "From task «X» · model" above the
  request; the model still receives the full header.
- **Failed turns read as prose.** Their reports use the answer font; command
  reports stay monospaced.
- **New-chat cards** form a 2 × 2 grid instead of 3 + 1, with aligned titles.
- **Settings text.** The Claude note no longer says each request only gets
  recent messages or that live updates are Codex-only; the account row shows
  either Sign in or Sign out; the Appearance subtitle names language and panels;
  the version shows its build number, e.g. 0.74.5 (109).

Not changed: the journal-read warning banner still has no dismiss button by
design, because it reports a data-integrity problem. The offscreen gallery drew
the sidebar title and footer dark in dark mode and some sidebar icons faint in
light mode; colors over the live sidebar material cannot be judged offscreen, so
this waits for a real-window check.

Verification on 2026-09-26: **2000 Native checks passed**, including new checks
for the origin label and new-chat inheritance; no Python file changed since the
2426-test run for 0.74.4. The 0.74.5 (109) bundle was staged and installed in
place; 0.74.4 (108) is kept as `dist/Proto-Mind Native 0.74.4 (108).previous`.

## Claude Updates and Restart Button — Native 0.74.4

**Updates while Claude works.** A message typed while a Claude turn runs now
reaches that turn as an update through the same saved queue as Codex updates;
the single composer action turns into Send while there is text and back into
Stop when the editor is empty. Live checks of the pinned CLI on 2026-09-26 set
the design. A user message written into a running session is added before the
model's next request, and `--replay-user-messages` echoes it with its UUID at
that moment. A message that arrives after the model's final text is instead run
by Claude Code as the next turn of the session. The worker therefore:

- announces readiness only after the prompt is written, so no update can be
  buffered with the first input line;
- writes each update with the queue item's UUID and acknowledges it as
  accepted, rejected or unknown;
- keeps an update pending until its echo arrives; if the turn's answer comes
  first, it keeps that answer as progress and waits (bounded to 60 seconds)
  for the follow-up turn, whose answer becomes the final one;
- rejects updates once the final answer is being returned.

An update that is still unconfirmed when the turn ends is named in the response
notes; nothing is resent. Attachments use the existing checked readers; images
become Anthropic image blocks. Accepted updates stay in local history, so a new
session bootstrap still sees them.

**Restart for updates.** A small icon beside sidebar search is gray while the
running build is current and turns blue when a different build is on disk
(version, build number, or the executable's inode or modification time). It is
checked every 30 seconds in a separate observable. Clicking it quits normally;
a detached helper reopens the same bundle after this process exits and gives up
if the quit is cancelled. With tasks running it asks first, because restarting
stops them.

**Memory.** Two smoke-test records in core memory ("Consolidation … smoke
succeeded") were forgotten with the existing `/memory forget` operation at the
operator's request, after a copy of the file was saved in
`proto_mind/data/backups/`. Forgotten records stay in history and are no longer
selected.

Verification on 2026-09-26: **2426 Python tests and 1998 Native checks passed**,
plus compileall; optional pytest is absent. A synthetic SDK covers an update
added during a tool step, one that arrives after the answer, rejection after the
turn and the bridge's steering handshake; Native checks cover the composer's
Send/Stop switch for Claude and build detection on a disposable bundle. Live
checks through PM's worker and the real CLI on Haiku: an update sent during Bash
steps produced `one two three BANANA`, and one sent as the answer began produced
the follow-up answer `ready BANANA`. The restart itself was not exercised by the
checks, which never quit the process. The 0.74.4 (108) bundle was staged and
installed in place while the app ran; 0.74.3 (107) is kept as
`dist/Proto-Mind Native 0.74.3 (107).previous`.

## Delegated Message Origin — Native 0.74.3

A message that one task's model sends to another through `pm_send_task_message`
used to arrive as plain user text, so the receiving model and the transcript
could not tell it from the operator's own words. It now starts with an origin
header: `[Proto-Mind: sent by the agent of task «Title» (provider · model)
through pm_send_task_message; the operator did not type it. Treat it as that
agent's delegated request.]`. Delegation itself is unchanged: the same grants,
Full Mac rules, target checks and non-recursion apply. An untitled target
conversation is named after the request, not the header, and an empty message
is still rejected.

The core also stops a false continuity label seen live on 2026-09-26. After
"…ладно, делаем паузу, продолжим позже" the next turn context said the current
message was not primary, carried unrelated important records and asked the
model to ground its next answer in one of them. Deferrals such as "продолжим
позже", "завтра продолжим" and "continue later" no longer count as references to
earlier context. English preference words match whole words, so "user", "pause"
and "because" no longer contain "use". The ignored-memory warning and its hint
apply only to important records that share a specific topic with the question.
This part is Python and reaches a conversation when its bridge starts.

Live checks on 2026-09-26: the first follow-up turn after the 0.74.2 restart
resumed the same Claude session (`--resume`) with a fresh turn-context block,
and its answer's response notes carried the new usage line (3 model requests,
context up to 261K tokens, 765K tokens read from cache). PM has no conversation
deletion, only archiving, so archived conversations keep both their history and
their Claude session; no session cleanup is needed.

Verification on 2026-09-26: **2423 Python tests and 1991 Native checks passed**,
plus compileall; optional pytest is absent. Native checks cover the origin header,
the title of an untitled target and an empty message; the new Python regressions
reproduce the false continuity label, the "use" substring match and the unrelated
grounding hint on the previous code. A live delegated turn has not been run. The
0.74.3 (107) bundle was built in a staging folder and installed by replacing its
files in place while the app kept running; 0.74.2 (106) is kept beside it as
`dist/Proto-Mind Native 0.74.2 (106).previous`. The Native change starts after
the next app restart.

## Core Updates After Native 0.74.2 — September 26

These changes are in the Python core only. A conversation picks them up when its
bridge starts (a new conversation or an app restart); no Native rebuild is needed,
and the app stays 0.74.2 (106).

**Live check of 0.74.2.** After the operator restarted the app on 2026-09-25, the
first Claude turn started a new session (`--session-id`), as the changed system
prompt requires. Its system prompt had no Observer block. The turn message carried
a `<proto_mind_turn_context>` block with a label that matched the message. The
request that the usage limit had interrupted was in the bootstrap with its
incomplete marker. The first resumed turn was checked in 0.74.3's section.

**Claude usage per turn.** Each completed Claude answer adds a content-free line
to its response notes: model requests (and subagent requests), the largest
context, cache reads/writes, uncached input and output with thinking. The worker
counts requests by message ID because result totals can include earlier turns of
a resumed session. Local transcripts showed that long tool-heavy turns spend most
of the quota by re-reading their context on every request; details are in
[Claude in Proto-Mind](CLAUDE_CONNECTION.md#model-catalog-and-subscription-limits).

**Memory.** "Давай использовать X" / "let's use X" steers the current task and no
longer becomes an automatic project decision that can replace a named earlier
one; "мы решили", "we now use" and "переходим на" still do. Task descriptions that
mention memory ("Посмотри модуль памяти. Что изменилось?", "Can you fix the
failing test? What changed in memory?", long requests) are no longer labeled
`memory_inventory`, which had doubled the records sent and could promote reused
records. Explicit questions such as "что мы решили" keep the label.

**Worktree tasks.** Project notes follow core memory: an isolated task in a
registered linked Git worktree reads and saves its main checkout's notes. Receipts
still name the task's own folder; a copied `.git` file keeps its own scope.

Verification on 2026-09-26: **2421 Python tests passed** (2333 + 88) plus
compileall; optional pytest is absent. New regressions reproduce each defect on
the previous code. No Native check was needed because no Swift file changed.
The usage line was checked with a synthetic SDK stream, not a live turn.

## Claude Continuity and Memory Bounds — Native 0.74.2

Claude Code keeps a session's first system prompt when it resumes. PM put the
per-turn Observer labels, selected core memory and correction hints there, so a
resumed session kept seeing its first turn's versions (observed live in 0.74.0)
while the context inspector showed the current ones. The Claude system prompt
now holds only session-stable rules; each turn's context travels in a
`<proto_mind_turn_context>` block inside that turn's message. The session binding
includes a hash of the system prompt, so a changed prompt starts a new session
from local history instead of silently keeping the old one. The first Claude turn
after this update therefore starts a new session in each conversation.

After Stop, a usage limit, a crash or a transient error, the next user-initiated
Claude turn from the same position continues the interrupted session with an
explicit notice; nothing is replayed. A failed or stopped request now stays in
every provider's local history, marked as having no confirmed answer and not to
be repeated unless the current request asks. Previously it was dropped, so a
session that had to start fresh after a usage limit never saw the request it was
asked to continue. Failed answers are still never replayed.

Automatic core-memory capture skips messages over 2,000 characters, which are
usually pasted reports or logs. Stored records are shown to models at up to
3,000 characters each with a truncation marker, and Claude/API/Ollama bound the
whole per-turn context as Codex already did, so one long record no longer fails
a turn. Isolated tasks in linked Git worktrees share their main checkout's
project memory; the link must be registered by the main repository, and the main
checkout's scope is unchanged, so no records move. The Settings MCP tool check
closes its own session instead of leaving a bridge and server running.

Verification on 2026-09-25: **2417 Python tests and 1988 Native checks passed**,
plus compileall; optional pytest is absent. Regressions cover an identical Claude
system prompt across a resumed session with current turn context, the prompt
hash in the binding, a 30,000-character memory record for every provider, long
pastes, failed requests surviving both resume and a fresh bootstrap, the
Swift/Python marker match, registered, relative and crafted worktree links, and
the Settings MCP check. Tests use synthetic SDK/MCP fixtures and disposable
state; no model request was made. The 0.74.2 (106) bundle was built in a staging
folder and installed by replacing its files in place while the app kept running.
The previous 0.74.1 (105) bundle is kept beside it as
`dist/Proto-Mind Native 0.74.1 (105).previous`. The new Native behavior starts
after the operator restarts the app. The live check after that restart is recorded
in the next section.

## Composer Stability — Native 0.74.1

A live hang sample from 0.74.0 captured the main thread inside
`NativeComposer.updateNSView → NSTextView.setEditable → input-method activation`,
whose nested event loop reentered SwiftUI's graph update. Opening an in-workspace
presentation could trigger this even when the model turn was already over.

Composer editability and focus changes now run after the SwiftUI update, coalesce
to the latest surface state and skip unchanged AppKit setters. Covered editors
refuse Send immediately; removed editors discard queued activation. The draft,
selection and retained editor stay intact. This UI fix does not alter Claude
session recovery or the provider's usage limits.

Verification: **615 Native interface checks passed**, including deferred and
idempotent editability, rapid presentation changes, draft/selection preservation,
Send gating, read-only editors and cancellation after removal. Tests use disposable
profiles and make no model calls.
The release app also passed six Settings/Chat cycles through the keyboard and
sidebar menu on a disposable Mock profile. An edited draft survived every cycle
and normal Command-Q, and no model request was submitted. The signed local
0.74.1 (105) bundle was installed with the user's app left closed. The live hang
sample and verification logs are retained in
`dist/diagnostics/composer-freeze-2026-09-25/`.

## Reliable Memory and Claude Sessions — Native 0.74.0

Ordinary Native questions now reach the selected model; core commands require
an explicit slash. Legacy CLI natural aliases remain available. Automatic memory
replacement requires one specifically named prior decision in the same scope;
generic topic overlap or a temporary coding instruction cannot deactivate other
decisions. New project decisions/facts carry their project identity; old unscoped
records and personal preferences remain shared. Existing records are not migrated.

Claude resumes a durable, exact per-chat SDK session. The old 12 × 2,000-character
limit is removed for Claude; bounded local history is used only to bootstrap a
new session. [Binding, error and recovery contract](CLAUDE_CONNECTION.md).
MCP sessions retain state across calls within their owning task, close on Stop
or completion, and stay independent across conversations. Tables now render with
aligned columns, inline formatting and horizontal scrolling in narrow panels.

New product ideas from the Opus review remain deferred, including cross-provider
context transfer and automatic additional model opinions. Task delegation keeps
its existing workflow and permission model.

## Claude Models and Limits — Native 0.73.1

The model menu displays versioned names from Claude Code's account catalog and
stores an exact ID when a version is selected. Default/legacy aliases remain
explicit; only observed effort levels are offered. Codex and Claude share a
provider selector in the sidebar and Limits page, with remaining percentages,
reset times and separate account identity. A bounded read-only CLI metadata
worker and independent UI observation keep refreshes out of task/editor state.
No model request, credentials extraction or paid extra-usage change is needed.
Live Pro metadata was verified; real task acceptance remains separate.
See [Claude connection contract](CLAUDE_CONNECTION.md).

## Claude Connection — Native 0.73.0

Claude runs through a pinned official Agent SDK worker and unmodified Claude Code
binary. Main and side chats share memory, context, history and explicit Mac access;
ordinary chat disables tools. Official login is available in Connections without
copying credentials into PM history or backups. Existing Codex accounts stay intact.
The first version uses bounded PM history on each request, without live steering,
Claude quota display or multiple Claude accounts. [Contract and verification](CLAUDE_CONNECTION.md).
Real subscription login and task trials await the operator's new account.

## Agent Workspace — Native 0.72.0

The assistant can now operate PM's projects, tasks, browser and document panels through a shared, turn-bound tool channel. Codex Full Mac advertises the frozen v3 catalog; API conversations opt into completed Responses/Chat Completions calls separately. Exact request, source binding and permission-generation checks keep delayed work out of another conversation. User questions persist, and late answers route to the original chat without consuming its draft.

Explicit MCP connections support stdio and Streamable HTTP, with bearer secrets in Keychain. Document libraries are hash-pinned and isolated; DOCX/XLSX/PPTX/PDF helpers use create-only atomic writes, Office previews use Quick Look and PDF images use the sandboxed page reader. Task delegation can use Git worktrees, with optional session-only one-turn child Mac access. Continuation remains an explicit user action. Native automatic skill selection is local and no longer requires an extra model request.

The complete acceptance list, test evidence, setup instructions and current limitations are recorded in [Agent workspace upgrade](AGENT_WORKSPACE_UPGRADE.md). Existing chats need no migration. Their Full Mac provider session is refreshed once to install the tool catalog, using existing bounded local context. The existing public download is not changed by this local release.

## Glass Cube Dock Icon — Native 0.71.1

The Native app icon is a new softly bevelled glass cube on a graphite tile.
Broad aqua/teal faces replace the small glyphs and heavy metal frame, keeping
the cube recognizable at Dock sizes. The 1024-pixel PNG and generation prompts
live under `assets/`; the existing icon packager supplies standard macOS sizes.
This is a local appearance update; the published 0.71.0 beta is unchanged.

Verification: the five existing icon checks passed, including exact transparent
corners, opaque center, dimensions and visible coverage. The ICNS representations
and signed local application bundle are checked during packaging. No Python,
conversation, permission or private-state behavior changed.

## Shared Conversation Surfaces — Native 0.71.0

The main reader and all side PM tabs now use `ChatView` and `ComposerView`.
`ConversationComposerContext` projects an exact conversation's draft, execution,
account catalog, effort, permissions and send/stop eligibility without changing
`AppModel.selectedID`. The same centered column, typography, responsive toolbar,
Mac access control and Apple dictation are available in compact and expanded
panels. Image/PDF/drop previews, criteria and project memory capture their source
conversation and presentation window; they no longer need to select the main chat.
Dictation retains its original draft and rejects late results after manual editing,
submission or moving capture to another composer. Ordinary typing keeps its caret;
programmatic updates synchronize mounted copies of the same conversation.

`ConversationRouting` observes intentional mouse/keyboard input inside workspace
content, excluding the sidebar, passive cube previews and focus/order changes.
Sidebar selection uses the last available target, reuses an existing chat tab or
adds one beside a browser/file/terminal. It preserves the main selection and all
other drafts, targets exact search/unread messages and reports the tab limit without
closing documents. Hidden/closed targets fall back to the main reader. The sidebar
New Chat action follows the same destination and retains provisional draft rules.
Window layout and routing do not grant access, alter accounts or end tasks.

Verification: 1917 full Native checks passed; after the final model-selection
compatibility adjustment, 607 interface checks passed. Coverage includes parallel
conversation execution, account/model isolation, retained drafts and caret state,
bound dictation, source-scoped image/PDF/drop previews, stale-preview refusal,
sidebar tab reuse/capacity and unavailable-target fallback. Isolated UI QA covered
an expanded companion and an embedded panel, browser-to-chat sidebar navigation,
shared menus, criteria, file-picker ownership and a reviewed text attachment in
the side conversation while the main draft stayed untouched. No paid model or
live microphone call was made. Python behavior and private-state schemas are
unchanged; portable distribution remains 0.66.1.

## Live Interface Language — Native 0.70.0

Settings → Appearance switches English/Russian immediately across the existing
workspace, cube, companions and voice controls. Profile-specific preferences
retain the choice after restart. Shared observation updates labels and locale;
native titles receive a language notification and transient popups dismiss to
avoid stale sizing. No workspace identity, task, tab, draft or history is replaced.

The additional English catalog covers memory/skill inspectors, journal and
recovery screens, attachments, account/voice/dictation errors and accessibility
labels. Literal templates support interpolation without translating inserted
user text, paths, provider IDs or exact confirmation tokens. Running task status
and empty browser/terminal titles resolve in the current language. Bundles include
RU/EN permission explanations; macOS-owned controls still follow system language,
and raw core/provider evidence retains its source text.

Verification: 1891 full Native checks passed, followed by 570 interface checks
after the final label/observer adjustments; 5 portable-runtime Python tests passed.
The localization checks cover live observation, profile isolation, idempotent
selection, exact draft/message/attachment preservation, in-flight status, retained
browser/terminal instances and all additional template placeholders. Isolated UI
QA exercised RU→EN→RU, normal and cube settings, a companion draft, the originating
file picker and attachment menu, and English persistence on relaunch. No model or
voice call was made. Python cognition and private-state formats are unchanged;
portable distribution remains 0.66.1.

## Menus Within Their Workspace — Native 0.69.1

Panel plus buttons use a contained list. Conversation, messenger and CLI choices
replace that list in place with a Back action. Header menus open below their
button, composer menus above it; both are bounded by the mounted surface and
the window's visible content, with scrolling for long content. Companion chrome
stays visible while its menu is open. Hiding, moving or resizing the owner closes
the popup. Internal panels now expose expand/restore in the top bar as well as
the corner control, retaining the same tabs and drafts. The entire model-source
disclosure row responds to clicks in both main and panel composers.

Verification: 558 Native interface checks passed, including narrow/offset popup
geometry and live boundary updates after panel resizing. An isolated QA app
exercised internal and separate-window add-tab menus, in-place messenger/CLI
lists, Escape dismissal, expansion/restoration with a retained draft and a click
in the middle of the model-source row. No provider turn was sent. Python and
private-state formats are unchanged; portable distribution remains 0.66.1.

## Multiple ChatGPT Accounts — Native 0.69.0

Each conversation can select a named ChatGPT subscription account from its model
menu, including companion conversations. Settings → Models manages sign-ins and
names; the same page and account-specific usage screen retain their originating
window. Existing conversations use the original main login. Additional profiles
use the official Codex browser login with isolated CODEX_HOME, model catalogs,
quota caches and provider-thread registries. Account names and IDs are UI
preferences; no credentials are copied from another profile or into backups.

An execution captures its immutable account before any await. Two accounts can
run tasks concurrently; send, steering, Stop, voice and paired Telegram input
keep the original execution. Sign-out closes only that account's idle bridges,
without changing global cloud consent or another account's task. A running turn
or pending steering receipt prevents account replacement. Switching an idle
chat retains its local messages but clears model/access choices and persists a
required local provider-session reset before the next message. Recent PM chat
history then seeds a new provider session; an earlier account's stale thread
cannot silently resume. A missing account label after restoring preferences
recovers the exact account namespace instead of falling back to the main login.

Provider bindings for additional profiles are inventoried in private backups and
discarded as authority during restore. Credentials and provider rollouts remain
excluded. PM memory, local history and other connected services are still shared
within this installation; this is per-chat provider selection, not separate OS
users or isolated PM memory profiles.

Verification: 2,331 Python tests and 1,875 Native checks passed; the final
steering-receipt guard also passed all 38 focused account/portable checks. Disposable
integration accounts covered parallel execution, late quotas, exact steering and
Stop, independent sign-out, draft/history reload and pending session reset.
A separate QA application verified account creation/selection, preserved main
login and nested account/usage pages in a companion window. The installed Codex
CLI 0.153.4 also confirmed that a fresh extra profile is signed out and does not
inherit an existing login; no model turn was sent. Two real signed-in accounts
have not been exercised together. Portable distribution remains 0.66.1.

## Messengers and Remote Tasks — Native 0.68.0

Telegram and WhatsApp web tabs use persistent, profile/service-scoped WebKit
stores. Ordinary browser tabs remain ephemeral. Explicit message selection is
required before a messenger snapshot enters the existing Browser to Task flow;
source identity, bounded content and untrusted-data labeling stay intact. Upload
pickers attach to their original window. Resetting sign-in closes matching views
before clearing that store. Calls, system notifications and in-app downloads are
not part of this release.

The optional Telegram bot uses Keychain credentials, expiring pairing links,
local account approval and a task allowlist. Private fresh messages can list,
select, create, inspect, start, steer and stop tasks. New chats carry model/folder
choices but not Mac permissions. Voice and Telegram share the same draft-free
execution entrypoint; completions send only after the regular AppModel save.
Connection metadata and an at-most-once input cursor live outside restored
private backups under ProtoMindConnections. A sidecar lease prevents simultaneous
polling by instances of one profile. Disconnecting leaves accepted tasks alive.
Connection startup is explicit; offline queued input is not executed later.

The floating window group now uses canJoinAllApplications, canJoinAllSpaces and
fullScreenAuxiliary consistently, including passive previews and voice. Normal
mode keeps its ordinary collection behavior and level.

Verification: **1,858 Native checks passed**, including real local WebKit
selection boundaries, persistent/ephemeral store separation, pairing/allowlist
controls, duplicate-update rejection, background steering/completion, exact stop,
draft preservation and disconnect behavior through a fake Telegram transport.
A separate signed QA app verified Telegram Web and WhatsApp's QR sign-in page,
panel launchers, retained web sign-in, and opening from settings. WhatsApp needs
a Safari compatibility version in WKWebView's user agent. Fullscreen collection
flags and passive hover transitions are covered locally; video-player-specific
overlay behavior still needs operator confirmation. The installed developer
bundle is **0.68.0 (95)**; its previous bundle was preserved. The portable
installer remains the separate 0.66.1 artifact.

## New Chat Project Folder — Native 0.67.2

The sidebar and File menu now call the new-conversation action **Новый чат**
(**New chat**). Empty, non-archived chats show **Папка проекта** directly above
the composer, including cube mode and companion conversation panes. After a
folder is chosen, its name appears in the same button; existing conversations
keep their uncluttered composer. The controls reuse the established main/pane
folder pickers and authorization behavior, without new persistence paths.

Verification: **552 Native interface checks passed**. An isolated signed app
verified the renamed action, folder selection and cancellation with a preserved
draft, the chosen folder label, absence in a populated chat, cube-mode placement
and folder selection from a companion chat. No live model or operator state was
used. The developer bundle is 0.67.2 (94); the portable installer remains 0.66.1.

## Companion Windows in Both Modes — Native 0.67.1

The two separate companion windows now work in the regular workspace as well as
cube mode. A compact overlapping-rectangles menu in the normal toolbar toggles
each window; ⌘⌥1 / ⌘⌥2 work in either mode. Mode changes retain the same windows,
tabs, live terminal processes, detached compact/expanded geometry and local
presentation stacks. Attached surfaces reflow beside the destination workspace,
keeping their upper/lower slots, gap and shared height split.

Normal mode uses the ordinary application window level. Minimizing or closing
the workspace hides both companions without changing their enabled preferences;
restoring it brings them back. The optional independent detached-window setting
continues to apply only to cube folding. Normal expansion measures the actual
sidebar edge (including resize/hide) and excludes the native toolbar. Explicit
main settings remain reachable by clearing covering companion expansions.
Transparency, source-owned dialogs, file pickers, hover chrome and return-to-base
use the same existing controls in both modes. No history schema or task permission
changes are involved.

Verification: **1,815 Native checks passed**, including **254 focused desktop
checks**. Coverage includes normal-mode startup/restoration, both switching
directions, attached movement, detached expansion, canonical reattachment,
minimization/close notifications, a real disposable terminal retaining its PID,
local presentation ownership, and unchanged draft/history/task state. A signed
isolated release app verified the toolbar menu, keyboard toggles, a local browser
page surviving repeated mode switches, the exposed regular toolbar/sidebar edge,
and settings opening inside an expanded companion. No live provider or microphone
was used. The operator's running application was not restarted; the portable
installer remains the previously prepared 0.66.1 artifact.

## Unread Replies and PDF Pages — Native 0.67.0

Completed model replies get an unread dot in the sidebar; interrupted requests get
an orange attention mark. The floating cube counts conversations with unread
results independently of its running-task ring. Its count opens a result menu.
Navigation targets the exact response, and only its visible footer in an active,
uncovered workspace acknowledges it. Passive cube previews and hidden tabs do
not acknowledge results. Read state survives restart in profile-specific UI
preferences, outside dialog history and private backups; old history starts read.
A temporarily blocked history load retains these preferences for recovery.

PDF panels render original page artwork locally through the existing isolated
worker. One page at a time is rasterized to at most 1600 pixels on the longest
edge; the 8 MiB document and 300-page limits remain. Navigation, fit/zoom and a
selectable-text mode work independently of the selected conversation's task.
The original source hash, page number, image dimensions and image digest are
checked before display. Changed sources fail visibly. Explicit attachment still
adds only the current page's bounded text, never the original or rendered image;
pages without a text layer remain viewable without enabling OCR. The original
PDF is never parsed in the GUI, and viewing never follows PDF actions or calls a
provider.

Verification: 2,324 Python tests and compileall passed; optional pytest is absent.
The broad Native run passed 1,795 checks, including two concurrent real disposable
bridges, interrupted/completed outcomes, exact acknowledgement, restart and
profile isolation, history byte preservation, independent PDF reads, source
changes, blank and rotated pages, and raster edge coverage. A final focused run
passed 90 response/PDF checks, including preservation during a pending restore. A separate app profile
verified sidebar marks, cube count/menu navigation, viewport acknowledgement,
original PDF colors/layout, portrait/landscape pages, zoom/fit, selectable text,
page-specific attachment and draft preservation after switching conversations.
The final release also verified that an explicitly reopened replacement PDF
resets page/zoom state, including replacing three pages with one.
No live model, microphone or operator profile was used for these checks.

## Response Actions — Native 0.66.1

The reply footer uses a grey ellipsis without a text label or menu chevron.
Its menu retains response details and exact task history, and adds Markdown
export through a Save panel attached to the originating window. The saved
snapshot contains only the chosen visible reply, never private receipts or the
rest of the conversation; selecting another task cannot replace its text.
Result panels offer the same Save action, meaningful heading/conversation titles
and brief copy acknowledgement. Export failures stay in the source workspace.

Verification: 520 focused Native interface checks passed, including exact UTF-8
export snapshots, bounded filenames and failure preservation. The signed release
was exercised in a disposable profile: chat and result-panel saves matched the
reply bytes, switching tasks retained the original export, and cancelling wrote
nothing. Copy acknowledgement, the ellipsis menu, a floating window's Save sheet,
and its in-place response details were checked in the UI. No live model was used.

## Browser to Task — Native 0.66.0

PM browser pages and selections can be explicitly handed to a chosen conversation.
An isolated WebKit read captures bounded text and its exact URL, excludes form
controls/editable regions, and rejects navigation or closure during capture.
The local preview adds the source to the existing draft; sending remains explicit.
Quoted page data is marked untrusted and uses the existing history, permissions
and steering contracts. Voice has exact browser/task routing with the same bounded
snapshot; ordinary browsing does not share page text with a model.

Completed replies open as transient Markdown documents beside chat, retaining their
original conversation for file links. Companion actions stay in their source panel.
English/Russian main UI and voice use a profile-specific language preference; a
restart applies it without changing stored messages or provider identifiers.
Technical core reports may still be Russian.

The portable release includes a fictional Northstar project and a two-minute
recording guide. It contains no account or pre-generated model answer. A real
model recording, second-Mac trial and Product Hunt submission remain separate.

Verification: 1,762 Native checks passed, including real WebKit selection/filtering,
bounded capture, exact destination/draft preservation, first-send history, injected
save failure and recovery, voice routing without a live API call, and language
isolation. Five portable Python checks passed. A disposable app verified English
after restart, browser capture, normal Mock submission, collapsed source evidence
and answers beside chat. No personal account, live model or microphone was used.
The final onboarding/sidebar copy corrections also passed 512 focused Native
interface checks; the full suite above was not repeated for these label changes.

## Panel Drafts — Native 0.65.7

Opening **Диалог PM** in an internal or floating panel creates only a provisional
editor. Repeating the action reuses an untouched tab in that panel. First nonempty
Send publishes the chat through the existing history writer, before any request.
An attachment-only Send follows the same path. Blank tabs do not appear in the
sidebar, history search, open-chat menu or voice task list, and are not persisted.

Written drafts and selected attachments are still saved for recovery. Closing
their last editor keeps them reachable in the conversation list; after restart,
these saved drafts are regular chats. An untouched tab is discarded when its last
editor closes. Existing chats, running tasks and previously saved empty chats are
left intact. No archive schema migration or provider change is required.

Verification: all 1,737 Native checks passed, including four independent launchers,
empty Send, repeated opening, first-send save failure, restored and erased drafts,
attachment-only submission, concurrent turns and the Session Spine history writer.
The attachment check also found and fixed normalization of macOS system path
aliases before text-file selection. A disposable app verified an internal panel
and both floating companions, publication on first Send, closing a written draft
and relaunching without the untouched tabs. No live model or microphone was used.

## Companion Navigation and Sizing — Native 0.65.6

Both floating companions have a size toggle next to Return to position. It expands
or restores the miniature; the hover corner remains available. Moving a detached
miniature translates its saved expanded frame, preserving the chosen large size.
Detaching again centers that size on the new compact location instead of restoring
an obsolete sidebar position. Attached expansion and the upper/lower home slots
keep their existing behavior.

Each companion now hosts its own auxiliary pages and nested confirmations.
Settings, conversation context and response details retain their source bindings,
live updates and dismissal guards, with Back returning to the mounted tab. Native
file/folder pickers attach to the initiating window without collapsing it. Delayed
previews capture their destination before awaiting; message image/PDF previews
also retain their destination panel. The main router tracks forwarded pages and
shared dismissal guards without creating another history writer.

Verification: 464 focused interface checks during implementation and all 1,716
Native checks on the final sources passed, including both detached geometries,
reattachment, captured routing after focus changes, nested dismissal, OS picker
ownership, same-turn reopening, moving an already-open screen between windows
and retaining settings in place while an operation blocks dismissal.
An idle nested page produces no further publication loop. A disposable application
build checked the new size toggle, lower-window attachment/context routes,
upper-window terminal confirmation/cancellation and opening a synthetic PDF in
that same expanded upper window. The release build also checked moving settings
from the main chat to the upper window and opening the API settings/editor from
its model popup. No live model or microphone was used.

## Companion Controls on Hover — Native 0.65.5

Compact floating companions now hide the complete top chrome when the pointer
leaves: window controls, tabs, browser navigation/address, document/PDF controls,
project-file navigation and conversation/terminal headers. Their content uses the
freed height. Hover anywhere in the window restores all bars together. Expanded
companions and ordinary workspace panels retain their controls.

The views remain mounted, including WebKit and SwiftTerm surfaces. A short exit
grace prevents flicker at the edge; address/filter editing, dragging and native
popup menus hold the controls open until the interaction ends. Hiding a window
clears transient holds. VoiceOver keeps controls visible; task errors remain
available independently of the header.

Verification: 437 interface checks and all 1,686 Native checks passed, including
real WebKit/PTY geometry,
independent upper/lower hover, rapid re-entry, interaction holds, expansion,
detachment, folding/reopening, retained page state and terminal input. A disposable
application build also checked the compact/expanded browser, retained page input,
tab menu and return to the main workspace. No live model or microphone was used.

## Synchronized Cube Transitions — Native 0.65.4

The chat and its companion windows now share one AppKit fade. The complete group
is prepared before the animation starts, and companions keep their child-window
ownership until the common fade out finishes. Floating windows disable AppKit's
independent automatic ordering effects. Reopening or returning to normal mode
cancels prior alpha animations; an obsolete completion cannot hide the new view.
The cube, voice window and explicitly independent detached windows remain outside
the group. Reduce Motion and nonanimated presentation update the group immediately.

Verification: 423 interface checks and all 1,672 Native checks passed. New checks
sample real AppKit window opacity and ordering throughout both transitions,
including attached/detached companions, mid-fade reversal, layout during folding,
explicit presentation, covering expansion, independent visibility and Reduce Motion.
Task ownership, drafts, history and microphone state remain unchanged. No live
model or microphone call is needed for these checks.

## Cube Hover Recovery — Native 0.65.3

Showing or focusing a companion no longer pins a hover preview. A local input
monitor pins only intentional mouse-down/key-down events in the workspace or its
companions; cube actions and explicit presentation commands retain their behavior.

During a preview, a cancellable pointer check uses the actual visible window frames
to detect leaving the group, including lost exits from overlapping/rebuilt tracking
areas. Crossing into the chat or a companion keeps the preview open. Tracking stops
when the workspace is pinned, hidden or shut down; it is never a task/sensor session.

Verification: 407 interface checks and the complete 1,656-check Native suite passed.
The regression uses real AppKit windows with injected pointer positions: focus
changes without input, missing companion exits, attached/detached companions,
continued hover inside a companion, click/key pinning, and stopped polling after
pin/hide/shutdown. Task ownership, drafts, history and microphone state are preserved.

## Companion Window Behavior — Native 0.65.2

The first and second companions keep their upper/lower slots even when a neighbour
is hidden or detached. The header action next to Close always returns to the base
slot; it no longer toggles detachment. Both that action and drag reattachment reset
the column width and the height split to equal halves, clearing covering expansions.
Detached compact/expanded frames and retained content remain separately owned.

The main title strip delegates dragging to macOS. Position notifications update
only the saved group origin; redundant resize notifications do not reflow the group.
Custom companion/core drags and the shared resize strip use captured global event
coordinates to avoid feeding previous window movement into queued events.
Companion hosting views no longer change the window's size constraints from content.

By default both free and attached windows follow cube previews, pinning and folding.
Appearance offers an explicit per-profile option to keep free windows visible.
No task, model access, history schema or private-state storage behavior changes.

Verification: 1,638 Native checks passed, including repeated parent moves and
queued pointer events, real-window cube hover/folding with detached windows,
canonical reattachment after free expansion, split reset and retained tab/draft
ownership. Disposable release UI checks covered detachment, drag reattachment,
expanded-window reset, shared-edge resize/reset and the Appearance switch.
The main header's native WindowServer drag handoff is covered in checks; CUA did
not demonstrate physical dragging of the main window, so perceived smoothness
still needs operator feedback. No live model or microphone call was made in UI QA.

## Stacked Companion Windows — Native 0.65.1

The two attached companions now share one right-hand column. They divide the
workspace height equally by default, preserving the 8-point gap. Resizing either
window's shared edge adjusts both heights; an explicit drag strip and accessibility
increment/decrement actions offer the same control. Split proportions persist per
profile. A single attached window fills the height. Reattaching beside the workspace
or above/below the attached sibling restores the split; free frames remain separate.
Heights are rounded once and derived together to avoid native-frame rounding drift.

Attached windows are AppKit child windows of the workspace. Parent movement moves
the group directly; position notifications only update its geometry reference.
The custom title strip moves the parent once per drag event, without entering a
second drag loop. Detach, hide, regular mode and shutdown remove child ownership.
Expansion and main presentations keep the sidebar and settings reachable.

All four controls around the cube have larger rectangular hit areas and the same
hover/press feedback. Companion commands observe desktop mode directly, so their
enabled state updates immediately when switching modes.

Focused verification: 374 Native interface checks passed, including complementary
resize, split bounds, sibling snap, direct parent and header-event group movement,
retained tabs/drafts and preference isolation. Disposable UI checks exercised shared
edge dragging, detach/reattach with saved proportions, settings and mode shortcuts.
The complete Native suite then passed all 1,623 checks. No live model or microphone
session was started by the manual UI checks.

## Floating Companion Windows — Native 0.65.0

The internal workspace retains its existing tabs, with one full-height panel by
default and a profile-persistent lower-panel switch under Appearance. Disabling
the lower panel retains its content and clears any covering expansion.

Floating mode adds two independent AppKit windows, controlled by buttons 1 / 2
on the left of the cube (also available in its accessibility/context actions and
via Command-Option-1 / 2). Their content uses the same PM conversation, WebKit,
file/PDF/image and SwiftTerm surfaces. Attached windows form a horizontal row at
the workspace height, with 8-point gaps and individually resizable widths. The
row fits the active monitor; the sidebar remains available during expansion.

A subtle hover glow marks the first window's lower-left and second window's
upper-left expansion corner. Attached expansion covers the area from the sidebar
to the row's right edge; detached expansion has its own saved frame. Dragging a
header beyond a small threshold detaches, and dropping by the adjacent right
edge reattaches; a link button provides the same action without dragging.
Compact and expanded detached sizes/positions are independent. Neither docking,
hiding, expansion nor mode changes recreate the retained panel/NSWindow. Attached
windows hide with the workspace; detached windows remain independently visible.
Ordinary mode hides the companions while retaining their sessions until quit.

Appearance has independent background-transparency controls for both companions,
respecting Reduce Transparency. Geometry, docking and visibility preferences are
namespaced UI state, outside private-state backups; tab contents remain transient.
Main settings, confirmations and file pickers reveal and raise their existing
owner, preserving source bindings. Shutdown closes owned terminal/browser sessions.

Verification: 1,604 Native checks passed, including negative-coordinate/narrow
monitor geometry, snap boundaries, real drag-event routing, independent frames,
profile preferences, unchanged running conversations/drafts, and session retention.
Disposable UI checks exercised actual detachment dragging, border resizing,
both expansion modes, browser text retained through docking/hiding/expansion,
interactive PTY command output, and the lower-panel switch with four independent
glass controls. A final 355-check interface pass and UI checks verified that
docking preserves keyboard focus and main settings rise above a detached expanded
window. No live model, API or microphone session was used for these checks.

## Parallel Workspaces and API Models — Native 0.64.0

Two equivalent panels sit to the right of the main conversation, sharing its
normal/floating workspace and transparency. Each has PM conversation tabs,
manual WebKit browser/web-app tabs, document previews and SwiftTerm 1.20.0 PTYs.
Dividers resize the split. Hover reveals the upper panel's bottom-left triangle
or lower panel's top-left triangle; expansion fills only the area to the right
of the sidebar. The tab menu also exposes expansion for keyboard access.

Stable mounted views retain browser state, terminal processes, drafts and
scroll positions while switching tabs, hiding the deck or expanding a panel.
Hidden surfaces relinquish keyboard focus. Closing a PM tab neither stops its
execution nor deletes its conversation; closing a running terminal asks to end
that terminal session. Quitting ends terminals, and tab layout is transient.
Each PM surface routes sends, Stop, Codex steering and selected context through
its existing ConversationExecution and the single AppModel history writer.
Async document results capture their destination panel before awaiting.

API connections support OpenAI Responses and OpenAI-compatible Chat Completions.
The exact model ID and endpoint are explicit. Connection metadata is a local UI
preference; credentials are stored separately in Keychain and bound to the
connection/destination. They never enter dialog objects, work journals or core
exports. API requests use core memory and selected project-note/skill/text/PDF
context with instruction and turn receipts. This route is chat-only: Full Mac,
automatic skill/recall selection, live steering and Brother Persona retain their
existing provider boundaries. Keys and connection metadata are outside private
core/dialog restores; a missing connection requires selecting it again.

The transport requires HTTPS for remote servers, permits loopback HTTP, has an
independent network-idle deadline and interrupts blocked response reads on Stop.
Incomplete streams cannot become completed replies. There are no automatic paid
retries, redirects, silent provider changes or hidden reuse of the voice key.
Installed Claude Code or another chosen executable runs in a terminal with its
own account; deeper PM integration of third-party CLIs remains a later adapter.

Verification: **1,534 full Native checks and 2,322 Python tests pass**. These cover
concurrent PM sends without selected-editor mutation, durable API connection
references, real interactive PTY input/ANSI output, and a complete Native → stdio
→ loopback API → receipt → history round trip. HTTP tests cover both formats,
malformed/incomplete responses, credential exclusion, required consent, denied
API Full Mac, and Stop during an idle stream. No live paid API call was made.

Disposable UI checks exercised both layouts, a PM response, interactive terminal
paste/execution, both expansion directions, the API connection form inside the
workspace and a browser draft retained across tab and normal/floating switches.
The release terminal also starts with both build-directory resource bundles
unavailable. The packaged Python/core/bootstrap, memory save/restart/backup and
17 Mach-O dependency paths pass portable verification, with the signature intact.
These are local checks, not a second-Mac installation test or live API-provider certification.

## Project Drag Indicator Cleanup — Native 0.63.2

The insertion line now belongs to one sidebar drag session rather than to each
project row. Moving over another group replaces the current marker; delayed exit
callbacks from older groups cannot clear or retain the wrong line. Drop, Esc,
sidebar disappearance and native drag completion clear the session. Destination
updates arriving after completion or mouse release cannot recreate a marker.
A release watcher runs in the common and event-tracking run-loop modes only during
a drag, covering drops outside a destination and older macOS versions. It removes
itself and the local key monitor when the gesture ends; there is no idle polling.
macOS 26 also uses the [native drag completion event](https://developer.apple.com/documentation/swiftui/view/ondragsessionupdated(_:)).

Verification: **245 interface checks pass**. New regressions cover missing/late
destination exits, source hover, completion followed by stale updates, release
outside a destination, watcher cleanup and unchanged persisted order. Gesture
state tests use an injected mouse-button reader; they are not a physical-drag
UI test. Dictation and Python runtime code are unchanged.

## Dictation Pauses and Project Dragging — Native 0.63.1

Dictation now uses Apple's multi-utterance recognition delegate. Completed
utterances accumulate separately from the current partial; a pause, revised
partial, repeated sentence or empty task-final result cannot replace earlier
speech. Recording and the editable draft retain their existing cancellation,
navigation and submission boundaries. [Apple delegate contract](https://developer.apple.com/documentation/speech/sfspeechrecognitiontaskdelegate).

Sidebar projects animate as whole groups, with a compact folder preview and a
line marking the insertion boundary. The full group accepts a drop, with a small
midpoint dead band to avoid indicator flicker. Hovering does not reorder or save
anything; release performs the move. Reduce Motion disables the movement animation.
The private drag representation is restricted to this process and still validates
the profile owner. Context-menu and accessibility moves remain available.

Synthetic Russian audio reproduced the old reset across 4- and 9-second pauses.
The production speech backend then retained all three utterances; a second run
also retained an intentionally repeated sentence and continued after 65 seconds
of silence. Both runs used on-device Apple Speech with no microphone capture,
OpenAI call or personal audio. They verify transcript continuity, not microphone
accuracy. Disposable UI checks inspected normal/floating layouts and moved a whole
group through accessibility without changing the draft. Physical drag feel remains
a manual check; the computer-use drag attempts did not yield a verified drop.

Verification: **1,487 full Native checks pass**, including native drag-provider
decoding, insertion-boundary stability, multi-utterance draft persistence and the
existing late-callback/navigation protections. Both release executables build.
No Python runtime code, personal-state schema or account configuration changed.

## Project Order and Dictation — Native 0.63.0

Project headings in the sidebar carry a private typed drag payload. Drop in the
upper or lower half of another heading to place the whole project before or
after it. Context-menu and accessibility actions offer the same moves. Manual
order applies across search/archive views; later activity cannot undo it. New
projects follow the saved order. UI preferences are namespaced by state directory
in UserDefaults, without changing dialog history, permissions or backup schemas.

The composer microphone now inserts Apple Speech partial/final transcripts into
an unsent draft. It preserves existing text, attachments and continuation; manual
editing, submission, conversation changes, leaving/folding the chat and opening
another workspace screen stop capture and reject late callbacks. Finishing
dictation stops the microphone immediately and allows up to three seconds for
final text. Sleep and application shutdown stop capture. Active task lifetimes
are unaffected. The ordinary voice conversation moves beside **Меню**, retaining
the independent voice window and the existing cube entry.

Russian is the initial dictation language; Russian, Ukrainian, English and system
language choices live in **Настройки → Голос → Диктовка**. Language persists, microphone
state does not. Apple Speech explicitly uses on-device recognition when supported;
otherwise recognition may use Apple's servers through the system speech permission.
The Info.plist permission explanation and voice settings describe that distinction.
The pipeline reuses the validated 24 kHz microphone conversion/device recovery and
has no OpenAI transport or audio-file writer. Dictation and GPT Live never share
the microphone concurrently. [Apple Speech request contract](https://developer.apple.com/documentation/speech/sfspeechaudiobufferrecognitionrequest).

Verification: **229 focused interface checks and 1,478 full Native checks pass**.
New checks cover cross-profile ordering, duplicate folder names, restart, search,
new projects, invalid drags, active tasks, partial/final dictation, manual edits,
draft persistence, attachments, navigation, failures, cancellation during permission
setup, language persistence and signed PCM conversion. A separate application using
the production speech backend recognized a synthetic Russian phrase on-device,
without opening a microphone or calling OpenAI; this is not an acoustic accuracy
benchmark. Disposable UI checks exercised project movement through accessibility,
the relocated voice entry and both normal/floating layouts. Computer-use coordinate
drag attempts did not produce a drop; physical mouse drag remains a manual UX check.
No Python runtime source changed and no paid API session was opened.

## Core Hover Preview — Native 0.62.1

Hovering over the folded core for 180 ms reveals the existing chat and sidebar
without activating Proto-Mind or taking keyboard focus. The workspace remains
visible while the cursor crosses into it; leaving both surfaces for 320 ms folds
the temporary preview. Clicking the core pins that preview, and another click
folds it without reopening until a new pointer entry. An intentional workspace
click or keyboard activation also pins it. Normal click-to-open remains available
without hovering, including through accessibility.

Core dragging cancels a pending reveal and dismisses only a temporary preview.
Sheets and inline page requests use the existing explicit reveal path, cancelling
pending hides. Mode changes and shutdown cancel delayed transitions. Hover uses
always-active tracking areas and cancellable one-shot delays; it adds no pointer
polling, model turn, microphone use, permission change or persistent state schema.
The same chat, draft, task executions and independent voice window stay mounted.
Reduced Motion continues to disable window fades.

Verification: **196 focused Native interface checks and 1,445 full Native checks
pass**, including delayed
entry, quick pointer passes, crossing to the workspace, pin/fold/reentry, dragging,
sheet requests, shutdown cancellation and preservation of running work and drafts.
Hover inputs are direct local Native events against disposable state; they are
not a claim of a physical mouse-hover test on the user's live session.

## Portable First Installation — Native 0.62.0

The separate **Proto-Mind.app** beta targets Apple Silicon and macOS 14+.
It embeds pinned CPython 3.12.14 and Codex 0.153.4 runtimes, with verified archive
hashes and upstream notices. The allowlisted Python package and the Swift app
share the development source tree. The developer bundle, account and existing
personal data paths are unchanged; no automatic migration runs.

`LaunchConfiguration` resolves installed code and binaries inside the running
bundle. Mutable core and Native state use sibling directories under the current
user's `Application Support/ProtoMind`. Bridge launches use installed code as
their working directory, isolated Python import settings and an explicit Codex
executable. Both private namespaces have owner-only directory permissions before
the bridge starts. A missing bundled Codex cannot silently select a system account or
runtime. A missing config file cannot switch the distributed bundle to the
developer profile. Chat sandbox access covers only the bundled runtime/helper paths and
the existing private execution roots. Updates can replace or move the bundle
without changing the profile path.

The first-connection page appears inside the workspace, checks the local core,
offers the user's ChatGPT sign-in, and keeps cloud consent explicit. It can be
skipped and reopened from Settings. Its dismissal is namespace-scoped UI state;
it cannot grant access or activate voice. Fresh portable dialogs use the Codex
catalog's default model; saved conversations keep their previous selection.
Voice/API, GitHub CLI, Ollama and the proprietary signed Computer Use helper
remain optional separate connections, described in the installation guide.

Verification: **2,313 Python tests** plus compileall and **1,435 Native checks**
pass; the subsequent missing-config guard passes **20 focused Native launch
checks**. Optional pytest is absent/skipped. Another **150 focused tests** pass with
the packaged Python 3.12. A relocated bundle with spaces in its path starts its
bridge, saves/reloads synthetic core memory, verifies a private backup, reads
signed-out Codex status, and starts/cancels browser authentication without a
credential or model turn. Its 17 Mach-O files have no absolute non-system
library dependency. Codesign verification still passes after use, with no
core data or Python caches added inside the bundle. GUI checks exercised the
welcome screen, unsigned-in status, Settings/help navigation, draft persistence
and restart after relocation. All runtime checks used disposable profiles.

This is **an ad-hoc signed beta**, not a notarized public download. Apple
Developer ID, notarization and testing the downloaded artifact on a second Mac
remain distribution gates. The current Mac is macOS 26.6.2; macOS 14 was not
physically tested. No microphone, paid model request, account import, public
upload or modification to the running developer application was part of these
checks. [Install guide](INSTALL_MACOS.md) · [Packaging workflow](native/Distribution/README.md).

## Unified Workspace Screens — Native 0.61.0

Auxiliary screens now replace the chat content within the existing workspace in both ordinary and floating modes. This includes Settings, quotas, response details, conversation/run history, backup workflows, memory/persona/skill screens, attachment previews, Session Spine and nested confirmations. Back and Escape dismiss only the top screen. Parent views and the underlying transcript stay mounted; source bindings and dismissal callbacks remain authoritative. Source-local form state is evaluated inside SwiftUI rendering so validation continues updating. In-progress save/commit guards also block Back and navigation; hidden pages cannot receive keyboard shortcuts. Selecting a dialog returns to that chat. Native open/save panels attach to the workspace window, including when launched from floating controls. Exit warnings use the same inline presentation and retain the existing unsaved/shared-operation checks.

The sidebar menu takes the available column width. One compact quota block sits above Settings, Limits and the mode switch. It shows the main `codex` weekly window first, then the five-hour window only if that account response includes it. Reserve buckets never substitute for absent core periods; missing readings remain unknown. Detailed account data remains in Limits. The ellipsis opens upward, and model/effort selection uses dedicated tabs and selected rows, with provider configuration in Settings.

Voice uses a separate resizable floating panel. Moving it leaves the workspace and cube in place; position is a namespaced UI preference. Its glass background follows chat transparency. Closing controls hides the panel without ending a call or stopping accepted tasks; the call's hang-up control remains explicit. There is no new microphone activation path, API call, account switch or data-format migration.

Verification: the **1,415-check full Native suite** passed, followed by **167 focused interface checks** after the final form-state and keyboard-isolation changes. Coverage includes nested pages, replacement bindings, exactly-once dismissal, source-local state updates, commit guards, task/history preservation, narrow settings layouts, core-quota selection and independent voice-window geometry. A disposable signed app verified Settings/quotas/back, typed rename validation, dialog navigation, model/effort tabs, upward menus, voice setup from the collapsed cube, an attached native folder picker and ordinary/floating mode transitions. No microphone or paid API session was opened for these checks. Release 0.61.0 (75) builds locally; Python runtime and private-state schemas are unchanged.

## Floating Sidebar and Voice Controls — Native 0.60.0

The existing floating window now contains the full shared sidebar beside its chat, each on an independently adjustable glass background. Settings → Оформление has two transparency sliders, persisted in the existing UI-only state-directory namespace. The sliders change backgrounds only; text, buttons, drafts and task state retain their opacity and ownership. Reduced Transparency keeps both surfaces opaque, preserving the stored choices for when that system setting is disabled. Existing window frames are fitted to the larger minimum workspace.

The 88 × 116-point nonactivating core reveals microphone and normal-window controls below the cube on hover. An always-active tracking area works while another application owns keyboard focus; entering or leaving never starts audio or changes modes. A separate cube handle owns click/drag events, leaving both buttons their normal hit testing. The core also exposes both actions through accessibility and its context menu. The tiny active-microphone indicator remains visible when the controls hide. Returning to ordinary mode uses the existing window and restores its appearance.

Both microphone entries share one launch path: a configured voice session starts immediately and shows conversation controls; an existing call reveals its controls without starting another session. A missing API key or disabled cloud consent opens Settings → Голос. API-key controls and consent have moved out of the conversation popover. macOS microphone permission still applies. Folding, hovering and restarting the application never start a call. This release changes no API protocol, billing policy, account selection or access grants.

Verification: **1,362 Native checks pass**, covering persistent independent transparency, namespace isolation, invalid preference values, always-active hover entry/exit, drag/click separation, accessibility actions and preservation of drafts, task execution and microphone-off state. A disposable signed app verified the full sidebar/chat, both settings sections, changed slider values surviving restart, cube expand/collapse, normal-window restoration and the cube’s voice action. The UI automation provider cannot move the pointer inside a nonactivating panel; hover behavior is covered by local Native event checks, while the two actions were exercised through accessibility. No microphone or paid voice API session was opened. No Python runtime code or private-state format changed.

## Computer Use Cleanup — Native 0.59.1

A completed Mail task left the shared service capturing its window. The signed helper resolves the running service beneath `CODEX_HOME`; Native supplied its isolated account profile, where that installation does not exist. The previous notify command therefore returned zero without sending a release. Only the signed Computer Use helper now receives the verified installation home. The Codex server retains Native's account, credentials and history namespace.

Normal completion, Stop and provider failure attempt an awaited release through the still-live Codex parent with the exact thread/turn IDs. A lost start acknowledgment can release the known thread without inventing a turn ID. The local command has a five-second deadline and contains no prompt, answer or credential; it does not start a model turn. Native closes the parent afterward, allowing EOF shutdown before bounded terminate/kill fallback. Publishing a final receipt cannot skip process shutdown. Cleanup failure leaves the answer intact and shows an explicit warning rather than claiming capture stopped. The receipt distinguishes a release request from an independent screen-state audit. Saved Full Mac selection remains enabled for the next task.

Live diagnosis used Codex CLI 0.153.4 and the installed signed service. The old isolated-home handler returned zero in 0.01 seconds while ScreenCaptureKit continued receiving frames. With the correct home and a Codex parent, the handler returned zero and the same active stream logged `stopCaptureWithCompletionHandler`; subsequent observation showed no new frames. The fixed runtime then verified all ten allowlisted MCP tools, repeated the scoped release in 0.075 seconds and exited normally. These checks made no model request, reopened no mailbox and did not kill the shared service.

Verification: **2,308 Python tests** plus compileall and **1,353 Native checks** pass; optional pytest is absent/skipped. Regressions cover completed/stopped/failed turns, an uncertain start, two distinct release scopes, cleanup timeout/nonzero/malformed results, private-output omission, no release before generation or without Computer Use, publication failure and bounded graceful process shutdown. No private-state migration is required.

## Floating Workspace — Native 0.59.0

The sidebar menu and ⌘⌥J switch the existing workspace into a floating glass presentation. A separate 88 × 108-point nonactivating panel holds a vector cube. Clicking it reveals or folds the chat; dragging moves the core without taking keyboard focus. The workspace keeps ordinary dialog selection, composition, voice, file/browser tabs, evidence and approval sheets. Esc and Close fold a floating workspace instead of stopping work or destroying its window. The normal window remains available from the header and core context menu.

There is one AppModel, dialog writer, task execution registry and voice connection. Folding orders the workspace out; it does not stop a task, hang up voice, clear a draft or create a second client. A sheet arriving while folded reveals its workspace. The original window level, appearance and geometry return on leaving floating mode. SwiftUI retains ownership of its titled frame and toolbar host: removing the title frame while SwiftUI removes its toolbar background caused an AppKit exception in the first disposable build, so the released implementation keeps the frame and hides its chrome.

The glass uses a behind-window NSVisualEffectView with a denser reading surface and a transparent outer frame. No screen-sized invisible overlay intercepts desktop clicks. The cube has no idle animation; running tasks animate at most 20 frames/s. Existing voice input and a playback-buffer meter drive its glow without another audio stream or stored audio. Reduced Motion disables rotation/scale; Reduced Transparency replaces the glass with an opaque surface. Core microphone status stays explicit.

Mode and two window frames live in macOS UserDefaults under a hash of the Native state directory. They contain no dialog, project title, credential or access grant and are intentionally outside private-state backups. Restoring the mode opens the workspace with voice off. Geometry is clamped to visible screens, including negative-coordinate monitors and removed displays. macOS controls placement in fullscreen Spaces and Stage Manager; this does not claim priority over every system surface.

Verification: **1,353 Native checks pass**, including 21 desktop/presentation checks. Disposable checks preserve a running ConversationExecution and unsent draft across folding, reopening and normal-window restoration; exercise event-coordinate dragging, Close behavior, geometry recovery, mode restoration, and clearing playback indication. The signed isolated app was exercised with synthetic conversations: normal/glass/core transitions, Esc, ⌘W, task selection, new conversation, file panel and restart. The nonactivating core is exposed as a named floating window for accessibility. The UI automation provider cannot drag that panel, so drag evidence is the direct native-event regression rather than a claimed pointer smoke test.

Three idle samples of the collapsed debug preview showed **0.0% process CPU**, with about **65 MB** reported memory on this fixture. This is an idle process measurement, not GPU profiling or a long-session energy benchmark. Existing Live voice behavior is covered by the Native regression suite; this interface release did not open a microphone or paid API session. No Python runtime code changed. The signed 0.59.0 (72) bundle was opened with the existing account and switched to floating mode; conversation-manifest and preferences hashes matched their pre-launch values.

## Live Voice audio repair — Native 0.58.1

The first microphone test reproduced nonzero input from macOS Voice Processing I/O but all-zero mono PCM after conversion. Its discrete multichannel format has no ordinary speaker layout: the default converter mapping can leave mono without a source. `LiveVoiceCapture` now explicitly selects microphone channel zero. Regression fixtures exercise 1, 2 and 9 input channels and check the actual converted signal and sample count; the previous mapping fails the fixture.

Starting a voice call waits for actual microphone callbacks before opening the paid session. A low-frequency health check notices a stalled capture stream. Core Audio configuration notifications are deferred and revalidated: a running graph stays running; a stopped graph with the same microphone format restarts in place. Recreating a settling Voice Processing aggregate repeatedly can itself cause repeated configuration stops. A changed microphone format rebuilds the graph locally, without recreating the API session or replaying accepted commands. Stale playback is discarded before recovery. Rapid repeated device failures still end visibly. The microphone meter shows received signal separately from connection and task status.

The opening follows the [Live greeting sequence](https://developers.openai.com/api/docs/guides/live-conversations#greet-before-the-caller-speaks): correlated instructions acknowledgment, then one commentary prompt while audio continues. An unrelated acknowledgment, duplicate acknowledgment or already-started user speech cannot issue a second opening prompt.

The explicit `--live-audio-device-smoke --synthetic-pcm PATH` check opens the actual audio engine without an API request or recording microphone audio. Three starts, benign notifications, a forced engine stop/restart, playback completion and engine release on hangup were checked on the MacBook's built-in devices. The probe holds only a weak engine reference so it cannot mask a lifecycle defect. Each run confirmed all 66,902 synthetic speech frames played. Ordinary regression suites do not open the microphone or API. The opt-in API probe also supports `--with-greeting --with-audio-device` for received speech plus real playback.

Verification: **1,332 Native checks pass**, plus **12 actual-device checks**. The opt-in API/device probe received the Russian greeting before its synthetic caller spoke, completed `list_projects` against a fixture, and received the spoken result. All 673,920 received audio frames reached playback completion; the session closed with **29 seconds** of reported usage. This checks the built-in microphone/speakers, not every possible external audio route. No Python runtime code changed in this patch.

The installed app was also checked with the operator speaking: greeting, microphone transcription, spoken replies, and a second call without restarting the app. The second call exercised an actual Core Audio stop and successfully restarted the same graph; its meter showed live microphone signal. Both calls were ended. Existing messages and drafts remained intact, and preferences matched their pre-restart hash; the spoken test command added its own interrupted task entry to history.

## Live Voice — Native 0.58.0

The waveform button beside Send opens a native GPT Live 1 conversation. The primary WebSocket uses continuous mono PCM16 at 24 kHz; AVAudioEngine captures and plays audio with voice processing for echo cancellation. Microphone access and a saved API key are checked before opening the billable session. Start is explicit, mute sends silence locally, and hangup closes the session while preserving accepted working tasks. No audio is recorded to disk and remote session storage is disabled. Captions are a bounded, temporary display, not authoritative task boundaries.

Responses delegation uses GPT-5.6 Luna to call the finite project/task interface: list known projects and tasks, open/create a task, submit a message, inspect status, or request cancellation. Completed function items are bound to their response/delegation; partial arguments and repeated call IDs cannot execute actions. Task messages use the existing conversation execution and history writer. Corrections are persisted in the original user message before delivery. Voice never consumes a typed draft, its attachments, criteria or prepared context. A received answer and an independently verified result remain different states.

API keys live in macOS Keychain, scoped to the Native state location. Settings and backups contain no key. Voice uses OpenAI API billing independently of the existing Codex account: [GPT Live 1](https://developers.openai.com/api/docs/models/gpt-live-1) is $0.05/minute at this release, with separate backend usage. API configuration follows the official [Live WebSocket](https://developers.openai.com/api/docs/guides/voice-websockets?api=live) and [delegation](https://developers.openai.com/api/docs/guides/live-delegation) contracts. No key, balance, or account metadata is embedded in the bundle.

Preferences v3 remember Full Mac selection for the exact conversation and optional workspace. Actual grants remain in memory and are issued afresh by each bridge. Workspace/provider changes, explicit disabling, cloud-consent revocation and recovery clear the selection; task interruption rotates the process grant without forgetting the choice. v1/v2 preferences remain read-only compatible until an explicit save, oversized settings cannot replace a readable file, and private restore removes remembered access. The original preference file was copied before installing the change.

Verification: **2,298 Python tests and 1,324 Native checks pass**. New checks cover protocol boundaries, malformed/repeated calls, bounded context, preference restart/reconnection, actual fixture task execution/steering, draft preservation, and independent voice/task shutdown. A live API test sends synthesized Russian speech, receives `list_projects`, returns only a synthetic project, receives the spoken answer and final `session.closed` usage of **20 seconds**. A separate disposable native UI run verifies API-key setup and a real microphone/connection start; this is not a claim of exhaustive acoustic testing across Mac audio devices. Ordinary suites never open a paid session.

Build scripts use two jobs by default and the installed macOS 26.5 SDK when the CLT macOS 27 interface requires an unavailable SwiftUI macro plugin. `PROTO_MIND_SWIFT_SDK` overrides the SDK; the system developer selection is unchanged. VIREN, local/free voice, permanent voice-conversation memory and visual input to Live remain outside this release.

## Architecture Decision

Use a real SwiftUI/AppKit application with a Codex-inspired sidebar, conversation workspace, composer, file/browser panel and separately accessible answer evidence. Preserve the existing Python cognitive core and its memory, learning and permission logic.

```text
SwiftUI / AppKit
    -> private newline-JSON stdio bridge
    -> existing shared Proto-Mind handler
       -> operator command: existing formatter and existing gates
       -> normal turn: Observer -> MemoryKeeper -> selected reasoner
                       -> memory evaluation -> reflection -> grounding -> log
    <- original text + completed Cognitive Turn Envelope

Reasoner choice:
    Ollama on loopback                         fully local
    Mock                                      deterministic local test
    official Codex app-server / ChatGPT login  explicitly cloud-connected
```

Native rendering and history do not replay a turn. The bridge does not dispatch model text through Proto-Mind commands. Manual operator writes require exact-input confirmation plus existing internal token/consent gates. Registry metadata is not a model grant. From v4.0d, a separate Full Mac grant enables official Codex built-in tools; unrestricted shell can reach files/CLIs outside the core gates, so those gates are not a filesystem security boundary in this mode.

Local library navigation takes a separate route: `SwiftUI -> library_list/library_inspect -> bounded fixed-store reader`. It never enters the normal cognitive handler or an LLM prompt.

## v4.0a: Native Foundation

Implemented:

- Real Swift executable and separate `dist/Proto-Mind Native.app`, not a Python GUI launcher disguised as a native app.
- New conversations, persisted local history, per-conversation provider/model selection, Return to send, Shift-Return for a newline, and native settings.
- Existing 387-command / 41-category catalog, search, risk/mutation labels, prepare-before-send controls, and a read-only core overview.
- Completed-turn inspector with actual retrieved memory IDs/previews, storage receipt IDs, grounding/reflection findings, preserved notices, and the raw core report. Retrieval is not proof of model use or truth.
- Original shared cognitive handler called once; process-memory session/consent state is isolated between conversations and expires on bridge restart. `/exit` discards that conversation's live core session, not its UI history.
- Loopback-only Ollama and explicit Mock. Unlike the legacy CLI, the new native Ollama adapter fails visibly rather than silently substituting Mock when the model is unavailable.
- Official Codex stdio adapter with browser-based ChatGPT sign-in, dynamic account model list, assistant-only text streaming, Stop, bounded context, and no Platform API-key fallback.
- Separate Codex profile and isolated child HOME; no reading or copying Codex Desktop credentials, project instructions, hooks, MCP setup, or parent API-key environment variables. No account connection on startup.
- Codex runs in an empty workspace with a read-only/no-network tool sandbox, approval policy `never`, shell/code/browser tools and extensions disabled, strict config parsing, all server tool requests denied, and non-chat items refused. An outer macOS `sandbox-exec` profile restricts the provider process itself to system/runtime files and its own three private directories, not personal file contents, native chat history, or core stores. It can write only its own profile/HOME; the trusted authentication/model controller needs network access, while model tool networking remains off. Missing OS isolation fails closed.
- Installed Codex 0.136.0 does not recognize the documented `tools.view_image` option. It is deliberately not used. The outer OS sandbox also covers built-in file readers, including local-image reads, which are not sufficiently contained by a read-only shell sandbox alone. Tests verify denied private reads, denied symlink reads, and denied out-of-profile writes. These guards are defense in depth, not a claim that a prompt alone is a security sandbox. CLI configuration is checked against the installed version and the [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
- Bridge failures do not automatically retry turns. Normal provider failures/cancellation occur before memory evaluation. Closing the native client does not kill an in-flight core write; EOF allows the helper to finish and close its own Codex child.

Unchanged: core JSON/JSONL schemas, automatic memory rules for successful normal turns, consent/capture/learning gates, Context Injection configuration, action/runner allowlists, CLI, PySide, and tkinter. The old `dist/Proto-Mind.app` and its shortcut are retained; the native build does not overwrite them.

## v4.0b: Everyday Workspace

Native 0.2.0 adds an everyday workspace without granting the model filesystem or computer-use authority:

- Conversation search, rename, reversible archive/restore, per-conversation drafts, and draft restoration after a failed send. Fenced code blocks have copy-only controls; links cannot open local files or command URL schemes. No model response is executed.
- Explicit cloud permission persists in private `preferences.json`, defaults off when missing, and is revoked on logout. Startup reads never create or rewrite history/settings. Corrupt/unknown-version settings fail closed and cannot be overwritten by a toggle. Checking the selected Codex account at startup happens only after this saved permission exists; it does not send a conversation or start generation.
- A workspace can be bound per conversation. Choose the same folder used in Codex to see the same underlying files, not a copied project. Status reads a bounded `.git/HEAD` when available, without invoking Git/hooks. Worktree `.git` indirection is deliberately not followed. Changes appear after manual refresh; no watcher, bidirectional sync, merge, rename, delete, or write tool exists.
- `native_workspace.py` provides native-only status/list/read helpers. Directory traversal is bounded and one level at a time (400 visible entries, at most 2,000 scanned). UTF-8 regular source/text files are limited to 256 KiB, with a 12,000-character preview. Symlinks, special files, path escape, hidden credentials, generated/build/backup paths, current core stores/exports, project-root exports/logs/desktop preferences, and native private state are excluded. Absolute directory traversal uses no-follow directory descriptors.
- Attaching is a separate explicit action after preview: up to three files and 6,000 characters per file. The UI saves relative paths, SHA-256 and truncation/count metadata, not file bodies. Before a normal turn the bridge rereads each file, compares its preview SHA-256, and refuses stale attachments before contacting a model or processing the core turn. This is a bounded best-effort snapshot, not a filesystem lock or secret-redaction system; review the visible excerpt before sending.
- Selected excerpts are quoted untrusted data in the native reasoner adapter only. Original user input still goes unchanged to Observer, memory evaluation, and the existing session log. File contents are not directly promoted into memory or appended to the user's input field. An answer may discuss the supplied content and remains private native history; subsequent bounded chat history may therefore include that answer. Slash/exact natural operator commands neither read nor consume pending attachments.
- Loopback Ollama health/model inventory is explicit and does not download or generate. Local requests bypass inherited proxies and refuse redirects. Codex errors use documented error codes for sign-in, usage limits, context size and connectivity, without dumping raw server error details or silently using a separately billed API.
- UI history v1 loads with safe defaults; a later explicit save writes v2 fields for drafts, archive state, workspace binding, and attachment manifests. This changes only the native UI archive, not any core-store schema. A separate UI-history checkpoint is required before upgrading an existing personal archive.

## v4.0c: Native Library Views

Native 0.3.0 exposes the cognitive records as three operator-only screens, rather than adding more slash commands:

- Memory lists persistent and working memory with separate source identities, active/superseded/inactive state, literal text/tag/ID search, and current/history/all filters. Goals show stored focus and priority; Skills show stored summaries/procedures and active/archive state. Unknown states remain explicit and are not promoted into the current filter.
- Compact lists use 100-row pages. A selected card rereads its source, shows the original bounded text and metadata, and reports SHA-256 changes since the list was loaded. Duplicate IDs within a source are omitted as ambiguous, not assigned new IDs. Source paths, read errors, omitted counts, and truncation are visible. Missing stores are reported without initialization or repair.
- `proto_mind/native_library.py` accepts only three collection names, not file paths. It reads only `persistent_memory.json`, `working_memory.json`, `goals.jsonl`, and `skills.jsonl` below the launch project's `proto_mind/data`, independently of the selected conversation's workspace. Reads use no-follow directory/file descriptors and reject non-regular files. Limits: 16 MiB per file, 5,000 inspected records per file, 200 search characters, 24,000 characters per detail block. Over-limit entries are explicitly omitted; the view is not a complete audit beyond that cap.
- Existing status/priority definitions are reused, but store constructors and legacy loaders are deliberately not called: they can initialize files, synthesize IDs/defaults, or read unbounded input. The native projection uses legacy defaults only for display, never to rewrite data. Plain-text skill bodies and stored provenance/lifecycle schema labels do not execute anything or claim fresh verification of provenance/truth.
- `LibraryModels.swift` decodes versioned read-only contracts; `AppModel` keeps library query/filter/selection in memory and ignores stale async responses. Reading never calls retrieval, `/skills use`, commands, model APIs, or telemetry. It does not write usage counters, focus, core schemas, native conversation history/settings, exports, or session logs. There is no attach-to-prompt, edit, apply, or run control in these screens.

Checkpoint before implementation: `backups/proto_mind_backup_2026-08-31_08-17-42.tar.gz`. Verification later found that the old backup source list omitted root `native/`, scripts, and most root documentation; this initial archive protects core data/code but is not a complete pre-change Swift rollback. Before fixing that coverage, `backups/proto_mind_worktree_2026-08-31_08-51-17.tar.gz` captured the then-current working tree (excluding backups, build/runtime caches, the built bundle, and local credential configuration). It is a later checkpoint, not a reconstruction of the earlier native source.

`backup_utils.py` now includes native source/tests, scripts, root Markdown documents, and the maintained source/data folders. It excludes build/bytecode caches, does not follow source symlinks, and publishes only complete private archives without overwriting same-second checkpoints. Four regression tests cover coverage/exclusions, no-overwrite permissions, failure cleanup, and symlink non-dereference. These changes affect backup output only, not cognitive logic or store schemas.

The updated CLI was then exercised directly: `backups/proto_mind_backup_2026-08-31_08-55-52.tar.gz` contains the native library source/tests, scripts, root docs, and core package, with mode `0600`. This is the verified current-source checkpoint, not a pre-v4.0c rollback.

Before replacing the local app bundle, `backups/proto_mind_native_history_2026-08-31_0845_library.tar.gz` preserved only `conversations.json` and `preferences.json`, not the credential profile. Native history schema remains v2; no archive upgrade is introduced.

## v4.0d: Native Agent Tools / Explicit Full Mac

Native 0.4.0 implements the operator's updated direction: an assistant that can actually work on the Mac, not only answer from manually attached excerpts.

- Two distinct modes: the existing isolated **Chat** default and explicit **Full Mac**. The latter enables `shell_tool`/`unified_exec` and built-in patch/image-reading tools through the official [Codex app-server](https://learn.chatgpt.com/docs/app-server). No custom shell RPC, MCP server, or model-to-slash dispatcher is added.
- Above the composer, the operator grants Full Mac for the selected Codex conversation and bound folder. A separate sheet describes user-level file/network/terminal access, no per-command approvals, cloud transmission of tool data, and the fact that the folder is not an access fence. This is not root, Accessibility, Screen Recording, or Full Disk Access from macOS; platform protections still apply.
- `AgentGrants` holds a random token only in bridge memory, bound to conversation, canonical starting folder and directory identity. Normal-turn requests require this token and explicit cloud consent; merely sending `access_mode=full_access`, selecting a folder, loading history, or logging in is insufficient. The UI never serializes the token. Disable/restart revokes it; provider/folder/cloud changes and failed agent turns discard UI access. A token from another conversation, folder, replaced directory, or earlier bridge process is refused before the cognitive/model turn.
- At the Native 0.4.0 milestone, Chat transport remained protected by its existing outer OS sandbox while Agent transport was intentionally unsandboxed with `danger-full-access` and `approval_policy=never`. The effective policy/cwd and absence of automatically loaded project instructions were checked before `turn/start`; hooks/MCP/plugins/browser/Computer Use/multi-agent/goal/background features were disabled at that stage. Native 0.14.0 keeps normal Chat isolated and now enables only the separately verified Computer Use MCP inside an explicit Full Mac turn. Isolated HOME prevents automatic Desktop-config import; it does not prevent Full Mac tools from reading explicitly addressed personal paths.
- Only user-submitted normal Codex turns can select the agent path. Slash/exact natural operator commands, library/workspace inspection, Ollama and Mock do not inherit tools. Existing cognitive processing, original session-log input, memory evaluation and injection settings are unchanged. Successful agent answers still participate in the existing memory rules; tool bodies are not directly added to user input or the session log.
- The UI shows access mode throughout the turn, observed command starts/completions, exit codes/output previews and file-change diffs. Final-answer phase is kept separate from commentary. Private/internal reasoning, hook prompts, foreign thread/turn events, credentials and arbitrary unknown event fields are not forwarded. Unsupported client-tool/approval requests are denied rather than silently adding permissions. This event projection is not a secret-redaction service: a legitimate command's printed output can contain private data.
- `native_agent_run.v1` includes run/thread/turn IDs, access mode/cwd, start/end time, completion/failure state, counts, bounded activity and warnings. It is saved with the Native message in archive v3; v1/v2 load without rewrite or grants. Records do not enter `proto_mind/data` or `exports`. A lost start response is conservatively treated as possible execution, not proof of no side effects. A completed model turn does not imply every command succeeded; failures/unknown item outcomes remain visible.
- Each agent turn has a 15-minute foreground limit and 64-observed-activity cap. These request interruption after a limit, not atomic admission before every effect. Stop/error does not roll back files, restart automatically, guarantee termination of detached processes, or turn partial work into success. The full-access app-server closes after a turn, never remains idle for normal account/library operations. EOF requests cancellation for model work while allowing already-running core writes to finish. In-flight UI receipts are not crash-durable; a crash can leave work requiring manual inspection.
- Full Mac's checkpoint/destructive-action guidance is a prompt instruction, not a restrictive policy engine. It can modify personal/core files under user rights and is not constrained by the existing four-command runner or preview exclusion rules. Enable it only for trusted, scoped operator work. Computer Use was still a future capability at this 0.4.0 milestone; Native 0.14.0 adds it under the same explicit broad grant, while stronger project-only editing remains future work.

Checkpoints before implementation: `backups/proto_mind_backup_2026-08-31_09-04-11.tar.gz` (native/scripts/docs members verified) and `backups/proto_mind_native_history_2026-08-31_09-09-49.tar.gz` (only conversations/preferences, no credential copy).

### Agent Acceptance Evidence

- Installed Codex 0.136.0 schema and live no-generation probe confirm `danger-full-access` request / `dangerFullAccess` effective response, `never`, the exact temporary cwd and no instruction sources. Direct official `command/exec` with `/bin/pwd` returns the temporary directory and exit 0. This probe does not add a public execution endpoint to Native.
- Live account-default model adapter turn, 2026-08-31 06:26:46-06:27:01 UTC: read only a disposable `message.txt`, create `message.txt.before`, edit `native-agent-pilot=before` to `native-agent-pilot=after`, and verify both files. Two command receipts returned exit 0; one file-change receipt contained the expected diff. Independent file reads confirmed the changed marker and original backup. No real project or personal data was supplied to this prompt.
- Python permission/protocol tests cover separate confirmation, token scope/restart/revocation/inode change, chat/operator bypass, original-input logging, partial failures/cancellation, unsupported requests, bounds, failure exit codes, lost start response, and unchanged chat-process isolation. Swift tests cover v1/v2/v3 compatibility, receipt persistence, no persisted permission, UI confirmation/cancel/disable and cloud/provider revocation without generation.
- Visual Native smoke used a code-only temporary project/profile: the projected live-pilot receipt displayed two expandable commands and the file diff; no commands were replayed from that fixture. Cloud-off refused tools, Cancel preserved Chat, the separate checkbox enabled Full Mac, and `/commands status` returned 387 prefixes without model generation. A signed-out normal turn produced a failed zero-command receipt and returned to Chat without retry. Successful grant/disable clears earlier configuration errors. This is UI/bridge verification plus a separate real adapter pilot, not a claim that the fixture UI itself ran that live edit.
- Personal core/export checksums remain the same across implementation and the isolated live pilot; Context Injection remains false. Native personal history/preferences are separately checked before/after bundle replacement. Auth-controller state may change during account/model requests and is not included in those content-preservation assertions.

## v4.0e: Conversation UI / Public Work Timeline

Native 0.5.0 follows the operator's Codex screenshots without replacing the cognitive core or changing permission defaults:

- A quieter grayscale sidebar groups conversations by their actual bound folder. Search, rename and reversible archive remain available; library/core screens move into a disclosure group. The conversation uses right-aligned user bubbles, open Markdown answers, icon-only diagnostic controls with labels, and a compact composer with access on the left and model selection on the right. Diagnostics start collapsed, not removed.
- `native_progress.py` consumes the official [app-server public message phases](https://learn.chatgpt.com/docs/app-server): `commentary` feeds the work log, `final_answer` feeds the response. Phase-less deltas wait for message completion to avoid temporarily displaying late-labelled commentary as the answer. Providers without phases retain the legacy completed-answer path.
- `native_work_log.v1` contains public commentary, public plans, references to already-projected tool receipts, provider compaction notices, stage, duration and completion/Stop/failure state. Raw reasoning, reasoning summaries, system/auth/hook payloads and other thread/turn events are never copied. No private chain-of-thought is requested or exposed. Agent instructions request brief public work updates, not private reasoning.
- Display bounds: 96 timeline entries, 4,000 characters per commentary, 12 plan steps, 100 ms coalescing for partial updates. Commands/output/diffs remain in the existing bounded agent receipt, not duplicated in the work log. This projection performs no extra model, memory, command, telemetry or export call.
- The Native timeline expands during work and can be reopened after completion. Tools disclose their observed output/status; interruption preserves available partial evidence and never claims rollback. Work logs persist only with Native messages as an optional history v3 field; v1/v2/v3 archives without it load without rewrite or fabricated progress. The model-history projection and core evaluation receive the final answer, not this log. In-flight logs are still not crash-durable or secret-redacted.
- Follow-latest scrolling waits for new content layout and, on macOS 15+, distinguishes user scrolling from output growth. macOS 14 keeps the conservative near-bottom fallback. A jump-to-latest button remains available; no persistent scroll settings are added.

Checkpoints: `backups/proto_mind_backup_2026-08-31_09-55-03.tar.gz` and `backups/proto_mind_native_history_2026-08-31_09-55-17_chat_ui.tar.gz` (conversations/preferences only, no credentials).

Acceptance evidence: 16 new Python stream/privacy/scope/failure/bridge tests and 13 new Swift history/grouping/presentation checks. A disposable code-only project/profile uses clearly labelled synthetic timed events to verify the real UI's live commentary, plan, tool disclosure, final-answer separation and Stop behavior; it does not execute those fixture tools. A separate real subscription chat adapter probe returned `Checking the reply format.` only in public commentary and `Proto-Mind public progress verified.` as the exact final answer in one 5.3-second turn, with no tools or personal project context. This verifies the installed account/default model, not every future provider or model phase implementation.

Personal data preservation: all 48 core/export SHA-256 values plus personal Native `conversations.json`/`preferences.json` remain unchanged. Context Injection remains disabled. The already-approved cloud authentication controller may update its own private profile state; that is not a core data/history preservation claim. No new command prefixes, categories, Full Mac authority, reasoning-effort selection, or background tasks are added.

## v4.0f: Native Material / Model Controls

Native 0.6.0 adds the operator-requested sidebar/typography and working model/effort menus, not new tools or an authentication migration:

- Sidebar material is a native `NSVisualEffectView` with `.sidebar`, `.behindWindow` and active-window tracking. System Reduce Transparency uses an opaque fallback; text is not made transparent. System typography is 14 points for conversation/interface text and 12 points for fenced/inline code and tool output, using macOS font rendering.
- The composer shows the selected model and effort together. Model and Effort submenus have checked choices, a catalog-default option, refresh and reset; Settings uses the same per-conversation state. Provider selection remains separate, preserving local Ollama and explicit Mock.
- Official [app-server model capabilities and turn settings](https://learn.chatgpt.com/docs/app-server) supply `supportedReasoningEfforts`, `defaultReasoningEffort` and `turn/start.effort`. The adapter projects only public picker fields and reads at most five 100-model pages, refusing incomplete/cyclic catalogs. Both chat and Full Mac revalidate before creating a generation turn. Model/effort settings do not become Observer intent, user input or permission grants.
- Optional history v3 `reasoningEffort` is empty for old conversations; loading never migrates or writes the archive. Explicit selection/reset updates only Native history. A manual switch to an incompatible model resets effort with a visible notice; catalog refresh alone preserves the stored choice and warns. Stale/unknown models or unsupported efforts refuse generation without silent substitution. Active turns freeze controls.
- At the original v4.0f acceptance, the installed Codex 0.136.0 catalog reported GPT-5.5 (default), 5.4, 5.4 Mini, 5.3 Codex and 5.2; supported levels were low/medium/high/xhigh. It did not expose the Desktop screenshot's 5.6/Max/Ultra. No entries were invented and no CLI update was part of that UI patch. The subsequent runtime update below verifies actual 5.6 access independently.

Checkpoints: `backups/proto_mind_backup_2026-08-31_11-07-24.tar.gz` and `backups/proto_mind_native_history_2026-08-31_11-07-42_model_ui.tar.gz` (history/preferences only). All 48 core/export hashes plus personal Native conversation/preferences hashes remain unchanged; Context Injection remains disabled.

Acceptance: 13 additional Python tests and 17 Native checks cover metadata projection, catalog pagination/drift, actual chat/agent effort payloads, unsupported-choice refusal before generation/Full Mac launch, operator bypass, legacy/read-only loading, per-chat persistence, defaults, reset and typography. Isolated UI smoke uses a clearly synthetic provider in a temporary code copy: actual menu selection reaches `turn/start` with `effort=xhigh`, survives restart, and resets visibly when a smaller fixture model does not support it. This is not a claim of real 5.6 account access. A separate live tool-free GPT-5.5 adapter probe sends `effort=high` and returns `Proto-Mind reasoning selection verified.` with unchanged chat isolation; it sends no project context and does not run the core or write personal chat history.

### Sidebar overflow correction (2026-08-31)

The v4.0f library disclosure previously increased the non-scrollable sidebar height and displaced the window's chat/composer. Navigation, disclosure, search and conversations now live in one height-bounded scroll view; the brand/new-chat header and settings footer stay fixed. Expansion state remains in-memory only. No model, access, history schema or core behavior changes.

Checkpoints: `backups/proto_mind_backup_2026-08-31_11-42-58.tar.gz` and `backups/proto_mind_native_history_2026-08-31_11-44-26_sidebar.tar.gz`. Six native checks cover unchanged minimum height, 320/600/820-point viewports, long conversation lists, search/empty results and no state writes. The release UI smoke verifies disclosure, collapse and sidebar-only scrolling at normal and short window heights using a code-only temporary profile. Verification: 1329 Python tests, 115 Native checks, compileall, PySide/tkinter imports and signed release build pass. This fixes layout, not the separate installed Codex catalog's model availability.

### Codex CLI refresh (2026-08-31)

The operator requested investigation of the missing GPT-5.6 Sol model and the suggested CLI 0.144.0 update. The actual Native runtime was the npm-managed `/opt/homebrew/bin/codex` at 0.136.0, not the binary bundled with Desktop. Version 0.144.0 exists, but the official [August 29 changelog](https://learn.chatgpt.com/docs/changelog) and npm registry identified 0.151.0 as the current stable release, including model/reasoning selection fixes. Version 0.151.0 was installed alongside the old runtime for compatibility probes before updating the existing global npm installation. No alpha or unverified model alias was used.

- The same isolated ChatGPT Plus profile returned GPT-5.6 Sol (catalog default), Terra and Luna after the update. Sol and Terra advertise low/medium/high/xhigh/max/ultra, Luna up to max; other catalog entries are not a promise that every model will accept a future request. No credentials, Desktop configuration, hooks or MCP settings were copied.
- Real tool-free Sol responses completed with `effort=medium`, `max` and `ultra` through the unchanged adapter and outer macOS sandbox. A separate full-access adapter smoke in an empty temporary folder executed exactly one `printf` command with exit code 0, a matching output preview, and no file-change events. These small compatibility probes do not benchmark model quality, quotas, long tasks or every tool. They bypassed the core turn pipeline and did not save personal chat history.
- Native was normally quit while idle, then reopened. Its real Model menu displays 5.6 Sol/Terra/Luna; the Effort menu displays Max and Ultra for Sol. The conversation retains catalog-default selection; the observed default effort is low. No stored model choice or permission was rewritten. Subagents remain disabled in the adapter, so accepting `ultra` is not evidence of the Desktop multi-agent mode described in the [model documentation](https://learn.chatgpt.com/docs/models).
- Verification after the runtime update: 1329 Python tests, 115 Native checks, compileall, environment guard, PySide/tkinter imports and real menu inspection pass. All 48 core/export SHA-256 values and both personal Native history/preferences hashes remain unchanged. Context Injection stays disabled. The auth controller may update its own private runtime/cache files outside those hashes.
- Project checkpoint: `backups/proto_mind_backup_2026-08-31_12-17-45.tar.gz`. History/preferences-only checkpoint: `backups/proto_mind_native_history_2026-08-31_codex_upgrade.tar.gz`. The old npm package, including its native binary, is retained in `backups/codex_cli_0.136.0_before_upgrade_2026-08-31.tar.gz`; archives were integrity-checked and contain no copied authentication profile. Rollback is an explicit reinstall/restore of that version followed by a Native restart, never an automatic response to a failed model turn.

This is a runtime compatibility update with documentation changes only. Native stays at 0.6.0; registry, core schemas, chat isolation, Full Mac grants and the public work-log contract are unchanged. Recheck the actual CLI path/version and account catalog if a future update changes availability; do not infer access from Desktop screenshots or a hard-coded model list.

## Local Versus Cloud

Ollama is the offline path. A ChatGPT/Codex subscription runs inference at OpenAI; it is not a downloadable local model and does not make cloud requests offline.

Native cloud permission is an explicit device-local opt-in, persisted from v4.0b and independent of Context Injection. When Codex is selected, the user message, up to 12 prior user/assistant messages (2,000 characters each), the core-selected memory/correction context, and explicitly attached file excerpts can be sent to OpenAI. Full Mac additionally permits tool-read data/output to be sent; there is no claim that these tools cannot read a full store or secret. Instructions are capped at 24,000 characters with an explicit truncation marker and safety footer. Internal reasoning events, auth payloads and background system notifications are not forwarded to the chat UI. Operator reports, marked operator inputs, failed sends and structured tool receipts are excluded from subsequent model history; a successful final answer may still describe a tool result. Plain library/file preview remains local even with cloud permission enabled.

Authentication uses the official [`account/login/start` ChatGPT flow](https://learn.chatgpt.com/docs/app-server), not token extraction from ChatGPT or an unofficial subscription endpoint. [Codex authentication documentation](https://learn.chatgpt.com/docs/auth) distinguishes subscription sign-in from separately billed Platform API keys. Account access, rate limits, and the model list are controlled by the user's subscription and the installed Codex CLI.

## EV-01: Reliable Work Sessions / Native 0.7.0

Implemented after the operator requested common hover feedback and authorized the curated roadmap's first package:

- `NativeInteractions.swift` supplies shared hover/press feedback for buttons, icon actions, menus and disclosure headers. Fill/outline change without hover-time layout scaling; disabled controls stay neutral, Reduce Motion disables the transition, and sidebar expansion keeps the existing fixed-height regression coverage.
- The toolbar's work-journal button shows bounded per-conversation run cards and an interrupted-work banner. Cards distinguish response receipt from task verification and operator acceptance; verification is `not_assessed`, acceptance is `not_recorded`. Observed exit codes or a completed response do not certify a goal. The UI never invents missing historical progress.
- `native_work_sessions.py` owns `work_sessions/<uuid>.json` in private Native state, schema `proto_mind.native_work_session.v1`. Directory mode is `0700`, record/lock mode `0600`. A cooperative `flock` writer spans one normal turn; temporary file + file fsync + atomic replace + directory fsync save each checkpoint. Known external record/folder/lock changes are refused, not overwritten. This is not a cross-process lock for the separate cognitive stores, nor a security boundary against Full Mac or arbitrary same-user file edits.
- A prepared record is durable before the normal handler is admitted. `dispatching` is durably saved immediately before that handler is called. A stopped/vanished writer with no dispatch is `not_started`; an unfinished dispatched turn is `unknown`, including incomplete tool observations. A durable completed response survives a lost UI reply. Reading/restarting never rewrites states, marks a task verified, or replays a target. Errors do not persist raw exception/provider payloads.
- Run identity is independent of provider thread IDs and bound to conversation, launch project and optional workspace path/device/inode. Stored content is bounded: input preview 800 characters, final response preview 1,600, at most 96 projected public progress entries and 64 observed tool items; tool output/diff/commentary excerpts are further reduced. Complete prompts, transcripts, credential/config fields and raw/private reasoning are not copied into this journal. Legitimate public input/output can still contain sensitive data: this is not secret-redacted or encrypted storage.
- A journal supports up to 500 runs, at most 256 KiB per file. UI responses show the newest up to 30 runs, also capped at 2 MiB of compact data. No deletion/rotation/pruning happens automatically. Corrupt/unreadable state or exhausted limits block new normal turns for manual review, rather than continuing without durable evidence. Read-only library/operator paths remain separate. An observed mid-turn persistence failure requests Codex interruption; prior side effects and detached processes may remain.
- `work_sessions` and `work_session_continuation` are read-only, Native-only RPCs, not model tools or new slash commands. Continuation quotes a bounded prior input/answer into a visible editable draft. It is reconstruction, not official `thread/resume`. The button refuses to replace an existing draft/attachment selection. Only a separate Send processes the draft; an optional history-v3 `draftContinuation` stores an ID/fingerprint, never permissions. Existing archives load unchanged, and only explicit draft editing saves that optional field.
- A prepared continuation rechecks the parent fingerprint, project/conversation/folder identity and original explicit attachment hashes. Send checks them again and admits at most one child for that parent under the writer lock. Duplicate run IDs never dispatch twice. Current cloud/mode/grant/model/effort gates still apply; no prior Full Mac grant, attachment or provider-session authority is restored. Replacing/unlinking a draft is an explicit fresh operator request, not a promise of global exactly-once side effects. Unknown historical outcomes stay visible after a child finishes; this first slice has no automatic reconciliation or acceptance writer.

Rule 0 evidence: `backups/proto_mind_backup_2026-08-31_12-37-51.tar.gz` and `backups/proto_mind_native_history_2026-08-31_12-38_hover_sessions.tar.gz` (conversations/preferences only, before the new journal existed; no credentials copied).

Verification adds 27 Python regressions and 24 Native checks to the pre-change baseline: real child-process exit after dispatch, interruption before dispatch, lost completed reply, duplicate IDs/events/continuations, corruption/symlinks, disk-full before/during processing, external edits/lock replacement, bounded reads, explicit-source drift, no inherited consent/grants and backup/restore. A disposable private-state restore preserves completed versus unknown evidence without starting work. The real-window UI smoke uses clearly synthetic run records and one actual local Mock continuation; its tool text is not executed. No live cloud generation or real-project edits are needed for this acceptance.

Private backup/rollback: close Native windows after active work has stopped; make a private copy of `conversations.json`, `preferences.json` and the complete `work_sessions` directory together. This is separate from `/memory backup`; do not include the Codex credential profile in a source/archive submission. Inspect restored state first in an alternate `--state-dir` with the same project binding, as the fixture restore test does. Never rewrite an unknown record to completed or clear an ID to force retry. Downgrading the app does not convert these files; retain the journal and make a separate reviewed restore plan before using an older client to edit a continuation draft. No automatic restore, repair or backup UI is installed by EV-01.

## EV-02: Context And Artifact Desk / Native 0.8.0

Delivered text-first slice after the operator's model-menu hover report and explicit request to start EV-02:

- The model menu takes its intrinsic width before applying hover feedback, with a 32-point minimum height. The highlight no longer covers unused space in the composer; model/effort choice and permissions are unchanged. Native layout tests vary the available width.
- The composer's Context button opens `ContextDeskView`. Native-only `context_preview` performs local no-write inspection of the actual bounded history and explicitly selected file excerpts: at most three supported UTF-8 files, 6,000 characters each, 12 history messages of up to 2,000 characters. Each source shows expected/current SHA-256, available/changed/unavailable state and its exact eligible excerpt. Changed files expose no newly selected content; the normal Send path retains its independent hash revalidation.
- The desk identifies Codex/OpenAI cloud, loopback Ollama, Mock or an operator route and shows existing cloud consent without contacting a provider or changing a grant. Normal core recall/correction context is selected at send time, not falsely predicted by this preview. The completed-turn inspector remains the source of actual recall evidence. Core memory is shared under the launch project, not isolated by a conversation's folder binding. Full Mac may read other files/use the network after Send; this manifest is not a tools sandbox, privacy scrubber or complete provider prompt.
- `native_desk.py` projects a compact `proto_mind.native_context_manifest.v1` into new ordinary run records: source hashes/limits, input hash/count, history counts, requested provider/model/effort, workspace, core-memory scope and observed injection setting. It does not persist complete source excerpts or chat history. It is recorded by the existing private single writer, not by opening a view. Operator inputs still create no work-session records; core/session schemas and Context Injection are unchanged.
- The work journal's Results tab uses `artifact_list` / `artifact_preview`, bound to a saved run ID/fingerprint, conversation and launch project. Up to 24 observed file-change paths have source tool/run references. New normally completed turns capture supported source-file SHA/size/time using the existing bounded no-follow reader, only inside the unchanged selected workspace identity. Metadata lives in optional `proto_mind.native_artifacts.v1` within the same atomic private run record. Symlinks, credentials, core stores, exports and outside-workspace paths are not previewed, regardless of broader Full Mac authority.
- A manual artifact inspection compares current bytes against the hash observed at completion. A changed file is labelled current/stale rather than silently presented as the old result. Missing/binary/excluded paths are diagnostic. Legacy/interrupted runs have no fabricated historical hash and are not rewritten. The original hash is known only for a matching explicitly selected input attachment; no original file bodies or intermediate versions are retained. Multiple file-change events can share the final completion hash, which is not the state after each individual edit.
- Saved diff fragments remain the bounded preview of the entire source tool event, not a reconstructed complete per-file patch. Command output/exit-code evidence, the model answer, unstructured success criteria, unassessed goal verification and unrecorded manual acceptance are separate. Exit zero does not prove that tests ran or the task succeeded. HTML/scripts are shown as plaintext; preview never opens an interpreter, repairs files, sends data, replays a command, restores a file or writes acceptance.

Limits at 0.8.0: this is not the full EV-02 acceptance. Structured criteria/manual assessment follow in 0.9.0 below. Binary images/PDFs, side-by-side patch reconstruction, open/reveal/restore actions and project-memory isolation remain follow-ups. Files created only through shell commands without file-change events are not discovered. Hashes are read at normal turn completion, not at an atomic tool transaction or crash; they are not signed evidence, exclusive agent authorship proof or secure rollback data. Existing 500-run / 256 KiB-record / 30-row-page limits and separate private backup remain in force.

Verification: 31 new Python regressions cover exact selected excerpts, stale sources and Send refusal, core-scope disclosure, no preview-time provider/command calls, malformed manifests, protected/symlink/traversal reads, no grants, compact persistence, run/project/conversation/workspace drift, legacy/unknown states, bounds, plaintext HTML, and a scripted adapter with one fixture edit plus observed verification. Native adds 31 checks (including the hover fix) for layout, actual RPC/UI models and no-write behavior. The live isolated-window smoke uses synthetic run evidence, an actual two-assertion local Python fixture, fresh/stale files, diff/current-source views and command output; no cloud generation or real-project tool edit is part of this acceptance.

Rule 0 evidence: `backups/proto_mind_backup_2026-08-31_13-42-39.tar.gz` and `backups/proto_mind_native_history_2026-08-31_13-43_ev02.tar.gz` (conversations/preferences only; the personal work journal was absent, and credentials were not copied). All 48 personal core/export files and personal Native conversations/preferences retain their SHA-256; Injection remains disabled, Registry 387/41, accepted findings 12 and unknown 0.

## EV-02: Criteria And Manual Acceptance / Native 0.9.0

Delivered as the next bounded desk increment, without extending tools or automatically declaring success:

- The composer checklist opens **Готово, когда…**. The operator may save up to eight unique one-line criteria, 300 characters each, in optional history-v3 `pendingCriteria`. Opening/cancelling the editor writes nothing; explicit Save persists only the private draft. Existing history loads an empty list without migration. The Context desk shows the exact criteria before Send.
- Normal Send freezes `proto_mind.native_success_criteria.v1` (operator-before-send origin, stable item IDs/text and SHA-256) into the private run and context manifest. Only the native Codex/Ollama reasoner prompt gets the requirement prefix; raw Observer input, cognitive memory evaluation and session-log schema stay unchanged. Empty criteria preserve old prompt behavior. No second model call or permission is added. Successful normal Send consumes the draft; failures retain it. Slash/natural operator commands exclude and retain it. Mock explicitly does not evaluate criteria.
- The work journal adds **Приёмка** beside Overview/Results: read the original criteria, personally mark each met/not met/not checked, choose accepted/needs work and optionally add a note of up to 1,000 characters. A local `review_preview` rereads saved evidence/current observed files; a second sheet displays the exact assessment before explicit `review_save`. Merely selecting checks, previewing or cancelling never writes.
- Acceptance requires normal completion (including completed agent status when present), non-empty criteria frozen before Send, every item marked met, the same workspace identity and complete matching completion-hash observations. Changed, unavailable, uncaptured or partial artifacts refuse acceptance. Text-only runs with an explicitly captured empty artifact set can be assessed by the operator; this is not a claim that files or code were verified. Unknown/interrupted/failed work cannot be reviewed into success. Legacy runs without declared criteria cannot be accepted retroactively, but a normally completed legacy run can receive a needs-work note without invented hashes/criteria.
- Saving holds the same cooperative writer lease, checks exact source bytes/run fingerprint, re-reads observations and compares the preview fingerprint including choices/note, then atomically fsyncs one private run. It changes only `operator_reviews`, `acceptance` and `updated_at`; core stores, exports, conversation history, grants and target files are untouched by this operation. Wrong scope, active writers, stale/replayed previews, storage errors and detected external edits refuse without automatic retry. The receipt does not invoke the original command/model, repair files, promote memory or grant a future run.
- `proto_mind.native_operator_review.v1` stores UUID/run/time, operator-reported decision/checks/note, evidence SHA, observed current/completion hashes and workspace/completeness flags, `no_execution:true`, `automatic_verification:false`, previous receipt hash and stable receipt hash. Up to 12 assessments are retained; another explicit assessment appends without deleting earlier decisions. No automatic pruning. Final manual state is `operator_accepted` or `operator_needs_work`; the run's original status and `verification:not_assessed` remain unchanged. Readers validate criteria, receipt hashes/chain and evidence consistency. Native cards display manual state, individual historical checks and current artifact drift separately.

Safety ceiling: this is manual assessment, not an automated verifier, human-identity signature or immutable audit. A same-user Full Mac process can edit private files; hashes detect inconsistent evidence but are not a secret-backed signature. File checks are bounded observations before saving, not a filesystem freeze: later changes do not rewrite historical acceptance. No image/PDF support, restore, task auto-apply, provider-thread resume or project-memory isolation is added. Existing successful-normal-turn core writes and Full Mac's broad optional authority remain as previously documented.

Compatibility/rollback: back up private conversations/preferences/work_sessions together before a downgrade; preserve the evidence rather than having an older client rewrite new fields. No read-time migration or automatic repair occurs. Receipt-free old runs still load unchanged. The existing private record size/capacity limit still applies, including review history.

Verification: 37 new Python regressions and 26 Native checks bring totals to 1,424 / 196. Coverage includes raw-input preservation, criteria bounds/operator bypass, no extra provider/tool grants, no-write preview, one-file save, replay/concurrency/CAS/disk failure, stale/symlink/workspace evidence, legacy/unknown states, contract/receipt/chain corruption and bounded history/restart. UI smoke uses disposable state, a synthetic run backed by two real local fixture assertions, and one explicit Mock message: cancel/save criteria, exact Context preview, unchecked/stale refusal, confirmation cancellation, manual acceptance, results labelling and later needs-work history. No live cloud/Ollama generation or real-project target edit is part of this acceptance.

Rule 0: `backups/proto_mind_backup_2026-08-31_14-30-48.tar.gz` plus `backups/proto_mind_native_history_2026-08-31_14-33_ev02_acceptance.tar.gz`. The personal journal was absent and remains absent; no credentials copied. All 48 core/export files and personal Native conversations/preferences retain SHA-256. Context Injection remains disabled; Registry remains 387 commands / 41 categories, accepted-known findings 12 / unknown 0.

## EV-02: Selected Image Inputs / Native 0.10.0

The next bounded input increment adds saved images without screen access, a new model tool or automatic cloud permission:

- Composer **+ > Изображение или скриншот…** opens an explicit PNG/JPEG file picker, not screen capture. A local sheet shows the decoded image, original dimensions, bytes, path, SHA-256 and cloud/privacy notice. Attach is a separate gesture; cancel/preview never writes. Selected images appear as removable thumbnail chips. The Context desk shows current readiness and hashes; message/journal views retain source metadata and never silently reattach old pixels.
- `native_images.py` accepts regular selected files, including outside the bound workspace, while excluding credentials, hidden/generated/backup paths, current core stores/exports and Native private state. Every path component is opened no-follow; only the verified macOS `/var` and `/tmp` system aliases are normalized to `/private/...`. Arbitrary symbolic links, traversal, URLs, extension/MIME mismatch and unreadable/changing files fail closed. Limits: three images, 4 MiB per file / 8 MiB combined, side length at most 16,384 and at most 24 megapixels. PNG chunk framing/CRC/IHDR/IDAT/IEND and JPEG frame/scan/end markers are checked; APNG and unsupported JPEG variants are refused. This is bounded container validation, not a complete Python codec/security scanner. Native ImageIO separately verifies decoding/type/dimensions and produces an in-memory display thumbnail up to 1,440 pixels.
- `image_preview` returns a bounded read-only DTO with one selected image for local rendering. Swift validates schema, hash, sizes and ImageIO result. Pending/message metadata uses `proto_mind.native_image.v1`: path, name, MIME, dimensions, byte count and SHA only. Explicit attachment/removal uses the existing atomic private history writer with rollback on save failure. History format v4 preserves older v1/v2/v3 reads without rewriting; older clients reject v4 rather than losing image fields. Back up private state before downgrading; do not force an older writer onto a new archive.
- Normal Send rereads each chosen source, compares its selected SHA and freezes immutable bytes. It requires the existing cloud consent and a Codex model explicitly advertising image input in the current `model/list` catalog. Unknown/missing capability is refused conservatively, not assumed from a model name. The existing [official app-server contract](https://learn.chatgpt.com/docs/app-server) receives `turn/start` image data URLs beside the text input; no local file path is handed to the provider. Both isolated Chat and separately granted Full Mac share this transport. Chat's sandbox is unchanged, and selecting an image never grants tools. RPC line limits remain bounded; large/partial pipe writes are handled without truncating image JSON.
- Image input currently supports Codex only. Ollama/Mock refuse selected-image turns rather than ignoring pixels, pretending to analyze them, changing provider or enabling cloud. Slash/exact natural operator commands exclude and retain pending images. Failed normal sends retain draft/attachments; successful sends consume them. Empty image input preserves previous adapter behavior. Original Observer/log text, core memory rules and Context Injection remain unchanged.
- Only metadata is stored in private Native history and the optional work-session/context manifest; no original image bytes or data URLs are saved there. Opening history never rereads image paths. Bounded model-history entries explicitly mark older image pixels as absent; continuation also requires manual reattachment. A prior textual answer can remain in normal chat history, but that is not a fresh visual observation. Reopening a saved attachment locally rechecks the original file hash and writes nothing. No automatic original copy, disk thumbnail cache or repair of missing sources exists.

Privacy and scope: Send transmits the original selected file, including embedded EXIF/other metadata. No automatic redaction, recompression, OCR, clipboard import, screen capture, PDF/HEIC/GIF support, local-provider vision or generated-image workflow is added. Thumbnails are display-only; they do not sanitize the original. This feature does not claim project-memory isolation, change successful-normal-turn cognitive writes or expand Full Mac authority. Source paths in private history are not a redacted export. Codex manages its separate profile and remote processing; metadata-only claims apply to Proto-Mind's history/journal, not a promise about provider retention.

Verification: 24 new Python tests and 22 Native checks bring totals to 1,448 / 218. They cover format/bounds, protected/no-follow paths and system aliases, stale sources, immutable payloads, catalog/provider/consent refusals, operator bypass, metadata-only journal/history, old-history compatibility, decode/hash corruption, stale async UI results, save rollback and no automatic image replay. A release-window smoke on disposable state covers picker/preview cancellation with byte-identical history, explicit attachment, Context source/cloud notices, cloud-disabled Send refusal with retained draft, and removing the attachment without touching its original. No cloud request or work-session record is created by that refused UI send.

A separate live adapter smoke used current Codex 0.151.0 and catalog-confirmed `gpt-5.6-sol` at low effort, with one generated 192 x 128 PNG containing colored shapes. Sol correctly described the red background, blue circle and yellow shape. The probe used no personal image, chat history, memory or tools and did not enter the normal cognitive writer. This verifies one image transport/answer path, not all vision tasks/models, OCR accuracy or live Ollama. Existing official credentials/profile remained in place, without copying credentials.

Rule 0: `backups/proto_mind_backup_2026-08-31_15-34-04.tar.gz` plus `backups/proto_mind_native_history_2026-08-31_15-35_ev02_images.tar.gz` (conversations/preferences only). All 48 core/export SHA-256 values and personal history/preferences are unchanged; personal work_sessions remains absent. Context Injection disabled; Registry 387 commands / 41 categories, accepted-known findings 12 / unknown 0. The rebuilt separate app is Native 0.10.0; CLI/PySide/tkinter remain available.

## Attachment Recovery And Drop / Native 0.10.1

Focused fix for the operator's saved-image report, without deleting the failed turn or changing the wider EV-02 boundary:

- The pending image's vertically fixed-size notice expanded during `NavigationSplitView` minimum-width probes. It could push both sidebar content and composer outside the window and recur after restart because the attachment draft was preserved. Bounded wrapping (three lines plus full tooltip) and fixed-height image/file strips keep the layout within the viewport. The image picker now uses an asynchronous sheet/panel, not a nested modal run loop.
- Finder may launch with only `/usr/bin:/bin:/usr/sbin:/sbin`. The npm Codex launcher was found at `/opt/homebrew/bin/codex`, but its `/usr/bin/env node` could not find Node. The existing minimal child environment now includes known Homebrew/system runtime directories, deduplicates them and drops relative PATH entries. Private HOME, config isolation, authentication profile and both tool policies are unchanged. Local EOF uses an internal sentinel and reports a startup/transport failure instead of fabricating a provider JSON-RPC error. Failed requests are never automatically retried.
- `AttachmentDrop.swift` accepts local file URLs in the chat and AppKit composer. It loads bounded URL payloads with a ten-second provider timeout, rejects remote/decorated/duplicate URLs and keeps no file promises. Up to three PNG/JPEG images and three supported UTF-8 files use existing read-only readers. Text must be inside the already-bound workspace; dropping never copies it or changes the binding. Existing image limits/protected-path checks are unchanged.
- A local batch sheet shows thumbnails/excerpts, hashes and destination notice. Cancel/preview writes nothing. A separate Attach revalidates conversation/workspace and saves both metadata arrays together in existing private history v4; stale results, invalid batches, overflow and save failure cannot partially attach. Send remains separate and blocked while a preview is loading/open. Image bytes and text bodies are not persisted by attachment; history reload does not resend them.

Verification: five new Python tests and 49 Native checks bring the totals to 1,453 / 267. Coverage includes minimal Finder PATH, early EOF versus real provider errors, minimum-width image-notice sizing, large PNG plus mixed text, provider timeout/late callbacks, native editor drop without path insertion, stale conversation/workspace, duplicates/out-of-scope/symlink/unsupported files, cancellation, save failure and metadata-only restart. Sources/core hashes remain unchanged in fixtures.

The live disposable UI reproduces the broken saved-image window before the fix and confirms restored sidebar/composer afterward. Native file-URL drag gestures into the chat (text) and composer (3.7 MB image) open the local batch sheet; Attach, Cancel and the original + picker work without Send. The temporary in-window drag source was removed before the final release build. Cross-window Finder automation was inconclusive, so it is not claimed as a verified gesture path; the same file-URL/pasteboard contracts have direct integration tests.

A real installed Codex 0.151.0 initialization passes with Finder's minimal PATH and an isolated signed-out profile. A separate tool-free `gpt-5.6-sol` low-effort call uses only a generated 1,448 x 850, 3,694,443-byte noisy PNG and correctly describes colored static. It uses the existing separately authorized Native profile without copying credentials; no personal image/history/core context is submitted and no cognitive writer is invoked. This is one runtime/large-image transport check, not model-quality or general image-format certification.

Rule 0: `backups/proto_mind_backup_2026-08-31_17-31-52.tar.gz` and `backups/proto_mind_native_history_2026-08-31_17-33_attachment_fix.tar.gz`. The second private archive now includes the existing failed-run `work_sessions` record/lock with conversations/preferences, never credentials. All 48 core/export SHA-256 values and private history/preferences/work-session hashes are unchanged. Context Injection stays disabled and Registry stays 387/41. No historical repair, auto-retry, new grant, OCR/PDF/HEIC support or source conversion is introduced.

## Run Notices And Review Availability / Native 0.10.2

The old unfinished image request remained `unknown` after later successful replies. Its banner had no dismissal action, opened the newest run instead of the affected run, and the Acceptance tab showed an entirely disabled editor without explaining that no completed answer was available.

- A banner X and journal Hide/Show buttons now change only a display preference in `conversations.json`. The original run remains visible with its original unknown/not-started outcome. The banner opens that exact run. No retry, repair, deletion, acceptance or permission change occurs.
- The optional history-v4 `dismissedWorkSessionWarnings` field contains at most 500 unique run UUID/fingerprint/state tuples per conversation. Reads of old history do not rewrite it. Only the observed matching revision is hidden; changed/new run evidence warns again. Busy/stale/wrong-conversation writes refuse, repeat hiding is a no-write operation, and failed saves restore the visible warning. This is not an authorization or audit record. Journal storage diagnostics are never suppressed by this preference.
- The Acceptance tab explains running, unstarted, unknown or inconsistent states and the review-history limit, rather than displaying dead controls. Completed replies without predeclared criteria start at `needs_work` and require a comment. Completed replies with criteria keep the existing per-criterion choices, read-only preview and separate save confirmation. Backend eligibility, evidence hashes, review limits and core stores are unchanged.

Verification: 1,454 Python tests and 299 Native checks pass, including one new backend regression over both decisions on unstarted/dispatched-incomplete requests and 32 Native checks for dismissal, restart, stale/new evidence, non-dismissible storage diagnostics, malformed/legacy preferences, save rollback and review availability. Compileall, Python/PySide/tkinter imports, release build, plist and signature checks pass; optional pytest is not installed.

Live UI smoke uses `scripts/native_smoke_fixture.py <new-temp-project> --notice-state <new-temp-state>` with three synthetic run records, never personal conversations. Banner-to-run navigation, Hide/Show, X and restart persistence pass. Completed no-criteria rework and completed declared-criteria acceptance reach separate confirmation previews; Cancel writes nothing. A legacy synthetic run without artifact evidence remains refused rather than receiving invented hashes. Only explicit hide/show changed the fixture's conversation file; run files remained byte-identical. No provider or tool was called.

Rule 0: `backups/proto_mind_backup_2026-08-31_18-44-41.tar.gz` and private `backups/proto_mind_native_history_2026-08-31_18-48-18_notice_review.tar.gz` (conversations/preferences/work_sessions only, no credentials). All 48 core/export files, both personal conversation/preferences files and four personal journal files retain their SHA-256 values from this task's checkpoint. Context Injection remains disabled; Registry stays 387 commands / 41 categories. Personal notices are left for the operator to dismiss with the new control, not silently acknowledged by installation.

Limitations: hiding is not reconciliation or proof that a failed request had no effects; historical error messages remain in the transcript. The journal still shows a bounded last-30 list. Corrupt/unreadable journal diagnostics require inspection. Criteria cannot be added to old runs retroactively, and no automatic task verification is introduced.

## EV-02: Selected PDF Page Text / Native 0.11.0

The earlier drag/drop implementation supported PNG/JPEG and workspace UTF-8 files, not PDF. PDF consequently fell into the workspace/text refusal path. This increment adds an explicit text-PDF workflow rather than suppressing that diagnostic.

- Drop one local PDF onto chat/composer, or use **+ > PDF**. Page 1 opens locally; select up to eight pages (for example `1-3, 7`), then Read pages. The exact bounded text, empty-page and truncation notices appear before Attach. An edited page selection cannot attach until refreshed. Attach and Send remain separate; Return while previewing cannot send a turn.
- Limits: one PDF, 8 MiB, 300 document pages, eight selected pages, 3,000 Unicode characters per page. Drop the PDF separately from image/text batches; it can coexist with already selected images/text. Explicit PDFs need not be inside the workspace, but protected/hidden/generated paths, symlinks, nonregular files and unsafe URLs remain excluded.
- `native_pdf.py` reuses the existing protected no-follow byte reader. A fixed bundled `ProtoMindPDF` worker uses Apple PDFKit over stdin with no source-path argument or inherited credentials. OS policy denies network/file writes; timeout is 12 seconds and CPU limit eight seconds. No file conversion cache, helper chosen by RPC, shell command, dependency, password attempt or cloud fallback. Damaged, encrypted/copy-restricted and unavailable documents fail visibly.
- Only selected text is quoted into the Native Codex/Ollama prompt. PDF instructions are untrusted source data; page citations are requested but not claimed automatically verified. Original PDF/images/layout and unselected pages are not uploaded by this attachment path. No OCR; all-empty/scan-only selections cannot attach. Truncated selections explicitly say they are incomplete. Mock remains a labelled UI fixture, not document analysis.
- Send revalidates the original SHA-256 and exact selected-page text hashes/counts before a work session/provider call. Operator commands bypass/retain attachments. Context Desk shows the same text and staleness. Only metadata (path/name/document SHA/page numbers/text hashes/bounds) enters private conversation history v5 and optional run manifests. v1-v4 load without a rewrite; old binaries cannot silently discard v5 inputs. No automatic source/text reattachment on restart, continuation or later turns.
- Privacy ceiling: normal answers may quote document text and are still ordinary persisted chat history; provider retention is separate. Full Mac remains a separate broad grant and may access other files independently. This patch does not change cognitive memory rules, global project-memory scope, the session log schema or Context Injection.

Verification: 1,471 Python tests and 346 Native checks pass. New coverage includes read-only preview, selection/truncation, malformed metadata, changed bytes/text, permission-before-read, exact Codex/Ollama adapter inputs, operator bypass, no next-turn replay, history rollback and real sandboxed PDFKit extraction including Cyrillic and encrypted-PDF refusal. Native layout probes cover narrow/zero-width PDF chips. Build, compileall, CLI/PySide/tkinter imports, plist and signatures pass; optional pytest is absent.

Live release UI smoke uses `scripts/native_smoke_fixture.py <new-temp-project> --pdf-state <new-temp-state>`, not personal data: PDF picker, page-2 refresh with attach disabled until preview, compact attachment, Context Desk, restart persistence and explicit Mock-only Send pass. Finder-style pasteboard and AppKit composer drop dispatch are integration-tested; a physical cross-window Finder gesture is not independently certified by this UI automation. No live Codex/Ollama document-quality claim is made.

After returning to the personal profile, all 48 core/export files and six personal conversation/preferences/work-session files retain their pre-change SHA-256 values. Context Injection remains disabled. Tests use synthetic PDFs only; no user document or new live model request was used.

Rule 0: `backups/proto_mind_backup_2026-08-31_20-19-00.tar.gz` plus private `backups/proto_mind_native_history_2026-08-31_20-23-37_pdf_input.tar.gz` (conversations/preferences/work_sessions, no credentials). Registry remains 387 commands / 41 categories. The full EV-02 package remains open for visual/scanned documents, local-provider vision, richer artifacts and project-memory isolation.

## Durable Codex Sessions / Native 0.12.0

Native conversations now continue the provider-side Codex thread instead of rebuilding provider continuity from local chat history on every turn.

- The first Codex Send for a Native conversation calls non-ephemeral `thread/start`, validates the returned ID/cwd/sandbox/approval/instruction-source policy, then atomically stores only the conversation UUID, provider thread ID, exact optional workspace identity, timestamps and last model/mode. Up to 12 bounded local user/assistant messages are quoted once as bootstrap state. No prompt or credential enters the binding file.
- At the 0.12.0 milestone, later isolated-chat and explicitly granted Full Mac turns called `thread/resume` for the same ID while revalidating cwd, model, sandbox and policy. Native 0.14.1 corrects that design: developer instructions are durable provider-thread state, so Chat and Full Mac now use separate mode-bound threads rather than attempting to replace instructions during resume.
- Each mode binding survives Native/bridge restart. Full Mac authorization does not: it remains an in-memory, conversation/workspace-bound grant and must be enabled again. Switching modes creates or resumes that mode's own thread; its first turn receives one bounded local-history bootstrap.
- Model Settings shows new/resumable/mismatched state and a short non-secret identifier. **Start New Codex Session** requires a separate destructive confirmation, revokes any live agent grant and removes one local binding. It does not call the provider, delete local chat/work-session evidence or remove the old provider rollout. Context Desk shows whether Send will create or resume and whether bounded local history is included.
- `codex_threads.json` is a 500-binding / 512 KiB private atomic store. No-follow reads, strict schema/identity validation, `0600` files, `0700` state, duplicate refusal and write blocking on malformed state preserve evidence rather than repairing it. Atomic-replace failure leaves the previous file. There is no automatic pruning, merge or migration.
- The separate Codex profile now uses `history.persistence=save-all`, required for restart-safe resume. Codex rollout files may include prompts, replies, selected source content and tool output. They are not redacted Proto-Mind exports, are not covered by `/memory backup`, and currently have no Native retention/delete/export UI. Back up or remove provider history only as a separate, deliberate profile operation; the small binding file alone cannot restore missing rollouts.

Rule 0: `backups/proto_mind_backup_2026-09-01_07-47-09.tar.gz` plus private `backups/proto_mind_native_history_2026-09-01_0749_durable_threads.tar.gz` (existing conversations/preferences/work_sessions only; no credentials or Codex profile). Verification: 1,488 Python tests and 348 Native checks pass, including store corruption/symlink/atomic-write failures, one-time bootstrap, same-process and restarted resume, no hidden fallback, policy/workspace drift, chat/Full Mac/chat transitions, status/reset RPC and context UI contracts. No personal model turn was used for this implementation acceptance; first live two-turn/restart continuity remains an operator smoke. Registry stays 387/41 and no dependencies, slash commands, core schemas or Context Injection changes were added.

## Full Mac Live Web Search / Native 0.13.0

Native 0.13.0 gives explicitly granted Full Mac sessions current public-web lookup without changing ordinary chat:

- Default chat retains strict `web_search=disabled`, `tools.web_search=false`, disabled shell/unified execution and the existing outer process isolation. It cannot silently inherit the Full Mac network capability.
- A live, conversation/workspace-bound Full Mac grant starts Codex with `web_search=live`, Web Search enabled and the existing Full Mac shell/unified execution settings. The grant is still held only in bridge/UI memory, is revoked on mode/reset/logout boundaries and is not restored after restart.
- Web Search activity is shown alongside terminal/file work. Receipts and durable work-session projections retain only a bounded query, recognized `search`/`openPage`/`findInPage` action and sanitized HTTP(S) page location. URL credentials, query strings, fragments, opaque provider result payloads and unknown fields are discarded; `network_access_performed` makes the boundary visible.
- Agent instructions treat every page/result as untrusted, prohibit putting local file contents, credentials or secrets into searches, and request material source citations. This reduces accidental leakage but is not automatic secret redaction or a comprehensive network audit.
- The UI now names the mode **Full Mac + Internet**, explains that search queries/pages are processed through OpenAI, and continues to expose visible activity, Stop and receipts. The official configuration surface is documented in the [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
- At the 0.13.0 milestone no interactive browser, browser cookies/login state, arbitrary URL navigation UI, Computer Use, Accessibility, Screen Recording, mouse/keyboard input, background browsing or automatic search was enabled. Native 0.14.0 adds the separately documented Computer Use path below; logged-in browser automation and background browsing remain unavailable.

Rule 0: `backups/proto_mind_backup_2026-09-01_08-37-08.tar.gz`. Targeted Python acceptance passes 131 checks, the full suite passes 1,491 tests, and Native acceptance passes 349 checks. Installed Codex 0.151.0 accepts the strict live-search configuration without starting a model turn. Release build, plist, signature and isolated UI disclosure smoke pass. All 48 core/export, three personal history/preferences/thread-binding and seven private work-session files retain their pre-change SHA-256 values. Context Injection remains disabled and Registry remains 387/41. No dependencies, slash commands, core schemas or persistent Full Mac grant were added.

## Full Mac Computer Use / Native 0.14.0

Native 0.14.0 adds GUI operation only to the existing explicit Full Mac mode:

- `native_computer_use.py` locates the canonical per-user `Codex Computer Use.app` and nested `SkyComputerUseClient`, rejects symlinks/non-executables, verifies both bundle IDs, OpenAI Developer ID authority and team `2DC432GLL2`, and reads the bounded installed version. Proto-Mind does not copy, modify or redistribute that proprietary OpenAI runtime.
- Ordinary chat remains unchanged: strict config keeps `features.computer_use=false`, `mcp_servers={}`, shell and Web Search disabled, under its outer read-only/no-network process sandbox. Login, bootstrap, file preview and saved history never grant screen access.
- A live Full Mac grant configures one required stdio MCP server, the verified client with argument `mcp`, a 15-second startup/90-second tool timeout, no parallel calls and exactly ten enabled tools: app inventory/state, click, drag, scroll, keyboard/text/value/selection and secondary accessibility action. Before generation, the app-server inventory must contain only `computer-use`, include the required tools and expose no unknown tool. Other MCP, plugins, hooks, browser and subagents remain disabled.
- `mcpToolCall` events are accepted only from that server/allowlist. The Native receipt/work journal keeps action type, status, bounded app name, duration and an explicit omission note. Arguments, screenshot/content results, accessibility tree, coordinates, pressed keys, typed/set/selected text and opaque MCP fields are never copied into Proto-Mind history. This privacy projection does not prevent the live screen/app content from being processed by OpenAI or retained under provider controls.
- The Full Mac confirmation names screen authority and the installed service version. The composer/settings/context desk distinguish available/unavailable Computer Use. Stop or the service's Esc takeover can interrupt the active turn but cannot undo an earlier click, typed text, submission, purchase, message or filesystem side effect. Agent instructions require a fresh app state around actions and a pause before consequential external actions; these are defense in depth, not a universal transaction/approval broker.
- No slash command, dependency, core/session-log schema, Context Injection behavior, background process or persisted Full Mac grant is added. Native version is 0.14.0 build 16.

Rule 0: `backups/proto_mind_backup_2026-09-01_09-12-48.tar.gz`. Targeted Native adapter suites pass 137 tests; the full suite passes 1,497 tests and Native acceptance remains 349 checks. Installed Codex 0.151.0 starts the strict configuration with signed OpenAI Computer Use 26.828.1000919 and exactly ten allowlisted tools. Model-free calls through the authenticated Codex app-server successfully list applications, read Calculator state, press a harmless key, re-read state and clear the input without printing returned screen/application data. A direct unauthenticated service call is refused by the installed runtime. Release build 0.14.0 build 16, plist and application signature pass; the personal app relaunches on that version. All 48 core/export files, three personal Native history/settings/binding files and seven private work-session records retain their pre-change SHA-256 values. Context Injection remains disabled and Registry remains 387/41.

## Mode-bound Codex Continuity / Native 0.14.1

Native 0.14.1 fixes a real cross-mode continuity failure without changing Full Mac authority or adding tools:

- A provider thread's original developer instruction is durable. Resuming a Chat-origin thread under Full Mac could therefore preserve the earlier no-tools instruction even though Proto-Mind correctly launched the Full Mac process and exposed Computer Use. The model then reported that it could see only the working folder while the run receipt truthfully showed zero tool calls.
- `codex_threads.json` v2 keys bindings by conversation and `instruction_mode`. Chat resumes only Chat; Full Mac resumes only Full Mac. The first turn of a missing mode creates a new provider thread and receives up to 12 bounded local messages once, preserving conversational continuity without sharing incompatible authority instructions.
- Existing v1 bindings are loaded read-only as `legacy_unknown`, preserved if the v2 store is later written, shown in Settings as historical, and never guessed or resumed as either mode. There is no provider-thread deletion, data rewrite on read, hidden fallback or automatic permission grant.
- Settings lists available mode sessions. Explicit **Start New Codex Session** still removes only local bindings for that Native conversation; it does not delete Native history or provider rollouts. Full Mac remains explicit and process-memory-only.

Rule 0: `backups/proto_mind_backup_2026-09-01_15-11-25.tar.gz` plus private `backups/proto_mind_native_history_2026-09-01_15-23-34_mode_threads.tar.gz` (conversations/preferences/bindings/work sessions only; no credentials or Codex profile). Verification: 1,500 Python tests and 349 Native checks pass. Release 0.14.1 build 17, plist and application signature pass. A real personal read-only turn migrated the v1 binding to historical `legacy_unknown`, created a distinct Full Mac thread and invoked `list_apps` plus `get_app_state`; the signed runtime protected ChatGPT's own state. A second turn resumed that Full Mac binding and successfully read Finder state using `get_app_state`, with no click/type/scroll/file action. All 48 core/export files, conversations, preferences and eight work-session records retained their pre-acceptance SHA-256 values; only `codex_threads.json` intentionally changed. Registry remains 387/41, Context Injection remains disabled, and no dependency, slash command, core schema, tool, provider permission or session-log format was added.

## Computer Use Fresh-State Guard / Native 0.14.2

A real personal Safari request exposed two sequential `get_app_state` failures, each at the previous exact 90-second MCP limit. The same signed Computer Use service read Safari in under one second when asked for a fresh state, and Proto-Mind then read it successfully with one explicit `disableDiff=true` call. The problem was a stale/diff observation path, not workspace isolation, account access, Safari permissions or the Full Mac grant.

- Every eligible Full Mac turn receives current runtime guidance even when its durable provider thread was created with older instructions. The first state read for each app must use `disableDiff=true`, because Proto-Mind intentionally does not persist or replay raw UI trees between turns.
- A timed-out `get_app_state` must not be retried under another display name or bundle identifier in the same turn. Non-timeout name-resolution failures may still use the normal app inventory path.
- The strict Computer Use tool timeout is now 30 seconds rather than 90. No parallel calls, automatic screenshot/shell fallback, UI activation, click, retry or extra authority is introduced.

Rule 0: `backups/proto_mind_backup_2026-09-01_15-42-53.tar.gz` plus private `backups/proto_mind_native_history_2026-09-01_15-47-13_safari_timeout.tar.gz`, excluding credentials and provider profile. Targeted checks, the full 1,502-test Python suite, 349 Native checks, Swift typecheck, plist validation and the signed release build pass. A live ordinary Russian Safari request resumed the existing Full Mac thread and completed with exactly one read-only `get_app_state` in 334 ms; no click, typing, scrolling, shell command or file action was observed.

## Agent Contract And Automation Onboarding / Native 0.15.0

Native 0.15.0 hardens the existing subscription-backed Full Mac path without replacing it:

- `native_agent_contract.py` freezes one deterministic pre-start contract containing the exact subscription provider, selected model/effort, canonical workspace device/inode, bounded input/output shape, shell/Web Search/Computer Use authority, ten-tool allowlist, 15-minute/64-item limits, no background execution, no automatic retry/rollback, fixed stop conditions, a digest of declared success criteria and separate operator acceptance. Contract text never retains the user prompt or criterion text.
- `CodexSubscription.agent_answer` attaches the contract before starting the Full Mac app-server process. The connected MCP inventory is then checked against the frozen allowlist before the provider thread starts. Contract/hash/inventory are displayed and optionally persisted only through strict public projections in the existing private work-session schema. Legacy records remain readable and are not migrated.
- `native_agent_evals.py` and `evals/native_agent_contract/cases.jsonl` provide six dependency-free local checks against the real guardrail functions: valid contract, refusal of auto-retry/background/allowlist drift/unknown MCP tools, and privacy-safe classification of macOS `-1743`. The runner prints JSON to stdout and writes no eval result store.
- The design patterns come from the locally installed official OpenAI Developers plugin. Proto-Mind does **not** adopt the Agents SDK runtime, API-key authentication, OpenAI Platform connector, Deployment Manager, a new provider, background agent or extra MCP authority. The separate ChatGPT subscription profile and Codex app-server remain the runtime.

The reported `Computer Use -1743` was isolated to macOS Automation authorization for the Proto-Mind caller chain. The same signed OpenAI service can list apps and read Safari through current Codex, while System Settings listed only ChatGPT under Automation and no Proto-Mind entry. Native bundle metadata now includes `NSAppleEventsUsageDescription`; the UI converts the exact bounded failure into an actionable notice and can open the Automation settings page. It cannot approve the prompt/toggle, bypass TCC, retry the action or claim recovery. A live Proto-Mind Computer Use acceptance remains pending until the operator grants the new macOS entry and starts a fresh Full Mac turn.

Rule 0: `backups/proto_mind_backup_2026-09-01_16-21-07.tar.gz`. The local agent evals pass 6/6, the full Python suite passes 1,510 tests, all 349 Native checks pass, and the release build/plist/ad-hoc signature verify. The rebuilt personal app relaunches as 0.15.0. All 48 core/export files plus conversations, preferences, thread bindings and 12 work-session records retain their original SHA-256; only the separate provider `models_cache.json` refreshes during normal post-relaunch catalog discovery. Registry remains 387 commands / 41 categories and Context Injection remains disabled. Live post-permission Proto-Mind Computer Use acceptance is pending the operator-owned macOS Automation approval.

## Local Capability Contracts And Computer Use Lifecycle / Native 0.16.0

Native 0.16.0 adopts the useful local interface discipline from the inspected ChatGPT App skill without turning Proto-Mind into a public web/MCP app:

- `local_knowledge_capabilities.py` declares exactly two private-stdio callbacks, `search` and `fetch`, over the existing read-only `NativeLibrary`. Schemas reject undeclared properties; annotations are read-only, non-destructive, closed-world and idempotent. Results use exactly `structuredContent`, one bounded text fallback and `_meta` that fixes contract version, local transport, and false network/model/write authority.
- The Python bridge produces the typed result directly. Swift checks the complete envelope before decoding its existing page/detail contracts; unsafe or malformed envelopes fail visibly. A new app may call the old `library_list` / `library_inspect` methods only when an older bridge explicitly reports the typed method absent. There is no generic dispatcher, public MCP listener, Node dependency, model invocation, automatic recall or store writer.
- `native_work_log.v1` now includes a monotonic positive `state_version`. Swift accepts only a newer version for the same run ID, while separately identified runs and old unversioned history retain compatibility. The field orders public UI snapshots only; raw reasoning, summaries and internal prompts remain excluded.
- Root-cause inspection of the hot post-task Computer Use process found that Proto-Mind correctly closed its app-server but had overridden Codex `notify` to an empty list. The signed OpenAI client exposes the official `turn-ended` handler used by ChatGPT itself. Full Mac turns with verified Computer Use now configure that exact handler; ordinary Chat and Computer-Use-free turns keep `notify=[]`. The shared desktop-managed service may remain resident for ChatGPT, so Proto-Mind does not kill it or claim process ownership.

Rule 0: `backups/proto_mind_backup_2026-09-01_18-32-25.tar.gz`. Targeted Python checks pass 119 tests, the full suite passes 1,517 tests, all 355 Native checks pass and the local agent eval remains 6/6. The release build, plist, ad-hoc signature and personal-app relaunch pass as 0.16.0 build 20. The already-stale shared service from the prior build remained near 20% CPU; one operator-side TERM reset removed it without stopping ChatGPT or Proto-Mind, and no such kill path exists in the app. All 48 project `data`/`exports` files retain their checkpoint SHA-256, Registry remains 387 commands / 41 categories and Context Injection remains disabled. No slash command, core/session-log schema, dependency, public endpoint, Platform/API-key integration, additional Computer Use tool or persistent grant is added.

## Persona Snapshot Inspector / Native 0.17.0

Native 0.17.0 delivers Persona 0.2 as a visible but inactive preview:

- `native_persona.py` accepts one exact private-stdio request for the selected conversation's provider, model, workspace and access controls. Workspace paths pass through the existing protected reader and become only an opaque device/inode-bound reference. A Full Mac self-model is possible only after validating the current in-memory conversation/workspace grant; the token and absolute path never enter the response.
- The compiler reads the existing Identity projection without initialization, selects no memory and emits the same hashed, non-authorizing Brother snapshot from Persona 0.1. Context Injection is read as enabled/disabled/unknown but neither its payload nor setting is changed.
- `PersonaInspector.swift` independently validates the exact envelope, kernel/voice invariants, bounded Identity items, empty memory projection, workspace linkage, runtime/tool coherence, source summary and safety flags. The sheet is opened explicitly from **Обзор ядра** and shows Kernel, Identity, self-model, boundaries, evidence and omissions.
- The preview performs no provider/network/model call, retrieval, command execution, core/private/export write, permission change or background work. It displays no private chain-of-thought and is not consumed by Codex, Ollama or Mock prompts. Activation remains Persona 0.3 and requires separate parity/readiness/rollback gates.

Rule 0: `backups/proto_mind_backup_2026-09-01_21-07-05.tar.gz`. Seven new Python regressions bring the full suite to 1,540; all 368 Native checks pass. Persona evals pass 7/7 with `model_calls=0` and `store_writes=0`, Agent evals pass 6/6, and compileall/imports pass under Python 3.11.15. Release 0.17.0 build 21, plist, ad-hoc signature and personal-app relaunch pass. All 48 project `data`/`exports` files retain their checkpoint SHA-256; Registry remains 387 commands / 41 categories and Context Injection remains disabled. No dependency, slash command, core/session-log schema, memory selection, Context Injection behavior or authority is added.

## Persona Provider Readiness / Native 0.18.0

Native 0.18.0 makes the pre-activation gates inspectable without activating Persona:

- `persona_activation_readiness.py` validates an already compiled snapshot and renders a bounded future prompt projection entirely in memory. Codex declares `baseInstructions` refreshed on thread start/resume; Ollama declares its per-request system message; Mock remains a control-only adapter with no model prompt.
- Every projection binds the snapshot, invariant, runtime and prompt hashes plus exact provenance for kernel, Identity, task/runtime and each already-selected memory record. Memory content remains quoted untrusted data and cannot become authority.
- Codex and Ollama must preserve one kernel/Identity/memory/task invariant while reporting their real provider/model/access differences separately. Provider safety instructions are non-replaceable; prompt bounds, no added authority and no side effects are explicit gates.
- `persona_readiness` compiles Codex/Ollama/Mock evidence through private stdio without a coordinator, provider connection, model/network call, retrieval or write. Enabled or unknown Context Injection makes the report `NOT_READY`; Mock selection is a visible control-only `WARN`.
- `NativePersonaReadiness` independently validates the exact summary and displays adapter placement, parity SHA, nine gates, blockers and warnings inside Persona Inspector. There is no activation control and the existing conversation reasoners receive no new text.

Rule 0: `backups/proto_mind_backup_2026-09-01_21-33-08.tar.gz`. Twelve new regressions bring the full suite to 1,552; all 374 Native checks pass. Foundation and readiness Persona evals each pass 7/7; readiness reports zero model/network/retrieval/store calls and zero activation. Agent evals remain 6/6. Release 0.18.0 build 22, compileall/imports, plist, ad-hoc signature and personal-app relaunch pass. All 48 project `data`/`exports` files retain their checkpoint SHA-256; Registry remains 387 commands / 41 categories and Context Injection remains disabled. No dependency, slash command, core/session-log schema, persistent preference, prompt activation, permission or provider behavior is added.

## Controlled Brother Persona / Native 0.19.0

Native 0.19.0 crosses the prompt boundary narrowly, visibly and reversibly:

- Model Settings offers **Проверить и включить…**, not a trait slider. A first read-only READY report creates a pending confirmation bound to the current conversation/provider/model/access/workspace and a timestamp-independent activation fingerprint. Confirmation fetches readiness again and refuses any drift before writing one private preferences-v2 boolean.
- Each later normal Codex/Ollama Send recomputes readiness and validates current provider, explicit Codex model, workspace/full-access evidence and independently disabled Context Injection before provider dispatch. Mock and operator commands cannot activate Persona. Context is checked again immediately before compiling the turn snapshot.
- The compiler uses only memories already selected by the existing coordinator. One bounded Brother projection replaces the legacy identity/memory system context for that turn while provider/developer safety instructions remain separate. It adds no retrieval, model call, network call, writer, permission or tool.
- `persona_turn_activation.v1` binds the exact final active/legacy prompt hashes, snapshot/invariant/runtime/readiness hashes, memory IDs/provenance and explicit zero additional-call/write counters. Native validates the closed receipt and shows a bounded summary; Python remains the canonical receipt-hash verifier.
- **Вернуться к legacy prompt** changes only the private preference and restores the exact previous prompt path for the next turn. It does not erase already persisted Native or durable Codex thread history. Persona remains one Brother identity with contextual adaptation; no facets, modes, provider forks or automatic evolution exist.

Rule 0: `backups/proto_mind_backup_2026-09-01_21-51-33.tar.gz`. Twelve Python regressions bring the full suite to 1,564 and 13 Native checks bring the Native suite to 387. Foundation/readiness/runtime Persona evals pass 7/7 + 7/7 + 8/8 with zero real model/network/retrieval/store calls; Agent evals remain 6/6. Release 0.19.0 build 23, compileall/imports, plist, ad-hoc signature and personal-app relaunch are acceptance gates. All project `data`/`exports` files must retain their checkpoint SHA-256; Registry must remain 387/41 and Context Injection disabled.

## EV-04 Cognitive Memory Loop v1 / Native 0.20.0

Native 0.20.0 starts the Memory And Skill Workshop roadmap with two narrow read-only surfaces:

- Memory cards call the existing durable learning-provenance verifier after rereading the fixed source. `VERIFIED` means the embedded schema, record payload and deterministic hashes agree. `UNAVAILABLE` means an operator/legacy record has no such chain and Proto-Mind does not invent one. `ERROR` means the stored metadata failed the contract. None of these labels proves that arbitrary memory content is true.
- The completed-turn inspector can search the fixed memory sources for its selected bare record ID and open it only when exactly one layer matches. Missing or cross-layer duplicate IDs fail visibly.
- **Кандидаты опыта** reads only the already-existing process-memory Experience pilot for the selected conversation. It does not create a Coordinator/pilot, request consent, capture a turn, run a command, accept/reject a candidate, build a proposal, promote a lesson or write memory/skills. Buttons place exact existing `/experience` inspection commands into the composer for later operator review.
- The report binds the selected workspace identity as context but labels canonical memory scope `global_legacy_stores` and `project_isolation_enforced=false`. A real scoped-memory schema/migration remains a separate milestone.
- Persona 0.3.1 adds an exact same-thread next-turn rollback test for Codex `baseInstructions`. Russian benchmark coverage now includes a current-decision query that explicitly rejects the superseded JSON choice.

Rule 0: `backups/proto_mind_backup_2026-09-01_22-58-40.tar.gz`. The full Python suite passes 1,569 and Native checks pass 390. Release 0.20.0 build 24, plist, deep strict signature, personal-app relaunch and a model-free read-only memory/Workshop smoke pass. All 48 project `data`/`exports` files retain the checkpoint SHA-256 manifest `7f682153ecf38b20c03ce8556985d5ff327f67299ec9e30e1d5b580c4d361ab3`. No new dependency, slash command, Registry entry, session/core-store schema, permission, Context Injection behavior or background worker is introduced.

## EV-04 Supervised Lesson Review / Native 0.21.0

**Кандидаты опыта > Разобрать урок** reuses the existing core instead of dispatching slash commands or adding another learning writer:

1. Read the current process-memory candidate and source event IDs. Separately preview and confirm acceptance or rejection; this changes only the existing decision session.
2. Explicitly select 1-20 active, unambiguous memory IDs for duplicate comparison. Separately preview and confirm a `memory.lesson.v1` proposal; references are not edited and the proposal remains process-memory-only.
3. Preview current apply readiness, then type its exact token and acknowledge that the lesson enters shared global memory. Final apply uses the existing `learning_applies.apply` contract to append and verify one lesson, show its receipt and open the stored provenance. There is no apply-all or automatic step chaining.

`memory_learning_review` and `memory_learning_preview` are read-only private-stdio methods. Only `memory_learning_confirm` invokes the four fixed operations; they are not model tools or new Registry commands. The screen changes neither the unsent composer nor Native chat history. Requests/results bind the selected conversation, candidate, workspace and explicit reference/reason fields. Current source/store hashes and core tokens are rechecked under the Native turn lock; stale requests, corrupt/symlink stores, unknown fields and unapproved operations fail closed. Confirmation results are never automatically retried, including after a transport failure.

The existing shared core writer now appends to raw original JSON rows rather than round-tripping legacy rows through a lossy dataclass projection. Unknown fields and absent legacy fields survive; the new lesson remains the fixed existing schema. A no-follow, regular-file, 16 MiB-bounded read precedes a private fsynced atomic replacement. Post-write verification failure restores the exact original bytes only when the file still matches this operation's intended bytes; concurrent changes and pre-existing temporary files are never overwritten/deleted by recovery. This is not a global transaction lock or a guarantee against every cross-process race.

Limits: one successful memory apply per running Native bridge across its conversations; closing a conversation or losing the result after a successful write does not renew that budget. Proposals expire after 15 minutes. Decisions/proposals/detailed receipts disappear on restart, while applied lesson provenance survives. Reference IDs limit comparison, not project access. Global legacy memory is not project-isolated. Evidence and hashes prove lineage/consistency, not truth. An empty reference store, expired proposal or missing process candidate needs a new explicit operator workflow, not automatic recreation. Skill authoring arrives separately in 0.22.0 below; lifecycle UI and durable review drafts remain follow-ups.

Verification: 26 new Python regressions, including raw legacy-field preservation, exact rollback, collision/concurrent-write defense, private RPC refusals and dropped-session/lost-result budget protection, bring the suite to 1,595. Real stdio Mock checks add 34 Native assertions (424 total), covering exact tokens, explicit reference selection/global acknowledgement, one-store apply, replay refusal, unchanged drafts/history and restart-safe provenance. `scripts/test_native.sh --learning-only` runs that isolated workflow directly. Persona evals remain 7/7 + 7/7 + 8/8 and Agent evals 6/6. The obsolete build-number pin in the Automation test is replaced by valid SemVer, positive build number and fixed bundle identity checks.

Release build 25, strict deep signature verification, Python compileall and Proto-Mind/PySide6/tkinter imports pass. Personal-app smoke verifies Memory Workshop's empty/not-started pilot without starting capture or sending a model turn. All 48 core/export files and 28 Proto-Mind-owned history/preferences/work-session files retain their original hashes and inventory after verification; official Codex profile caches are excluded. Context Injection stays disabled. The complete write workflow is exercised only in disposable synthetic fixtures, not against personal memory. Optional pytest is unavailable and is skipped by the existing test runner.

Rule 0: `backups/proto_mind_backup_2026-09-02_06-13-52.tar.gz`, plus a separate private Native history/settings/work-session archive excluding credentials. All actual writes during apply verification use disposable synthetic stores. No dependency, slash command, registry category, session/core-store schema, Context Injection behavior, cloud opt-in or permission change is introduced.

## Native Cube Icon / 0.21.1

The Native bundle now has its own silver, petrol-teal and turquoise dimensional cube icon inspired by the operator-supplied emblem, without its wordmark. `assets/proto_mind_native_icon.png` is the versioned 1024 x 1024 RGBA master. `scripts/build_native_icon.sh` uses only local macOS `sips`/`iconutil` to create ten standard 1x/2x representations from 16 to 1024 pixels. The normal Native build installs `ProtoMindCube.icns`, keeps the same bundle identity, signs it and refreshes only this app's timestamp and Launch Services registration to avoid the stale legacy icon cache. The old PySide app and icon are untouched.

Artwork generation used the built-in image tool. Its opaque checkerboard was removed once with macOS Vision/Core Image after explicit operator approval; neither runtime nor packaging invokes an image model or Vision. [Design prompts and asset preparation](assets/NATIVE_ICON.md) are kept alongside the finished master.

Verification: 1595 Python tests and 429 Native checks, including five master-image assertions, pass. ICNS round-trip preserves all ten dimensions and their alpha channels; small-size preview and the real About window show the cube in Native 0.21.1 build 26. All 48 core/export and 28 Proto-Mind-owned history/preferences/work-session files retain their hashes and inventory; official Codex profile caches are excluded. Context Injection remains disabled. This is a branding/packaging patch, not a cognitive feature, new dependency, permission or persistent-state change.

Rule 0: `backups/proto_mind_backup_2026-09-02_07-17-27.tar.gz`.

## EV-04 Supervised Skill Workshop / Native 0.22.0

The persistent verified lesson card now opens **Create skill from lesson**. This works after restart without a live Experience pilot or capture consent and reuses the core v3.5b/v3.5c/v3.5d/v3.5e contracts rather than adding a second writer:

1. Read the exact lesson, provenance, lifecycle and duplicate checks. Fill the bounded local form: name, summary, trigger, preconditions, steps, permission requirements, verification and failure modes. Opening/editing changes no files and does not synthesize steps or call a model.
2. Preview the exact procedure body and type its authoring token. This creates one of at most 16 core process-memory authoring receipts, not a saved skill or permission.
3. Separately preview current apply readiness, type the distinct apply token and acknowledge that Skills are shared global legacy stores. Final apply appends exactly one non-executable `skill.procedure.v1` record through the existing writer, verifies it and shows the result. There is no apply-all, execution, automatic retry or chaining between stages.

`skill_authoring_review`, `skill_authoring_preview` and `skill_authoring_confirm` are fixed private-stdio UI methods, not model tools or Registry/slash commands. The bridge shares its foreground lock with turns and binds the exact lesson, authored fields, selected conversation, canonical workspace identity and current memory/skill hashes. Swift rejects undeclared top-level fields, widened mutation/authority flags and mismatched responses. Editing a form clears pending confirmation. Closing/reopening a conversation or losing a success response cannot renew the one-skill Native process budget, including the existing operator slash-apply entry.

The shared writer preserves original Skill Library bytes and unknown legacy fields, rejects duplicate JSON keys, symlinks/non-regular files and files beyond 16 MiB, uses a private exclusive temporary file and fsynced atomic replacement, and verifies the exact appended bytes plus unchanged source memory. Failed verification restores original bytes only while this operation's output still owns the target; concurrent changes and pre-existing temporary files are preserved. This is not a global cross-process transaction lock. Do not run concurrent legacy writers against the same store.

Skill Library detail independently rechecks embedded procedural provenance and the source lesson with bounded read-only helpers. It exposes verified, legacy/unavailable, source-drifted and invalid evidence, including after restart, and can navigate back to the source lesson. Source hashes prove lineage/consistency, not procedure quality or truth. Permission requirements are text, never a tool grant. Authoring drafts and detailed receipts expire with the bridge; stored provenance survives. Lifecycle/restore UI, durable drafts, project-isolated memory and executable skill packages remain separate work.

Rule 0: `backups/proto_mind_backup_2026-09-02_17-42-43.tar.gz`, plus a private Native history/settings/work-session checkpoint excluding credentials. Write-path verification uses disposable synthetic stores only. No new dependency, Registry prefix/category, persistent record schema, background task, Context Injection change or new authority is introduced.

Verification: 23 new Python regressions bring the suite to 1,618. Native checks pass 463, including 34 new skill/alias assertions with real private stdio, exact confirmations, scope/replay refusals, one-file apply and durable provenance after restart. Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Real UI smoke on a code-only synthetic project fills a Russian procedure, refuses the wrong token and missing shared-scope acknowledgement, saves one skill, verifies its receipt, opens its library/source cards and refuses re-creation. Only synthetic `skills.jsonl` changes; its source and private chat remain byte-identical. This is workflow/integrity evidence, not a procedure-quality benchmark.

Release 0.22.0 build 27, plist, strict deep signature, Python compileall and Proto-Mind/PySide6/tkinter imports pass. Personal-app relaunch/About confirms the version without sending a model turn. All 48 project core/export and 28 Proto-Mind-owned history/preferences/work-session files retain their original SHA-256 and inventory; official Codex profile caches are excluded. Context Injection remains disabled, Registry remains 387 commands/41 categories, and optional pytest is unavailable/skipped. UI smoke caught a Foundation/Python `/var` versus `/private/var` spelling mismatch; current matching resolves both paths while retaining rejection of a different workspace.

## EV-04 Skill Evidence And Lifecycle / Native 0.23.0

Open **Library and Core > Skills > a skill > Results and lifecycle**. The bounded Native sheet reads the existing core's evidence rather than building a second skill state machine:

- The current durable state distinguishes active verified/historical/restored, verified archive, ambiguous archive, payload drift, legacy/unprovenanced and invalid records. The exact source lesson can be opened without executing a command.
- The transition list contains only verifiable apply/archive/restore traces in the current record, including the embedded prior archive after restore. It is explicitly incomplete history, not a reconstructed event log. Missing old metadata is not repaired. Consistency hashes are not proof of truth or effectiveness.
- Manual-use results come only from the already-existing Experience pilot of the selected Native conversation. No pilot, capture consent, event, decision or receipt is created. The core's exact lineage review produces success/failure/mixed/insufficient candidates; stored `uses` is display-only, not a success metric. No conversation selection still permits durable inspection without including another conversation's events.
- Restored skills use the separate post-restore reviewer. Pre-restore and unbound later events are counted but excluded from fresh results. The post-restore capture writer remains absent. Durable restore evidence can be verified after restart, but an unavailable detailed process receipt is not recreated or persisted.

`skill_inspection` is one fixed, operator-only, private-stdio RPC, not a slash command or model tool. It shares the foreground lock and accepts only a skill/conversation selection, optional current workspace and expected library SHA. `skills.jsonl` and `persistent_memory.json` are read without store construction, using no-follow regular-file checks and existing 16 MiB/5000-record bounds. Corruption, duplicate JSON keys/IDs, non-finite values and oversize snapshots fail closed rather than yielding a partial verified verdict. Up to 256 existing Experience events are considered. Source readback discards a verdict if it observes an intervening change; this is not a filesystem freeze or cross-process transaction.

Swift checks the closed read-only envelope, selected IDs/workspace, safety flags, state/count coherence and bounded values. A closed or changed selection ignores late responses. Refresh/source navigation does not change drafts, chat, preferences, core stores, export files, usage counters, Context Injection, tool grants or background work. The library remains global legacy state; selected workspace is context, not project isolation.

Rule 0: `backups/proto_mind_backup_2026-09-02_18-42-12.tar.gz`, plus a separate private Native history/preferences/work-session checkpoint excluding credentials. Mutation/corruption fixtures remain disposable synthetic data. No dependency, Registry command/category or persistent schema is added. Lifecycle writes, explicit outcome capture controls, persistent review history, project-isolated memory and executable skill packages remain separate work.

Verification: 26 new Python regressions bring the suite to 1,644. All 491 Native checks pass, including 28 new real-stdio, read-only-envelope, scope and navigation assertions. Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Isolated UI smoke verifies restored apply/archive/restore traces, exact source navigation, refresh and honest legacy unknowns; all five fixture data/private files remain byte-identical. A Swift 6.3.3 optimized optional-borrow compiler failure was resolved with explicit validation steps, without relaxing checks or disabling optimization.

Release 0.23.0 build 28, plist, strict deep signature, Python compileall and Proto-Mind/PySide6/tkinter imports pass. Personal-app relaunch/About confirms the version without sending a model turn. All 48 project core/export and 28 Proto-Mind-owned history/preferences/work-session files retain their pre-change SHA-256 and inventory; official Codex profile caches are excluded. Context Injection remains disabled, Registry remains 387 commands/41 categories and its doctor is OK. Optional pytest is unavailable/skipped. This acceptance proves the inspection workflow and evidence integrity, not real-world procedure effectiveness.

## EV-04 Manual Skill Outcomes / Native 0.24.0

Open **Library and Core > Skills > a skill > Record manual outcome**. Choose success or failure/correction and describe the already-performed manual result in at most 800 characters. This is an operator report, not independent verification, automatic training or procedure execution. The existing core redacts recognized credentials and stores a compact preview/fingerprint; it is not a guarantee that every secret format is detected.

An active verified non-restored skill and readable explicitly disabled Context Injection are required. The current conversation must already have exact Experience consent. If absent, the form explains the prerequisite and can open the existing Workshop without executing or preparing a command. The separate operator-run `/experience preview` and exact consent flow remain unchanged; that consent covers bounded normal cognitive turns too, not only one outcome. Opening the new form never initializes stores, creates a coordinator/pilot, enables consent or changes Context Injection.

Three fixed private-stdio RPCs (`skill_outcome_review`, `skill_outcome_preview`, `skill_outcome_confirm`) reuse the existing core builder and capture session. A preview binds the exact form, selected conversation/workspace, current source/config hashes, pilot identity/state, event/receipt snapshot and core blueprint. Confirm requires that fingerprint, the exact core token and acknowledgement that the result is manually reported and process-only. Edited inputs, source/consent/event drift, a different selection, malformed/symlink/over-limit sources and an exact replay are refused. The bridge lock prevents overlapping foreground turns; readback detects observed external changes but does not freeze the filesystem.

Only confirmation appends the existing four-event batch and one receipt in bounded process memory. Nothing is written to core stores, exports, private history/settings or session logs. No `uses` update, model/network/tool call, permission, automatic learning or lifecycle decision is added. The core's 16-receipt, event and byte caps are preserved; a buffer rejection appends no partial batch and may stop the pilot fail-closed. Lost responses do not trigger an automatic retry; reopen/refresh to inspect the existing receipt. A process restart expires consent, events, forms and receipts, not the durable skill. Evidence remains scoped to the selected conversation; the skill/lesson libraries are still global legacy stores.

The saved receipt links directly to **Results and lifecycle**. Success remains operator-reported, an error/correction maps to failure, and conflicting later reports stay mixed. Archived, restored and unprovenanced skills cannot use this capture path. Post-restore capture, lifecycle decision/write controls, persisted manual-use history and runnable skill packages remain separate work.

Rule 0: `backups/proto_mind_backup_2026-09-02_19-51-28.tar.gz` and a separate private Native checkpoint `backups/proto_mind_native_history_2026-09-02_19-51-28_skill_outcomes.tar.gz`, excluding credentials. The change adds no dependency, Registry command/category or persistent schema.

Verification: 25 new Python regressions bring the full suite to 1,669; Python compileall passes and optional pytest is absent/skipped. All 536 Native checks pass (491 previous + 45 form/real-stdio/receipt assertions); focused learning checks pass 141. Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Release 0.24.0 build 29, plist, strict deep signature and Proto-Mind/PySide6/tkinter imports pass. UI smoke on a code-only synthetic project demonstrates missing consent, explicit existing consent setup, Russian evidence input, wrong-token refusal, one confirmed result, exact receipt linkage in the inspector and replay refusal. All five fixture data/private files retain their pre-capture bytes, including after app shutdown. No model or actual procedure was tested.

Personal-app relaunch/About confirms 0.24.0 (29), without sending a model turn. All 48 project core/export and 28 Proto-Mind-owned history/preferences/work-session files retain their pre-change SHA-256 and inventory; official Codex profile caches are excluded. Context Injection remains disabled. Registry remains 387 commands/41 categories and its doctor is OK. This proves capture/receipt integrity and the operator workflow, not real-world skill effectiveness.

## EV-04 Skill Outcome Decisions / Native 0.25.0

Open **Library and Core > Skills > a skill > Results and lifecycle > Decision from results**. The operator chooses manually: confirmed success permits keep; failure or mixed evidence permits revise or archive recommendations. Nothing is preselected, and the exact source/capture evidence must be available in the selected conversation. An archive recommendation does not archive the skill; revise does not edit it; keep does not authorize execution or certify effectiveness.

Three fixed private-stdio methods (`skill_decision_review`, `skill_decision_preview`, `skill_decision_confirm`) reuse the existing decision builder/session/doctor, not a new writer. The Native outcome reader supplies bounded no-follow snapshots of skills, source lessons and explicitly disabled Context Injection. Preview binds the selection/choice, workspace identity, raw source SHA-256, pilot state/session, events, capture receipts and existing decisions. Confirm requires that current fingerprint, the exact core token and an acknowledgement of a process-only decision. The foreground lock and source/process readback detect observed changes; they are not a cross-process filesystem transaction.

Only confirmation adds one terminal decision receipt in process memory. No new Experience event, disk write, skill status/uses change, lifecycle apply, command, procedure, model/network call, grant or consent change occurs. Separate prior manual outcome consent is not silently created. An operator can explicitly decide over retained evidence after stopping capture, without resuming it; a stop between preview/confirm invalidates that preview. The core's one-decision-per-skill-per-conversation-pilot and 16-receipt bounds remain. Lost responses are never automatically retried; reopening displays the existing receipt.

Receipt integrity and evidence currency are distinct: later results can make a still-verifiable receipt historical. The original receipt is neither rewritten nor replaced, and no new authority is inferred. The inspector remains reachable. Archived/restored/unprovenanced skills cannot enter the new decision path; missing/corrupt evidence and unsafe settings fail closed. Restart discards choices/decisions/evidence/consent, not the saved skill. Shared legacy stores are not project-isolated. Actual lifecycle apply UI, persisted decision history, revision payloads and the pending post-restore writer remain separate work.

Rule 0: `backups/proto_mind_backup_2026-09-02_20-38-05.tar.gz` plus `backups/proto_mind_native_history_2026-09-02_20-38-05_skill_decisions.tar.gz` (private history/preferences/thread bindings/work sessions; credentials excluded).

Verification: 24 new Python regressions bring `scripts/run_tests.sh` to 1,693 tests; compileall passes, optional pytest is absent/skipped. All 587 Native checks pass (536 previous + 51 decision assertions), including 192 focused learning checks. Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Release 0.25.0 build 30, plist, strict deep signature and Proto-Mind/PySide6/tkinter imports pass. Real isolated UI smoke checks no-evidence refusal, manual choice, wrong token, cancel/reset, one confirmed archive recommendation, receipt linkage, reopen and unchanged active status/uses. All five synthetic data/private files retain their pre-decision SHA-256, including after shutdown. Historical-state behavior is also checked through real private-stdio Native tests. No model or real procedure was run.

Personal-app relaunch/About confirms 0.25.0 (30). All 48 core/export and 28 Proto-Mind-owned history/preferences/work-session files retain their pre-change hashes and inventory; official Codex profile caches are excluded. Context Injection remains disabled; Registry stays 387 commands/41 categories with doctor OK. This acceptance proves the manual decision workflow and evidence integrity, not real-world skill quality or applied lifecycle behavior.

## EV-04 Skill Lifecycle Apply / Native 0.26.0

Open **Library and Core > Skills > a skill > Results and lifecycle > Decision from results**, then **Check decision application** on an exact recorded decision. This is separate from deciding what should happen. Review/preview are read-only; a new exact core token and shared-library acknowledgement are required before any application. No choice or action is automatic.

Three fixed private-stdio methods (`skill_lifecycle_review`, `skill_lifecycle_preview`, `skill_lifecycle_confirm`) reuse the existing readiness and keep/durable-archive sessions. The bounded reader validates fixed skill/lesson/config sources and current conversation/workspace identity. Preview binds raw store hashes, decision receipt, pilot state, events, capture receipts and prior apply state. Swift validates the closed result/safety schema and independently recomputes the core token. Changed sources/evidence/settings/scope, historical or corrupt decisions, wrong tokens and replay are refused. A fresh explicit apply over retained evidence does not resume stopped capture; stopping between preview and confirmation invalidates that preview.

- **Keep:** verify unchanged skill/source bytes and retain one process-only no-op receipt; no file is rewritten.
- **Archive:** use the existing durable core writer for exactly one active skill; change only `lifecycle`, `status`, `updated_at`. Preserve procedure/provenance/uses/unknown fields, neighboring raw JSONL bytes and record count. Re-read actual disk bytes and source dependencies before recording a successful receipt.
- **Failure:** exclusive temporary creation plus expected-byte atomic replacement; restore original bytes only if current bytes still equal the writer's own payload. Concurrent/unreadable changes are never overwritten by recovery. This is not a cross-process transaction lock or an automatic repair service.
- **Attempt limit:** one Native lifecycle attempt per bridge process, including a failure after entering apply or a lost response. Invalid token/acknowledgement and stale previews do not consume it. Changing/closing a conversation does not renew it; an existing successful operator lifecycle apply also consumes it. No automatic retry.

The receipt shows exact decision/skill IDs, source/post-state hashes, actual mutation count, changed fields, durable metadata ID/hash, verification status and current/historical evidence. Reopening is read-only. Detailed receipts/decisions expire on restart; the saved archive envelope and source provenance remain independently inspectable. Missing process evidence remains unknown, not recreated. The form links to the exact archived skill and its existing evidence inspector. Shared legacy stores are not project-isolated. No new model/network/retrieval call, command, procedure execution, Experience event, memory/private-history write, Context change, grant, persistent schema or Registry prefix is introduced. Revision, restore and the pending post-restore capture writer remain separate work.

Rule 0: `backups/proto_mind_backup_2026-09-02_21-11-36.tar.gz` plus `backups/proto_mind_native_history_2026-09-02_21-11-36_skill_lifecycle.tar.gz` (private history/preferences/thread bindings/work sessions; credentials excluded).

Verification: 24 new Python regressions bring `scripts/run_tests.sh` to 1,717 tests; compileall passes, optional pytest is absent/skipped. All 639 Native checks pass (587 previous + 52 lifecycle assertions), including 244 focused learning checks. Native fixtures exercise keep/no writes, revision refusal, exact archive, token cryptographic binding, contract widening, replay, wrong acknowledgement, receipt/restart and exact changed-file inventory. Python also checks rollback, collision, concurrent-write preservation, strict sources, global attempt limits and dependency drift. Persona evals pass 7/7 + 7/7 + 8/8; Agent evals pass 6/6. Release 0.26.0 build 31, plist, strict signature and Proto-Mind/PySide6/tkinter imports pass.

Real isolated UI smoke uses a synthetic skill and an explicitly consented synthetic manual failure, not a model or actual procedure. After a separate archive decision, the new apply form refuses a wrong token, then records one VERIFIED/CURRENT archive receipt. Only that fixture's `skills.jsonl` changes among five core/private files; all other hashes remain identical. Refresh performs no replay. After a complete process restart, the archived record/provenance/cause remain verifiable, `uses` stays zero, and temporary outcomes/decisions are absent. Post-apply/restart SHA manifests are identical. The inspector's WARN for unavailable process evidence is expected, not invented success or a failed archive.

Personal-app About confirms 0.26.0 (31). All 48 personal core/export and 28 Proto-Mind-owned history/preferences/work-session files retain pre-change SHA-256 and inventory; official Codex profile caches are excluded. Context Injection remains disabled; Registry doctor stays OK at 387 commands/41 categories. No personal skill was archived during acceptance. Next: expose the existing separately confirmed restore gate in Native, not a generic revision editor or post-restore capture engine.

## EV-04 Skill Restore / Native 0.27.0

The archived skill inspector now opens **Restore from archive**. Only a currently verified, provenance-current archive can prepare confirmation. The app uses the existing durable restore session rather than a second status writer. A new exact token and explicit shared-library acknowledgement bind the current source bytes, archive envelope, one-record/three-field scope and conversation/workspace.

Restoration changes only `lifecycle`, `status`, and `updated_at`, embeds the complete prior archive envelope and returns a fixed independently hashed/verified receipt. Procedure body, provenance, neighboring raw bytes and memory remain unchanged. One Native attempt per bridge process, including post-start failure, prevents silent retries; the existing core's successful operator restore also consumes that slot. There is no procedure/model/tool execution, consent/grant recovery or post-restore outcome capture. Old results are not fresh evidence of success.

Source/audit reads are bounded and do not initialize missing stores. The existing writer now preserves neighboring JSONL bytes and uses expected-byte replacement; failed post-checks restore original bytes only while the store still contains this attempt's payload. Foreign/unreadable bytes are preserved with a visible error. Cooperative checks do not provide an external-process transaction lock.

The detailed receipt remains process-memory-only in this milestone; durable restoration/provenance can still be independently inspected after restart. No historical receipt is reconstructed or relabelled as original. Context Injection stays disabled, permissions and core schemas stay unchanged, and Registry remains 387 commands/41 categories.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-02_22-16-51.tar.gz` and `backups/proto_mind_native_history_2026-09-02_22-16-51_cognitive_cycle.tar.gz` (Native-owned history/preferences/binding/work sessions; credentials excluded). Verification results are recorded in the Architect Ledger after acceptance.

## Turn Lineage / Native 0.38.0

Successful ordinary Codex and Ollama turns now produce `proto_mind.native_turn_receipt.v1` inside the existing private work session after the exact response is observed. The closed receipt stores no prompt or answer text: it binds normalized run/conversation UUIDs, provider and access mode, Unicode character counts, SHA-256 of input, exact raw response and bounded answer preview, plus the preceding Instruction Receipt hash. It explicitly keeps `task_success_verified=false` and `provider_delivery_verified=false`. Python validates the canonical material and cross-checks every run-owned field and preview hash before a saved record can be listed.

The corresponding assistant `ChatMessage` may carry one optional `proto_mind.native_turn_reference.v1`. Native independently validates its canonical hash, original user-message UUID, exact user/response bytes, conversation, provider/mode, run ID and stable turn-receipt hash whenever history is saved or loaded. Source messages and run IDs cannot be reused ambiguously. A clock button refreshes the bounded journal and opens only the referenced run whose current receipt still matches. Later operator review can change the whole-record fingerprint without invalidating this immutable subreceipt; a missing, old, out-of-window or tampered run fails visibly and is never substituted with the newest or adjacent run.

History v5 and `native_work_session.v1` remain optional-field compatible: no load-time migration or rewrite is performed. Mock, slash/operator, failed and interrupted routes receive no invented lineage. The receipt is an unkeyed local consistency proof, not a creator signature, provider delivery/interpretation proof or task verification. It does not write Session Spine, reconcile an archive, alter model input, call a provider, expose private reasoning, add permission/command/dependency, change Context Injection or touch core/export schemas. The next possible slice can use this exact trio for a read-only live Session Spine preview before any production writer is considered.

Verification adds four mandatory Python regressions and twelve Native checks. They cover canonical content-free receipts, exact fake-provider response binding, atomic completion failure, immediate source pairing, history restart, legacy compatibility, source/response/conversation drift, run relabelling, stable resolution after review and missing-evidence refusal. The mandatory suite passes 2,016 tests; `scripts/test_native.sh` passes 884 checks, Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Registry remains 387 commands/41 categories and Context Injection remains disabled.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-04_06-28-10.tar.gz` and `backups/proto_mind_native_state_2026-09-04_06-28-21_turn_lineage.tar.gz` (Native-owned state only; Codex credentials/profile/runtime workspace excluded). Complete acceptance totals are recorded in the Architect Ledger.

## Live Session Spine Preview / Native 0.39.0

Every assistant answer carrying a verified Turn Lineage reference now offers a second, connected-node action beside the exact-run clock. Native requires the immediately preceding exact user message, refreshes the bounded 30-run journal, resolves only the referenced run and sends a closed request containing that message pair, the content-free reference and the current `run_id + fingerprint` to `session_spine_preview`. The bridge reads that one explicit record through the existing protected inspector, independently validates the reference against its durable `turn_receipt`, then invokes the existing `native_session_spine.py` P1 projection in memory. It never scans for a replacement, chooses the latest run or accepts a stale fingerprint.

The bridge returns `proto_mind.native_session_spine_live_preview.v1`: a bounded, canonical and self-hashed content-free event map. It contains event sequence/type/time, source-event provenance, folded-surface membership, text character counts and SHA-256, tool kind/status, run/reference hashes and the existing P1 summary. Prompt, displayed answer, raw provider answer, tool command/output and private reasoning text are not returned in this second payload. Swift checks the closed top-level safety fields, exact messages/reference/run, receipt hashes, contiguous event sequence, surface parity, event-specific metadata and preview hash before rendering the 780 x 680 scrollable sheet.

This slice is inspection only. It does not write a Session Spine record, chat history, work session, export or migration; call a model or operator command; replay a tool; enable a permission; change Context Injection; or claim task success, provider delivery, authenticity or authoritative history. Legacy messages have no fabricated button or backfill. The preview is unavailable when the referenced run is absent from the bounded journal, changed, invalid or currently unstable. P2a-P2d private stores and bundles remain detached research contracts with no live caller or production writer.

Verification adds seven mandatory Python regressions and nine dependency-free Native checks. Synthetic exact Codex-shaped evidence crosses the real stdio bridge without a provider call and proves hash parity, content-free output, deterministic repeat, strict drift/busy/missing-run refusal, closed nested-schema enforcement, bounded UI and unchanged private fixture bytes. Full acceptance totals and personal-state SHA-256 results are recorded in the Architect Ledger.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-04_06-57-52.tar.gz` and `backups/proto_mind_native_state_2026-09-04_06-57-57_session_spine_live_preview.tar.gz` (Native-owned state only; Codex credentials/profile/runtime workspace excluded).

## Session Spine Archive-Copy Compatibility / P2e

The detached Python research layer now accepts immutable bytes for one explicitly supplied complete `conversations.json` copy and an exact filename-sorted SHA-256 manifest of supplied work-session records. It supports Native history v1-v5, reuses the existing canonical work-session parser, exact Turn Lineage verifier and P1 projector, and produces a deterministic content-free `OK/WARN/ERROR` report. Compatible turns retain only IDs, counts, hashes and event/surface fingerprints; legacy unlinked answers, receipt-less or incomplete runs, orphaned lineage and invalid/missing/duplicate evidence remain visible rather than being repaired or paired by proximity.

This is not a Native feature/version change and has no bridge, menu, UI or personal-state caller. The module has no path API, does not open `conversations.json` or `work_sessions/`, writes no report/export/store, calls no provider/model/command/tool, changes no permission and never falls back to the latest or adjacent run. It also cannot prove that an unseen source directory was copied completely: the verified manifest is authoritative only for the bytes the caller supplied. `ready_for_authoritative_writer` remains false even when compatibility status is `OK`.

Fourteen disposable regressions bring `scripts/run_tests.sh` to 2,037 tests and cover exact two-turn P1 parity, v1-v5 history, legacy/orphan visibility, missing/invalid runs, changed messages and references, duplicate identities, malformed input, manifest drift, canonical copied records, deterministic content-free output and no file access/input mutation. Native code and checks remain unchanged. Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-04_07-31-57.tar.gz` and `backups/proto_mind_native_state_2026-09-04_07-32-14_session_spine_p2e.tar.gz` (Native-owned state only; Codex credentials/profile/runtime workspace excluded).

## Session Spine Private-Backup Acceptance / P2f

After explicit operator authorization, the credential-excluding P2e Native-state backup was inspected through the new detached `session_spine_private_backup.py` boundary. It requires one absolute gzip-tar path plus an independent SHA-256, reads the exact regular file with no-follow protection, rejects archive traversal/duplicates/links/special members and validates a closed member allowlist. Known bounded macOS AppleDouble and provenance metadata is ignored without extraction to disk. It never searches for another backup, opens live Native state, writes a report, calls a model/tool or changes permissions.

The content-free result is `WARN`, not `ERROR`: two conversations contain 62 messages and 30 eligible assistant replies, all from the legacy pre-lineage shape. The archive has 27 work-session records: 26 completed records without a turn receipt and one incomplete record. There are zero invalid/incompatible/orphan records and zero persisted `turnReference` links. No automatic pairing or backfill is therefore defensible. Existing history remains readable legacy evidence; a later Session Spine writer, if built, should be forward-only for newly verified turns unless a separate explicit migration contract proves otherwise. The outer archive mode is `0644`, surfaced as a privacy-hygiene warning and deliberately left unchanged.

One uppercase-UUID compatibility regression and twelve P2f regressions bring the focused Session Spine set to 149 and `scripts/run_tests.sh` to 2,050 tests. The real acceptance printed aggregates only and persisted no personal report/hash. Rule 0 project checkpoint: `backups/proto_mind_backup_2026-09-04_08-32-44.tar.gz`; inspected private source: `backups/proto_mind_native_state_2026-09-04_07-32-14_session_spine_p2e.tar.gz`.

## Session Spine Forward Writer / P2g

The isolated `session_spine_forward.py` pilot starts only with newly exact-linked Native turns. Its read-only preview accepts one explicit detached store and stable owner, verifies the current work-session fingerprint plus exact persisted Turn Lineage/message pair, reuses P1, and binds one complete turn to a self-hashed CAS plan. Apply writes only that explicit store through the existing no-follow locks. It preserves the old byte prefix, verifies the exact candidate after fsync, returns no-write `ALREADY_COMMITTED` for an identical replay and refuses stale preimages or conflicting run/message identities.

`session_spine_store.py` now also supports one bounded complete-turn batch. An ordinary in-process partial write is truncated and fsynced back to the exact preimage before the writer is retired. This is deliberately not a crash-atomic guarantee: process death or power loss can still leave a visible `UNKNOWN` tail that blocks append until separate manual recovery. P2g dual-read output keeps legacy unlinked turns, exact forward matches, recovery candidates and store-only/source-copy-incomplete findings separate; it compares conversation/run/user/assistant IDs and never links by time or proximity.

Fifteen disposable regressions bring `scripts/run_tests.sh` to 2,065 tests and the selected Session Spine set to 171. Native source/checks are unchanged because no bridge method, UI action, default personal path, provider/model/tool call, permission, migration or production writer activation was added. Rule 0 project checkpoint: `backups/proto_mind_backup_2026-09-04_09-22-19.tar.gz`.

## Session Spine Commit/Recovery Handshake / P2h

The detached `session_spine_handshake.py` layer introduces an explicit owner identity for future Native writes. It derives one stable owner from the fixed `local.proto-mind.native` bundle ID and a caller-supplied canonical installation UUID. The identity is not based on a process ID, OS username or filesystem path, remains stable across a simulated relaunch, and grants no permission or execution authority.

Handshake preparation starts only after the exact linked assistant message is the latest message in caller-supplied saved-history bytes. It independently checks the canonical Work Session file, immutable turn receipt, exact adjacent message pair, Turn Lineage and P2g CAS plan. The resulting envelope contains only IDs, sizes, SHA-256 values, ordering claims and safety boundaries; prompt/answer text and source paths are absent. A valid self-hash is not treated as a signature: apply regenerates the P2g plan and compares all source and candidate fields before any write.

The required future ordering is `Work Session completed -> history saved -> history read back -> handshake prepared -> Spine CAS`. Spine-before-history is forbidden. If the process dies after the run completes but before the exact assistant history is durable, recovery reports `ORPHANED_COMPLETED_RUN`; it never recreates the full answer from the Work Session's bounded `answer_preview`. If history is durable and Spine is still at the exact preimage, a serialized handshake can be revalidated after relaunch. If the first apply succeeded but its response was lost, replay returns `ALREADY_COMMITTED` without writing.

Recovery distinguishes owner conflict, changed source lineage, stale preimage, store-only evidence, later source metadata and a non-appendable `UNKNOWN` tail. A valid operator review before commit changes the Work Session fingerprint and invalidates the old handshake; prepare again explicitly. The same review after an exact commit leaves the stable turn receipt intact, so recovery reports a visible WARN and performs no duplicate write. Torn tails and conflicts require a separate manual recovery task; there is no automatic repair, truncation, retry or backfill at this layer.

Eighteen disposable tests bring `scripts/run_tests.sh` to 2,083 tests. Native source/checks remain unchanged: P2h has no bridge method, UI, default store, persisted installation identity, durable handshake journal, personal-state caller, model/provider/command call, permission change, migration or authoritative-history activation. All writes exercised by P2h tests target explicit temporary Spine stores only. Rule 0 project checkpoint: `backups/proto_mind_backup_2026-09-04_10-18-00.tar.gz`.

## Session Spine Durable Intent Preparation / P2i

P2i implements the last detached durability prerequisites without activating a live writer. Native now defines one canonical, non-authorizing installation identity whose owner derivation exactly matches P2h. `loadOrCreate()` is explicit, publishes one private file without replacement and survives relaunch; ordinary reads of missing state create nothing. Corrupt, symlinked, over-permissive or unknown crash evidence blocks without regeneration or cleanup. The type is not instantiated by `AppModel`.

`ChatStore.saveAndReadBack` adds a throwable future boundary over the existing canonical history archive. It returns the exact bytes read after save, decoded archive, byte count and SHA-256; post-save read failure or byte mismatch blocks later writes on that store instance and does not pretend to roll back already durable history. Existing `save()` and the production `AppModel.persist()` path are unchanged, so normal Native behavior and personal history are not migrated or rewritten in this milestone.

The detached `session_spine_intent.py` store binds the complete content-free P2h handshake to explicit opaque Spine and intent-store scopes. A create-once prepared record survives relaunch; a create-once committed marker accepts only a strictly verified P2h apply receipt. First apply may write the explicit disposable Spine and marker. If the Spine commit succeeded but its response was lost, recovery obtains a no-write `ALREADY_COMMITTED` P2h receipt and writes only the missing marker. Closed replay writes nothing. Malformed/rehashed-conflicting records, changed source evidence, copied store scope, symlinks, unknown temp files and committed-marker tamper all fail closed with no automatic retry, repair, truncation or backfill.

Twelve new Python tests bring `scripts/run_tests.sh` to 2,095 tests, the detached P2a-P2i set to 194 and the broader Session Spine set including Live Preview to 201. Twelve new Native assertions bring `scripts/test_native.sh` to 905 checks. The fresh owner-only credential-excluding copy `backups/proto_mind_native_state_2026-09-04_11-17-30_session_spine_p2i.tar.gz` revalidates as WARN with 30 legacy-unlinked assistant turns, 26 completed legacy runs and one incomplete run, and zero incompatible/orphaned lineage evidence; no report or source text was persisted. It confirms that old personal evidence stays legacy, not that a live writer works. Rule 0 project checkpoint: `backups/proto_mind_backup_2026-09-04_10-57-23.tar.gz`.

There is still no bridge/UI caller, default personal Spine/intent path, production activation, model/provider/tool call, permission change, migration or automatic repair. P2j may design an explicit opt-in live sequencing gate and recovery UI, but should not make the Spine authoritative until a newly exact-linked personal turn passes that separate acceptance.

## Session Spine Activation Readiness / P2j / Native 0.40.0

P2j introduces the first production-visible gate around the dormant P2i prerequisites without activating their writer. From an already validated Live Session Spine Preview, Native re-resolves the exact adjacent message pair, Turn Lineage reference and current Work Session, then validates the preview again. A content-free readiness receipt binds conversation, user/assistant IDs, run/fingerprint, turn/reference/preview hashes, provider/mode and the observed installation-identity state. The sheet exposes `INACTIVE`, `ARMED` and `RECOVERY_REQUIRED`, plus the exact future safeguards and one manual next action.

Installation identity inspection is read-only. A missing identity is `clean_uninitialized`; a valid existing identity is `identity_ready`; malformed, unsafe or unknown evidence is `manual_inspection_required` and cannot be armed. The inspector never calls `loadOrCreate()`. One checkbox plus button can create only an in-memory grant for the exact readiness hash. It is not persisted, resets on relaunch and is invalidated by a new Send, conversation/provider/model/effort/workspace or access-mode change. Revoke changes only that memory state. Settings always labels the writer inactive.

P2j does not call the P2h/P2i Python writer, add a bridge apply route, create a default Spine/intent directory, save/read back personal history, prepare an intent or write a Session Spine event. It adds no model/provider/command/tool invocation, permission, migration, repair, delete, compaction, legacy pairing or Context Injection change. Eleven new Native checks bring `scripts/test_native.sh` to 916; Python remains 2,095 tests because its detached contracts and bridge boundary are unchanged. The project checkpoint is `backups/proto_mind_backup_2026-09-04_12-17-21.tar.gz`.

Final acceptance uses Python 3.11.15: all 2,095 Python tests, compileall, 916 Native checks, Persona 7+7+8 and Agent 6 evals pass. Release bundle 0.40.0 (45), plist and strict deep signature pass. Registry/Policy/Natural doctors remain OK at 387 commands/41 categories. Context Injection is disabled; all 48 core/export files and 31 Proto-Mind-owned private history/preferences/binding/work-session files retain their checkpoint SHA-256 and inventory. No personal installation identity, intent or Spine store exists after acceptance. Codex-owned profile/runtime caches remain outside the private checksum comparison.

The next activation step remains separate: accept one newly generated personal exact-linked turn under this visible gate, define explicit private paths and recovery evidence, and only then decide whether to connect the already-tested history -> intent -> Spine sequence. Until that acceptance passes, `writer_active=false` is structural rather than advisory.

## Session Spine Personal Acceptance Rehearsal / P2k / Native 0.42.0

P2k consumes only a freshly revalidated `ARMED` P2j candidate. The Native app binds that candidate to the current private state root, the exact optional installation-identity path and two explicit future namespaces, `session_spine_store/` and `session_spine_intents/`. Read-only path inspection rejects symlinks, noncanonical paths, unsafe permissions, unreadable state, oversized inventories and unexpected bytes. Missing future paths are reported as clean uninitialized state; they are not created. Existing future-store evidence becomes `RECOVERY_REQUIRED` and remains byte-identical for manual inspection.

The bounded sheet displays a content-free SHA-256 rehearsal, exact source/run lineage, path states and a fixed recovery matrix covering: before any write, identity-only, prepared intent without Spine, committed Spine without marker, and unknown/torn evidence. Every branch explicitly forbids automatic retry and repair. Acceptance requires a separate checkbox and the exact current rehearsal hash, exists only in process memory, can be revoked independently of P2j and disappears on relaunch. Source drift, another state root, a stale hash or P2j revocation clears or refuses the grant.

`ACCEPTED` is evidence that the operator reviewed this one future sequence; it is not execution authority. P2k never calls `loadOrCreate`, `saveAndReadBack`, P2i prepare/apply, P2g/P2h writers, a provider, model, command or tool. It creates no installation identity, durable intent, Spine event or history record; changes no permission or Context Injection state; performs no legacy pairing/backfill, cleanup, repair or migration; and explicitly does not authorize the next milestone. Any later single forward-writer pilot remains a separate decision and must revalidate all paths and source bytes immediately before writing.

Twelve new Native checks bring `scripts/test_native.sh` to 939. They cover clean exact-path binding, content-free evidence, bounded UI, wrong-token refusal, exact process-memory acceptance, independent revoke, relaunch expiry, changed state scope, unknown existing bytes, no repair and byte-identical history/private state. Python remains 2,095 tests because P2k adds no bridge or Python writer route. Python 3.11.15, compileall, PySide6 import, Persona 7+7+8, Agent 6 and Registry/Policy/Natural doctors pass at 387 commands/41 categories. Release 0.42.0 (48), plist and strict deep signature pass. A live personal exact-linked turn reached `READY`, accepted only in memory, returned to `READY`, then P2j returned to `INACTIVE`; no model turn was sent. All 48 core/export and 33 Proto-Mind-owned private files retain their exact SHA-256 and inventory, Context Injection remains disabled and no identity/Spine/intent namespace exists. Rule 0 project checkpoint: `backups/proto_mind_backup_2026-09-04_21-11-54.tar.gz`.

## Memory Reliability and Multilingual Recall / Native 0.44.0

This release closes three practical memory gaps: concurrent updates could replace one another, project recall missed common inflections and cross-language technical terms, and Ukrainian requests often bypassed the intended memory flow.

Core-memory writers now hold a reentrant per-file advisory lock over each complete read/change/save operation. Locks are shared across store instances, threads and processes, acquired in a consistent order and retained through learning verification and rollback. Commands, usage updates, promotion, supersession, cleanup and reference repair participate. Initialization rechecks missing files under the same lock; atomic replacement flushes temporary data, refuses non-finite JSON and cleans failed temporary files. Promotion re-resolves retrieved IDs so deleted or superseded records cannot be resurrected from stale objects. Ordinary reads remain free of writes and missing Native stores stay uninitialized until a mutation.

The lock is cooperative mutual exclusion, not a multi-file crash transaction. External tools that directly rewrite JSON must coordinate separately. Full-list `save_*` methods intentionally replace a layer; any new caller that derives a replacement from a read must enclose both in `MemoryStore.transaction()`. The persistent sidecar lock files must not be removed while clients are running. These constraints are documented beside the API; no personal data migration is required.

Project recall now emits `local_content_terms_v2`. Shared Unicode normalization and a finite, inspectable RU/UK/EN vocabulary handle forms such as port/порту, server/сервера, configuration/налаштування and test/тестів. Each family contributes one relevance term regardless of repeated aliases. Unknown words still match exactly; this is not general translation, fuzzy stemming or semantic search. Source text, workspace/version checks, manual-selection precedence, three-note/6000-character bounds and provider-call counts remain unchanged. Python and Swift still accept saved `local_content_token_overlap_v1` reports without rewriting or relabeling them.

Observer and MemoryKeeper now recognize Ukrainian inventory, continuation, preference, decision, override and explicit remember requests; topic extraction preserves Ukrainian letters and normalizes apostrophe variants. Decision questions are not stored as declarations. Native suggestions accept Ukrainian statements while retaining their exact Unicode source offsets; the existing quote, hypothesis, opt-out and sensitive-text filters also recognize Ukrainian markers. Saving a suggestion still uses the existing review flow.

Verification: 2,126 Python tests (23 added), Python compile checks and 975 Native checks (5 added) pass. The concurrency regressions exercise real processes, threads, initialization, logical mutation boundaries, failure cleanup and forked-child lock ownership; Native checks run against disposable bridge fixtures and reload both recall algorithms. Persona contract evals pass 7/7 + 7/7 + 8/8 and Agent contract evals 6/6, with no live provider calls. Optional pytest is not installed. Native 0.44.0 (51) builds successfully; plist and strict deep code-signature verification pass. The finished local app bundle replaces the previous bundle without terminating its running process. All 87 protected personal core/export/Native files retain their exact bytes and inventory.

## History Persistence Recovery / Native 0.43.1

Ordinary Send previously continued after `persist()` displayed a local history error. A completed response could remain only in memory and disappear from chat after restart, while a separate Work Session still existed.

History now has explicit unsaved/failure/recovery state. Send and pending operator confirmation refuse unresolved storage failures. The pre-dispatch save restores the exact conversation and draft on failure, leaving no new turn, provider execution or core mutation. A failed final save retains the reply and message IDs in memory; the recovery button saves this state without repeating the task. The close path flushes drafts and asks whether to stay or discard unsaved changes if saving still fails. An unreadable history may be closed without a warning when no new changes were made; its file is never replaced with an empty chat.

The recovery notice remains visible independently of generic dismissible errors. It offers a local save retry for transient failures and file navigation for unreadable history. The schema remains v5. Corrupt-history import/repair and automatic archival are separate product work; this correction does not claim that an explicitly discarded unsaved reply survives exit.

Regression checks use a real disposable Python bridge plus fault-injected private-history writes: unreadable startup, exact draft rollback, no dispatch before persistence, retained completed answers, save-only retry, restart with unchanged message IDs, failed draft flush on quit and confirmed operator commands refused before mutation. Verification: 970 Native checks (20 new) and all 2,103 Python tests pass; Python compile checks pass. Runtime writes in the failure scenarios use disposable state. The release is Native 0.43.1 (50).

## Session Spine Single-Turn Forward Writer / P2l / Native 0.43.0

P2l activates the first deliberately narrow production bridge to the already tested P2g/P2h/P2i contracts. It is reachable only from one exact-linked assistant answer after fresh Live Preview, a current per-launch `ARMED` P2j grant and separate `ACCEPTED` P2k rehearsal. A first bridge call returns a content-free read-only preview binding the exact conversation/message/run lineage, current history and Work Session hashes, all P2j/P2k hashes, the optional installation identity and the fixed private paths under the Native state root. Swift independently checks its closed schema, hashes and macOS `/var` path aliases. The final button requires a checkbox plus the exact deterministic `CONFIRM-SESSION-SPINE-<16 hex>` phrase.

After that explicit action, Native re-resolves every source and obtains a second identical preview before writing anything. It then saves and reads back the complete current Native history. A changed readback stops before identity/intent/Spine, clears all one-time grants and requires a fresh preview; confirmed saved bytes are not rolled back. A stable readback creates or exactly verifies one private installation identity. Python revalidates those bytes and can then prepare one immutable P2i intent, perform one P2g compare-and-swap commit and add one immutable P2i commit marker. The returned self-hashed receipt records each write boundary. The UI exposes no second-run button after receipt.

Crash-window recovery remains evidence-driven: identity-only state can be re-reviewed as a fresh exact candidate; an exact prepared intent or missing commit marker receives a new recovery token; an already closed intent returns a read-only `CLOSED` preview with no token; unknown, conflicting, torn, symlinked, unsafe or unrelated evidence remains blocked without cleanup. P2l does not infer legacy pairs, migrate or backfill old turns, retry automatically, repair/delete/compact data, call a provider/model/slash command/tool, replay tools, change permissions or alter Context Injection. It cannot automatically ingest subsequent turns and adds no background worker. The full writer sequence is exercised only in disposable synthetic state in this milestone; the operator's personal identity/intent/Spine paths remain untouched until a separate exact UI activation.

Eight Python regressions bring `scripts/run_tests.sh` to 2,103 tests and eleven end-to-end assertions bring `scripts/test_native.sh` to 950. They cover strict preview/candidate validation, false identity-transition refusal, busy gating, wrong token and source drift, canonical-history drift before writer, first identity/intent/Spine commit, fixed-path changed-file inventory, lost-response no-write replay, prepared-intent recovery, run-once UI and relaunch `CLOSED` inspection. Release 0.43.0 (49) uses Rule 0 checkpoint `backups/proto_mind_backup_2026-09-04_21-41-11.tar.gz`. Final build/signature, eval, doctor, Context Injection and personal checksum evidence is recorded in the Architect Ledger.

## Transcript Scroll Stability / Native 0.40.1

After the long-lived personal window resumed, scrolling an ordinary 66-message conversation triggered a macOS CPU resource event in Native 0.40.0. The saved 90-second report measured nearly continuous main-thread CPU and footprint growth from 866.97 MB to 2369.55 MB. Its sampled stack crossed SwiftUI `GraphHost.flushTransactions`, `SelectionOverlay.updateNSView`, `NSTextField.invalidateIntrinsicContentSize`, Auto Layout measurement, `LazySubviewPlacements`, `EventBindingManager.enqueueHoverUpdateIfNeeded` and `HoverEventDispatcher`. The conversation archive was only about 211 KiB; the Python bridge stayed small and idle. Evidence therefore points to a retained SwiftUI layout/selection/hover feedback loop rather than a model, bridge, store-size or data-corruption failure.

Native 0.40.1 removes each participating feedback edge without removing the user features. The variable-height selectable transcript uses a regular stack instead of macOS SwiftUI lazy placement; selection lives on paragraph, heading and code `Text` leaves rather than the mixed container containing controls and a nested horizontal scroll; common button hover highlight remains visible but changes immediately without queued animation; duplicate hover and bottom-follow state assignments are ignored. No history schema, attachment, provider, command, cloud, Full Mac, Computer Use, Session Spine, permission or Context Injection behavior changes.

Acceptance adds five Native checks, including three repeated window-bounded layouts of 96 mixed user/assistant Markdown rows plus work-timeline controls, bringing `scripts/test_native.sh` to 921. All 2,095 Python tests and compileall pass. Release 0.40.1 (46) builds, validates and signs. A relaunched personal build survived 96 accessibility-driven scroll actions in two series, the second after an idle interval. Observed CPU peaked near 29% and returned to 0%; the first active series held RSS near 195.4 MB within 0.1 MB, while the longer idle/re-scroll window fell from an initial 214.3 MB to 197.3 MB and remained there with no upward trend. `footprint` reported 126 MB. All 48 core/export files and 33 Proto-Mind-owned private history/preferences/binding/work-session files retained their pre-change SHA-256 and inventory. Codex-owned profile databases/cache files changed normally during app-server reconnect and are outside that Proto-Mind-owned comparison. Context Injection remains disabled; Registry remains 387 commands/41 categories.

This acceptance does not reproduce the exact hours-long idle interval or prove unlimited-history scaling. Replacing lazy layout with eager stable layout is appropriate for the current bounded 66-message transcript, but a future very large-history implementation should use a tested AppKit-backed virtualized or paged transcript rather than an unbounded regular stack.

## Paged Transcript Rendering / Native 0.41.0

Native 0.41.0 bounds the stable transcript introduced in 0.40.1 without changing conversation ownership or persistence. `TranscriptRenderingPolicy` initially selects the latest 80 messages from the existing complete `AppModel.messages` array. When older history exists, one explicit control above the rendered page reveals the next 60 messages. The old first rendered message is used as the post-expansion scroll anchor, so inserting rows above it does not jump the operator to the newly exposed beginning or back to the latest reply.

The policy also separates two live-update cases. While the operator follows the latest output, new messages retain the current bounded window. While the operator reads older history, the visible limit grows by the incoming-message delta so the earliest rendered message cannot be evicted underneath the viewport. Conversation selection resets the presentation window to the latest 80. None of these presentation values are serialized: all messages remain in the existing in-memory conversation and private history, and reopening an older page performs no bridge/provider/model request, file read, history write, migration, permission change or Context Injection change.

Six new Native checks bring `scripts/test_native.sh` to 927. They exercise a synthetic 1,000-message conversation, exact initial and expanded ranges, end-of-history clamping, incoming-message anchoring in both follow modes, repeated window-bounded layout and full message retention without state writes or provider connection. A separate 240-message live UI fixture verified `hidden 160` to `hidden 100`, preserved the old first visible message after expansion and remained idle at 0% CPU; RSS moved from roughly 172 MB to 182 MB after constructing 60 additional rich message views, with no ongoing growth observed.

This is bounded initial rendering, not recycling. Each explicit page expansion intentionally retains the additional views for the current conversation, so repeatedly loading every page can eventually construct the entire transcript. The next escalation should be an AppKit-backed reusable row implementation only if production measurements show this explicit paging contract is still insufficient; no speculative framework rewrite is part of 0.41.0.

## Instruction Receipt / Native 0.37.0

Successful ordinary Codex and Ollama Sends now attach an optional `proto_mind.native_instruction_receipt.v1` object to their existing private `proto_mind.native_work_session.v1` record. It is built from the same final `PreparedLocalInstructions` and mode-specific developer contract used by the real provider path, after the existing pre-provider source revalidation and before dispatch. The receipt records only provider/mode/Persona state, selected-memory IDs and counts, correction-hint count, and each ordered Proto-Mind-owned layer's source, placement, Unicode-character count and SHA-256. A canonical metadata projection and receipt SHA-256 bind the closed structure. Prompt text, memory content, correction text, provider-owned instructions and private reasoning are structurally absent.

The existing Work Session inspector independently checks the exact field set, fixed safety claims, provider/mode/layer relationships, canonical hash material and receipt hash before showing compact evidence. A receipt may exist only on a completed record whose provider and access mode match. Invalid receipt-bearing records are ignored with a visible storage warning and are never repaired or rewritten. Older work sessions remain valid without migration; Mock, slash/operator commands and failed provider turns receive no fabricated completed receipt. The surrounding historical `answer_preview` keeps its existing behavior and is not claimed to be content-free.

The receipt proves that Proto-Mind locally assembled those instruction bytes for the provider call. It deliberately sets `provider_delivery_verified=false`: an unkeyed local hash does not prove transport delivery, provider interpretation, authenticity or access to upstream system instructions. No new provider call, command, permission, dependency, thread lifecycle, automatic retry, Context Injection behavior or core/export schema is introduced. Runtime persistence is limited to the existing successful work-session completion write.

Verification adds five Python regressions and nine Native checks: exact Codex and Ollama provider-path parity, absence of sensitive instruction content, strict tamper refusal, successful work-session persistence, legacy compatibility, access-mode cross-checking and read-only rejection of a corrupted saved fixture. The mandatory suite passes 2,012 tests; `scripts/test_native.sh` passes 872 checks, Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Registry remains 387 commands/41 categories. Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-04_05-53-50.tar.gz` and `backups/proto_mind_native_state_2026-09-04_05-57-24_instruction_receipt.tar.gz` (Native-owned state only; Codex credentials/profile/runtime workspace excluded).

## Local Instruction Inspector / Native 0.36.0

The pre-Send Context desk now exposes the complete current instruction text authored by Proto-Mind without claiming access to the provider's hidden layers. Codex shows its dynamic `baseInstructions` and exact static Chat or Full Mac `developerInstructions`; Ollama shows its per-request system message. Every layer carries an explicit local owner, source, app-server placement, Unicode-character count and SHA-256. A canonical projection hash binds the complete displayed contract. Legacy Cognitive Core and Brother Persona sources are visibly distinct. Mock and operator commands bypass this envelope and receive no invented layer.

`native_instructions.py` is the single assembler used by both production Codex/Ollama Send and inspection. The bridge builds a detached read-only projection from the current draft, Observer state, pending correction hints and, only when requested by the Observer, the existing shared-core retrieval with `track_usage=False`. It does not initialize a missing store, update usage counters, call a model/network, start/resume/refresh a provider thread, execute a command, grant Full Mac or persist a Persona receipt. Swift independently verifies exact fields, route combinations, text bounds, each layer hash and the canonical projection hash before rendering. Changing Persona or Full Mac state invalidates the open preview; the ephemeral Full Mac token is request-only and is never returned in the projection.

The inspector cannot read or reveal upstream provider-owned system instructions, and it never requests or displays private chain-of-thought. Attachments, criteria, project notes and selected skills remain separately visible user-context sections rather than being relabelled as hidden instructions. Automatic skill selection may still use its existing separate ephemeral provider request and is not included in this local instruction projection. Send always revalidates current sources and recomputes the assembler output; therefore a preview proves exact bytes at inspection time, not that state will remain unchanged or that the provider will interpret those bytes as intended. These unkeyed local hashes prove internal consistency, not authorship, authenticity or provider receipt.

Verification: seven new Python regressions are included in the mandatory suite, bringing `scripts/run_tests.sh` to 2,007 tests. They cover exact Chat/Full Mac/Ollama placement, byte-compatible legacy construction, Brother projection, operator/Mock bypass, read-only memory retrieval and tamper refusal. `scripts/test_native.sh` passes 863 checks, including independent Swift validation, current Full Mac grant projection and immediate token removal after disable. Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Registry remains 387 commands/41 categories. Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-04_05-08-38.tar.gz` and `backups/proto_mind_native_state_2026-09-04_05-08-56_instruction_inspector.tar.gz` (Native-owned state only; Codex credential/profile/runtime workspace excluded).

## Native Instruction Contract Refresh / Native 0.35.0

Chat and Full Mac provider threads now carry a local SHA-256 fingerprint of the exact static developer-instruction contract used when each mode binding was created. The fingerprint binds a versioned domain, access mode and instruction bytes; `codex_threads.json` stores only that digest alongside the existing private provider ID/workspace metadata, never the instruction text. Dynamic base context such as selected memories, Persona state and current task is deliberately excluded so normal per-turn context changes do not rotate a durable thread.

`codex_threads.json` v3 reads v1 and v2 registries without rewriting them. A v1 row remains mode-ambiguous historical data. A v2 mode row has an unknown contract and is therefore stale against the current application. Settings and Context preview report that state locally; preview keeps bounded local history in the exact next-turn manifest and performs no provider call or migration.

Only an explicit ordinary Send may refresh a stale mode. Proto-Mind calls `thread/start` with the current sandbox, cwd, approval, base and developer instructions, validates the returned policy, then checks the old ID/workspace/contract and atomically replaces the local registry file with exactly that mode updated. Reused provider IDs, workspace drift, a concurrent in-process binding change, malformed storage or failed policy validation stop before `turn/start`. The new thread receives up to 12 bounded local messages once for continuity; the following unchanged-contract turn uses normal `thread/resume`. The other mode keeps its provider ID, timestamps, workspace and model metadata; a v2-to-v3 save necessarily adds the new contract field and canonicalizes the registry JSON. No provider deletion call exists: the former rollout remains in the isolated Codex profile, although there is not yet a UI to browse or relink retired provider threads. The registry has no cross-process lock, so running multiple Native bridges against one private state directory remains unsupported.

The completed turn's existing provider-thread evidence reports `started`, `resumed` or `refreshed`, the current contract hash prefix, whether a refresh occurred and that provider history was not deleted. This is lifecycle evidence, not proof of semantic equivalence between prompts. A SHA-256 match proves exact local contract bytes, not that the provider interpreted them as intended. Manual **Start New Codex Session** remains available for operator-chosen reset and still removes only local bindings.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-04_04-29-34.tar.gz` and `backups/proto_mind_native_state_2026-09-04_04-29-34_instruction_contract.tar.gz` (32 Native-owned entries; Codex credentials/profile/runtime workspace excluded). No new command, dependency, provider permission, tool or Context Injection behavior is introduced. Verification and personal-state acceptance are recorded in the Architect Ledger.

## EV-04 Source-grounded Memory Suggestions / Native 0.34.0

The local memory loop now connects an explicit operator statement to a small optional review card, then to existing project recall. It does not require opening a form for every task or generate an extra model request.

1. Complete an ordinary Codex turn in a selected workspace. The per-chat brain menu defaults **Suggest notes from my messages** on; local providers, operator commands, opt-out, missing workspace and incomplete turns bypass this path.
2. Anchored Russian/English statements such as `Мы решили...`, `Я предпочитаю...`, `Our project uses...` or `Lesson learned: ...` may produce a collapsed **Worth remembering?** card. Only the exact original operator text is examined, never the assistant answer, recalled notes, file/PDF/image content, tool results or older history.
3. **Review and save** opens the whole original quote, kind, run ID, source SHA and exact project folder. The preview is read-only. No summarization, hidden inference, new fact verifier or persistent proposal queue is involved.
4. A separate acknowledgement and **Save note** send the exact hash-bound preview token through two fixed private bridge methods, `memory_suggestion_preview` / `memory_suggestion_save`. No manual token copying is required. The backend rederives the exact quote and calls the original `NativeProjectMemory.save`; it accepts neither an arbitrary replacement body nor a supersession ID.
5. The new immutable note carries `source=operator_explicit`, `verification=operator_asserted_not_independently_verified`, `executable=false`, `automatic_learning=false`, and a source run/input hash/Unicode-offset description in the existing basis field. It can participate in the already implemented automatic project recall on a later manual Send. Saved notes selected for Codex go to the cloud under existing consent; the review itself is entirely local.

Bounds and refusals:

- At most two whole quotes / 600 Unicode code points each from a message up to 12,000 characters. Oversized or unrecognized text produces no candidate; it is not truncated into a claim. Extra matching statements are counted but not saved.
- Current notes in the exact launch-root/workspace identity are checked for normalized exact duplicates. Same-message duplicates are suppressed. Different decisions are not semantically merged; no existing note is silently superseded or repaired.
- Quoted/code/pasted examples, common hypotheticals/questions and obvious secret markers are conservatively skipped. This is a high-precision phrase heuristic, not comprehensive redaction, language understanding, conflict detection or permission enforcement.
- Source run ID/fingerprint, provider/completion, conversation, folder path/device/inode, original input SHA/length and exact quote offsets/hash must agree. Changed/deleted run evidence (including later manual journal review), workspace replacement, unsafe Context settings or private-note issues refuse review/save. Review again through ordinary project notes if historical evidence is no longer available; no source is reconstructed.
- Preview/save recheck the current source and existing note snapshot. The cooperative note writer supplies its existing atomic/no-overwrite guard; there is no cross-store filesystem transaction or protection against a fully privileged concurrent attacker. Hashes prove consistency, not truth or a digital signature.
- Invalid optional suggestion projection does not turn a completed answer into an error or trigger a retry. New optional chat fields preserve content-free source metadata plus the original user-message ID; Native verifies them before display/save/load. No-card turns do not persist an empty report. Metadata is excluded from model history replay. Existing history v1-v5 stays readable without a migration or load-time rewrite.
- Saving hides that suggestion in the current UI process. After restart, an old card can still be visible; fresh review detects the saved duplicate and refuses another write. No global warning suppression or automatic history cleanup is added.

Mutation boundary: calculation, cards, review and cancellation are read-only. Only explicit confirmed Save may add one immutable private `project_memory/` record and its cooperative lock. It does not write core data, exports, work journals, native conversation history, legacy memory, learned skills or Context settings, and never sends a task/model/tool request. The already-existing ordinary Send still records private conversation/work evidence and runs its established core memory/session logic; this milestone is not a global read-only promise for chat.

Rule 0: `backups/proto_mind_backup_2026-09-03_05-18-46.tar.gz` and `backups/proto_mind_native_history_2026-09-03_05-18-46_learning_suggestions.tar.gz`. The latter contains Native-owned history/preferences/bindings/work sessions, excludes credential profiles, and no private project notes or learning-history files existed at checkpoint time. Registry stays 387 commands / 41 categories; no new dependency, model tool, permission or slash command. Test totals, release verification and personal checksum acceptance are recorded in the Architect Ledger after verification.

## EV-04 Automatic Project Recall / Native 0.33.0

The Codex composer's brain-icon menu now enables **Automatically recall project notes**, default on per conversation without rewriting old history at load. A normal task can receive relevant current notes without a manual attachment form. The operator can disable it; any explicit project-note selection wins for that turn, with no hidden merging. Skill selection remains separate. Slash/exact natural operator routes and Mock/Ollama bypass automatic note reads.

`native_project_recall.py` reuses the fixed private `project_memory/` reader and exact launch root + workspace path/device/inode scope. Only explicitly saved, active versions are candidates; superseded records and notes belonging to a different folder/core are never included. Ranking is deterministic informative Unicode content-token overlap, casefolded with Russian yo/e normalization and a small RU/EN stopword set. Provenance/basis text is not scored. Ties use saved timestamp and ID; the output contains at most three whole notes and 6000 Unicode content-plus-basis characters. Omission is visible, not truncation. No meaningful match means no note, not a guessed recollection. This first slice has no stemming, translation, semantic search, attachment-content matching, vague-continuation inference or new model request.

Local **Context** preview includes the exact selected note text/basis and source IDs/hash metadata without cloud traffic, writes or a coordinator turn. Ordinary Send with the existing cloud permission repeats the selection. If the operator viewed a usable preview for the same task/scope/mode, `expected_project_snapshot` binds its source snapshot; changed sources refuse before main dispatch. Revalidation also runs after any skill selection, immediately before main dispatch, and immediately before the provider call. A source/config/scope change never silently swaps notes or retries. Reads are best-effort, not a global filesystem lock: the namespace snapshot hashes validated canonical immutable record IDs/hash pairs, so whitespace-only reformatting is not a semantic source change. The private reader scans up to 200 records across scopes before filtering; it is not a separate physical store per folder. No other working-folder traversal is introduced.

Missing storage returns an empty report and is not initialized. Missing workspace or initially unreadable/invalid private records/config produces visible unavailable status and ordinary processing without automatic notes. Duplicate JSON setting fields/non-finite values now make the shared read-only Context status unknown instead of accepting an ambiguous value. Context Injection must be provably disabled for this recall path; no setting is changed. Once a usable snapshot was taken, later uncertainty refuses the main task rather than falling back. Manual selection retains its stricter refusal semantics.

Only the selected content enters the existing Codex user-context adapter as quoted untrusted operator assertions, not verified facts, system instructions or additional permissions. The skill-selector prompt does not receive these private notes. Chat remains tool-free; Full Mac uses the same separately authorized broad grant. Off/no-match turns identify earlier provider-history notes as historical, but do not erase that provider history or prevent its answer from mentioning earlier conversation. Legacy core recall remains shared and unchanged. Ordinary Send still records its existing private work session/chat and may perform its pre-existing cognitive-store writes; only note retrieval and the context preview are read-only. There is no automatic note creation, promotion, learned skill, counter update, export, new background work, model-to-command dispatcher or Context Injection activation.

The optional `proto_mind.native_knowledge_context.v2` manifest records `selection=automatic_project_recall`, current note ID/record/content hashes, and a closed `project_recall` report: algorithm, task/conversation/workspace/mode, canonical namespace snapshot hash, current/matching/omitted counts, selected IDs, characters, fixed explanation, `read_only=true`, `model_call_performed=false`, `permission_granted=false`, `automatic_learning=false`. It can coexist with an explicitly selected skill reference. Swift validates the actual preview contents and scope; result metadata must agree with the private run. Old v1 manifests/chat archives load without migration; the optional per-chat switch is saved only by existing explicit history edits. Chat and journal show collapsed provenance reports, not duplicated note bodies or new reasoning transcripts.

Live fixture evidence: `scripts/eval_native_project_recall.py --live --model gpt-5.6-sol` passes eight tool-free subscription cases: RU port recall, EN accent recall, supersession, unrelated request, other workspace, opt-out, current-note replacement in the same durable thread, and opt-out in that resumed thread. Eight normal generations, zero additional selector generations; host checks confirm exact selected IDs, preserved synthetic note/core/workspace bytes and no agent receipt. Color-name capitalization is accepted as equivalent; case-sensitive deployment codes and numeric values stay exact. These are narrow source-grounding checks, not proof of general recall quality or guaranteed history erasure. No personal note/core/conversation data is sent, and the existing subscription profile is reused without credential copying. The opt-in harness is not part of app startup or routine tests.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-03_04-18-39.tar.gz` and `backups/proto_mind_native_history_2026-09-03_04-18-40_auto_recall.tar.gz` (Native-owned history/preferences/bindings/work sessions only; credentials/profile excluded). Release, complete test totals, visual acceptance and personal checksum preservation are recorded in the Architect Ledger after verification. Next proposed slice: source-grounded learning suggestions with a visible review boundary, not automatic promotion or silently seeded project notes.

## EV-04 Built-in Starter Skills / Native 0.32.0

**Skills / Auto > Built-in set** reads four application-authored procedures without a model call, file write or Send. The pack lives in `proto_mind/starter_skills.json`, version `1.0.0`, with `origin=bundled`, `learned_from_user=false` and `executable=false`. It is implementation data, not a new memory store or a claim that the system learned from the operator. Each contract has a trigger, preconditions, steps, permissions, verification and known failure modes:

| Stable ID | Intended task | Boundary |
| --- | --- | --- |
| `builtin.project_orientation` | Find project entry points, core logic and tests | Read only; do not turn orientation into an unrequested change |
| `builtin.verified_change` | Implement a scoped change and check it | Respect existing permissions/Rule 0; verify results, do not publish implicitly |
| `builtin.failure_diagnosis` | Explain a failure from observed evidence | Diagnose without repair unless separately requested |
| `builtin.work_handoff` | Summarize completed work and the next step | Distinguish historical checks from current evidence; no hidden history search or resume |

`native_starter_skills.py` enforces a closed schema, exactly four fixed IDs, non-executable authored contracts and a 40 KB no-follow regular-file read. Canonical pack/contract hashes identify content, not truth or a digital signature. A fixed parameter-free `starter_skills` bridge RPC returns a read-only hash-checked snapshot; the SwiftUI sheet independently validates it and exposes no execute/apply action. Its Russian headings display the original English procedure contracts.

Auto now combines those four entries with the existing eligible learned library. The catalog still has at most 32 entries: four slots are reserved for the pack and the first 28 eligible learned records by stable ID fill the remainder. Counts/omissions are visible; no hidden keyword prefilter is added. Personal records under the reserved `builtin.*` namespace are excluded. Learned eligibility and the conservative source/config gates remain unchanged: missing, unreadable or unsafe core/config snapshots disable all automatic guidance and allow the ordinary task path; they do not initialize stores. The pack viewer works independently. An invalid pack or pack/source drift refuses dispatch rather than silently replacing content.

One existing tool-free ephemeral Codex request selects zero to two offered IDs. Full contracts then become optional quoted guidance for the existing main turn, not instructions that grant authority or a procedure interpreter. Chat remains tool-free; Full Mac retains only its separately authorized existing broad tools. The pack is rechecked with the source stores before selection, after selection and before main dispatch/provider execution. No automatic retry, background task, new API, dependency, model-to-command route or new registry command is added. With readable sources, an empty learned library now still produces the selector request; this costs subscription usage/latency. Per-chat Auto off and manual learned-skill precedence remain available.

Private `proto_mind.native_auto_skills.v2` metadata adds pack ID/version/hash and bundled/learned counts. Bundled selections contain only origin, fixed skill ID/name, version, pack ID/hash and contract hash; they cannot invent a source lesson, provenance receipt or learned lifecycle. Learned selections preserve their source fields with `origin=learned`. Existing v1 messages/runs remain readable without migration. `quality_verification=not_assessed`, `permission_granted=false` and `automatic_learning=false` stay explicit. Inspection/selection never update core skills, counters, memory, project notes, learning history or Context Injection. Ordinary Send still has its pre-existing private chat/journal and cognitive-store behavior, not a new global read-only promise.

Validation: 1822 Python tests (12 new) and 783 Native checks (15 new) pass. Coverage includes malformed/symlink/duplicate packs, no source writes, legacy-only and mixed catalogs, namespace spoofing, origin-specific metadata, v1 compatibility and pack drift before main execution. `scripts/eval_native_starter_skills.py --live --model gpt-5.6-sol --full-access-pilot` passes 11 synthetic cases: seven Russian/English selector cases and four real foreground tasks. Independent host checks verify the project map, failure cause, unchanged diagnostic/handoff files, exact changed-file set, passing regression tests and positive/negative/zero subtraction results. The four task receipts observe 2/2/4/1 commands respectively; no Web Search or Computer Use tool was used and all synthetic core sources remain unchanged. The existing subscription profile is used without credential copying or personal history/core context. This is limited fixture evidence, not a guarantee of model selection quality, proof of general skill effectiveness or autonomous learning. The harness is opt-in, never part of app startup or normal tests.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-03_02-03-54.tar.gz` and `backups/proto_mind_native_history_2026-09-03_02-03-54_starter_skills.tar.gz` (Native-owned history/preferences/binding/work-session files; credentials/profile excluded). Release, visual and personal-checksum acceptance is recorded in the Architect Ledger after verification. At this milestone, automatic project recall and learning suggestions were separate future slices; 0.33.0 above delivers bounded local recall.

Mixed-catalog compatibility: the earlier six-case `eval_native_auto_skills.py` harness also passes against the new catalog, including the real CSV task and exact unchanged input. The initial old-ID-only diagnosis assertion failed when the model chose the new failure-diagnosis template. Both that template and the prior Python-inspection fixture explicitly cover this request, so the updated test accepts exactly either single selection, not arbitrary/redundant matches. CSV still requires its precise learned fixture ID; casual and unrelated tasks still require no selection. The separate starter harness retains exact fixed-ID expectations. Overlapping procedures can yield different valid choices; no deterministic model-choice guarantee is implied.

## EV-04 Automatic Skill Guidance / Native 0.31.0

This section records the original learned-only milestone; 0.32.0 above extends its catalog and private metadata without changing the execution boundary.

The normal Codex composer has **Skills / Auto**, on by default for new and old conversations without rewriting them on load. An operator can turn it off for a conversation or prepare a specific skill manually, which takes priority for that turn. There is no mandatory skill, goal or acceptance form. Existing slash/exact natural commands and local Mock/Ollama providers do not call the selector. Project-note attachment remains explicit.

On Send with Auto enabled, `native_auto_skills.py` reads only the existing Skill Library, persistent source lessons and Context Injection setting through the bounded no-follow snapshot reader. The same `verified_guidance` boundary serves manual tasks: active/current-source, provenance-verified, restart-safe, non-executable authored procedures, including verified restored skills. Provenance is not a claim of effectiveness. Invalid/legacy/archived records are excluded, not repaired or promoted. Missing, unreadable or unsafe source/config state produces an explicit unavailable report and ordinary task processing without skill guidance; it never initializes a library or changes Context Injection. Zero eligible skills means zero selection requests.

For a nonempty catalog, a separate **tool-free ephemeral subscription Codex turn** sees the current task, at most four recent bounded messages and up to 32 compact catalog entries in stable ID order. It receives names/summaries/triggers and bounded permission descriptions, not full procedures, source lessons, attached file/image/PDF payloads, private receipts or access tokens. The UI context desk explains this extra cloud input/cost before Send. Output is closed JSON with zero to two offered IDs, one bounded public rationale and up to four suggested checks. Duplicate/unknown IDs, extra fields, malformed/oversized output or attempts to use tools fail before the main task. There is no second API, embedding, keyword auto-execution, model-proposed command dispatcher or automatic retry.

Codex CLI 0.151.0 accepts `thread/start.ephemeral` and `turn/start.outputSchema`; its current schema cannot add `dynamicTools` to an existing `thread/resume`. The selector therefore does not replace or rewrite durable conversation bindings. Its read-only/no-network tool policy and empty instruction sources are checked, the normal outer chat sandbox stays active, and the process closes after selection/Stop/failure. The same selected model uses `low` for selection when advertised, otherwise its catalog default; the main turn retains the user's selected effort. Model network processing is still necessary for this subscription request; "tool-free" does not mean offline. This is one additional request when the catalog is eligible, not free or background computation. [Official protocol](https://learn.chatgpt.com/docs/app-server).

After selection, source bytes are rechecked, and exact current contracts are quoted as optional procedure guidance in the existing reasoner. The main task uses the same Chat or separately granted Full Mac path, with another source/grant check before dispatch/provider call. Current guidance overrides historical *selection state*, not the user's instructions; disabled/no-match turns identify earlier selections as historical data. Full Mac still has broad existing filesystem/tool authority, not a project sandbox enforced by skill descriptions. The model may plan and verify using those existing tools, but no new step executor or automatic success/acceptance rule is installed.

Optional `proto_mind.native_auto_skills.v1` metadata in the private work journal and chat stores selection state, task/conversation/workspace/mode binding, catalog/source hashes, selected IDs/version hashes, selector model/effort, public reason and model-suggested checks. It contains no second full procedure or credentials. Readers reject widened or inconsistent metadata; old messages/runs remain compatible without migration. `quality_verification=not_assessed`, `permission_granted=false` and `automatic_learning=false` remain explicit. Suggested checks are not operator-declared criteria; a completed answer is not proven skill effectiveness. No automatic uses, memory/skill/lifecycle update, learning event, acceptance, capture-consent change or new registry command is added. Ordinary Send keeps its pre-existing memory/session behavior and tool permissions; only the selection layer itself is read-only over core stores.

Limits: shared legacy library, maximum 5,000 inspected source records and first 32 eligible catalog entries (omission visible), two selected procedures, 60-second selector streaming deadline plus bounded startup/RPC waits, no embeddings/local-provider selector, no automatic new skills or learning promotion. Catalog descriptions are truncated to bounded text. The selector does not see attachment contents; tasks referring only to "this file" may need a more descriptive request. External writers are detected by best-effort SHA/scope checks, not blocked by a global transaction lock. Procedures previously sent can remain in provider history. At this personal baseline both existing skill records are excluded and zero are auto-eligible; normal tasks remain usable without selecting a skill. This was inspected, not repaired.

Validation: 1810 Python tests and 768 Native checks pass; the optional real subscription harness `scripts/eval_native_auto_skills.py --live --model gpt-5.6-sol --full-access-pilot` passes six synthetic cases. Russian/English CSV requests select the CSV procedure, Russian Python diagnosis selects the inspection procedure, casual/unrelated input selects none. In a disposable folder, one actual Full Mac turn selects CSV guidance, uses one observed command, creates `{rows: 3, total: "17.75"}` and re-reads it; independent host checks confirm the exact report, unchanged input and unchanged synthetic source stores. No network or Computer Use tool was used. The selector/main prompts use synthetic data and the existing private Native subscription profile without copying credentials; personal chat bindings/history/core stores are not sent or used by this evaluation. This is limited end-to-end evidence, not a general model-quality or autonomous-learning claim. The harness is opt-in, never part of routine tests or app startup.

Rule 0 checkpoints: `backups/proto_mind_backup_2026-09-03_01-03-31.tar.gz` and `backups/proto_mind_native_history_2026-09-03_01-03-22_auto_skills.tar.gz` (28 Native-owned history/preferences/binding/work-session files; credential profile excluded). Release/visual/checksum acceptance is recorded in the Architect Ledger after verification.

## EV-04 Operator-Guided Skill Tasks / Native 0.30.0

**Skills > a skill > Prepare task with skill**, also reachable from its evidence inspector, opens a read-only preparation form. Only an active, current-source, provenance-verified non-executable authored procedure is eligible, including a verified restored procedure. Restored availability does not prove a fresh successful use. Source stores are bounded/no-follow reads; Context Injection must remain disabled. No missing file, pilot, permission or record is initialized by preview.

The operator supplies a goal (at most 4,000 characters) and 1-8 observable criteria using the existing task contract. Review exposes the source procedure's trigger, preconditions, suggested steps, permission needs, verification and failure modes. The canonical preview hash binds exact source bytes, contract, conversation, project folder path/device/inode, goal, criteria, provider and access mode. Slash/natural operator routes and exit cannot be wrapped as guided tasks. READY means eligible preparation, not authorization or proven effectiveness.

After a review acknowledgement, **Apply to draft** changes only the existing private goal/criteria draft and an in-memory selection. It never sends, enables cloud/tools or writes core/export data. A concurrent draft edit is preserved, not overwritten. The composer chip and context desk expose the selection; goal/criteria/mode changes visibly require a new review. Changing workspace clears selection. Restart preserves the ordinary draft but drops the procedure selection and any previous Full Mac authority. There is no persisted task queue or automatic resume.

Only a separate ordinary **Send** invokes the existing cognitive/provider path. The bridge rechecks current source/scope/criteria before dispatch and again immediately before the provider call, with no silent fallback. The selected procedure enters the user-context adapter as quoted guidance, not system instructions, a script, a new command or permission. Codex still uses the subscription app-server; Chat stays isolated, Full Mac needs its existing explicit grant. Existing limits/Stop/evidence are reused. This is not a skill interpreter, autonomous planner, or hard restriction on the broad tools already granted to Full Mac. Prompted precondition/step/verification guidance is not a new enforced step engine. Mock only exercises the UI/evidence contract and explicitly disclaims understanding/execution.

The existing private work-session manifest gets an optional, closed `knowledge_context.skill_task` reference containing skill/source IDs, provenance/contract/source-store hashes, task and criteria hashes, folder identity, selected mode and `quality_verification=not_assessed`. It stores no second copy of the procedure. Readers check the reference against the enclosing run; older journals load unchanged. The journal links the current skill but preserves the historical version hashes. Existing tool observations/artifacts are evidence, not acceptance. Manual acceptance still requires every criterion checked, a completed response and current artifact/workspace checks; it writes only one private run receipt. No automatic skill-use counter, outcome event, lesson, decision or lifecycle mutation is produced. The old manual-outcome flow is separate; its pending post-restore capture writer remains uninstalled.

Limitations: shared core skills/legacy memory remain global; explicit project notes do not silently migrate them. Normal Send preserves existing core memory/session rules and Full Mac authority. Previously sent procedure context can remain in provider history, but no selection/grant is restored from it. Source rechecks are best-effort snapshots, not locks on external writers; hashes prove consistency, not truth. Model quality and automatic achievement verification are not claimed.

Acceptance: 1781 Python tests, 745 Native checks, release build 35/signature, compileall, CLI/PySide/tkinter imports and deterministic Persona/Agent evals pass. A disposable real UI workflow demonstrates missing-criteria refusal, exact task preparation, an unsent chip, matching context, one manual Mock Send, linked run provenance, unassessed outcome, unchecked-criteria refusal and separately confirmed operator assessment. It is not a live-model quality benchmark. All 48 personal core/export files and 28 Native-owned private files retain original SHA-256 and inventory; neither private new namespace was created in the personal profile. Registry remains 387 commands/41 categories, Context Injection disabled. Rule 0 checkpoints are listed in the 0.27.0 section.

## EV-04 Explicit Project Memory / Native 0.29.0

The Memory screen and composer attachment menu expose a separate project-note library, not a guessed conversion of `persistent_memory.json`. An operator explicitly supplies one `project_fact`, `preference`, `decision`, `lesson` or `constraint` with content and source/basis. Facts are labeled `operator_asserted_not_independently_verified`; notes are not executable and do not activate automatic learning.

Fixed `project_memory_list/recall/inspect/preview/save` RPCs share immutable private storage. Only exact preview-bound Save writes `project_memory/`; note identity includes the launch project, exact workspace path/device/inode and originating conversation. Conversations in that same folder can read the notes; another/replaced folder cannot. `supersedes_id` is explicit, project-local and current-only. Predecessors stay historical; broken/ambiguous linkage and corrupted records block recall/sending/saving without repair. A cooperative locked snapshot check prevents concurrent branches of a replacement. No data/exports file is rewritten.

Reading and saving do not attach notes. **To next message** selects up to five current inspected notes in UI memory only. The context desk shows exact text/basis locally; Send re-reads scope, integrity and supersession before dispatch. Current notes go to the selected existing provider as quoted user context, not system instructions or permissions. Cloud consent and Full Mac grants remain separate. Mock explicitly disclaims understanding; no additional retrieval/model call or hidden counter update is added. Private work manifests record IDs, hashes, kind, size and scope without note contents. A slash command ignores and retains the selection. Restart drops pending attachment, not the saved notes.

Limits: 200 immutable records across this private namespace, paged lists of 40, 4,000 content and 1,000 basis characters, five exact-token-overlap recall results. No embeddings, fuzzy semantics, morphology, implicit temporal decisions, deletion, auto-cleanup, background task or encryption. Hashes prove consistency, not authorship or truth. Context Injection must stay disabled for new note writes/attachment. The legacy shared core still participates in ordinary recall; this slice does not make the entire cognitive core project-isolated. Previously sent context can remain in Codex provider history. Include `project_memory/` in private-state backups.

## EV-04 Saved Learning History / Native 0.28.0

**Skills > Results and lifecycle > Learning history** separates durable historical evidence from restart-expiring live authority. Four fixed private RPCs list, preview, explicitly save and inspect immutable snapshots. A current snapshot-bound token plus historical-only acknowledgement copies only the selected skill/current source inspection and available manual-outcome, decision, keep/archive and restore original receipts. Manual outcome receipts retain the exact four linked events; unrelated conversation text/events are excluded. Full old authoring/lesson receipts are outside this first selected-skill archive; their compact durable provenance remains in the saved skill. No expired receipt is invented.

Original receipts keep their original process-only/persistence flags unchanged. The outer `proto_mind.native_learning_history.v1` archive explains that it is a later explicit historical copy, not the live object or authority. Every read checks the private envelope/body SHA-256, original known receipt schemas/hashes and manual-event linkage. The UI independently checks the exact canonical hash material, preserving Python numeric representations rather than round-tripping event confidence through Swift. Hashes prove consistency, not authorship or independent procedure quality. Current skill drift is displayed separately.

The shared fixed-namespace private record primitive reads without creating files, uses no-follow descriptor traversal and bounded regular files, and saves only under explicit foreground request. Exclusive temporary files, cooperative writer lock, atomic no-overwrite link, fsync and readback preserve prior snapshots; identical content returns the original record without rewriting. Corrupt records, symlinks, unknown files, size/count bounds and write failures fail closed with inspection advice, not repair. Crash leftovers are not silently removed. Limits: 200 snapshots, 512 KiB per record, 40 receipts and 64 manual events per snapshot; no deletion/rotation/import/rehydration or background save.

History is bound to the exact launch project, conversation, workspace identity and skill ID. It does not make the legacy shared Skill Library project-isolated. Core stores, exports, private conversations/preferences and live pilot state stay unchanged; only explicit Save writes `learning_history/`. Add that directory to private-state backups; `/memory backup` remains the separate project backup. Context Injection, provider choice, Full Mac grant and Registry 387/41 are unchanged.

The current goal's Rule 0 project/private checkpoints cover the pre-feature state; acceptance fixtures are disposable, with no personal skill or model invocation. Verification results are recorded in the Architect Ledger.

## Storage And Launch

```bash
scripts/build_native_app.sh
scripts/run_native.sh
```

Requirements: macOS 14+, Apple Swift Command Line Tools, existing Python 3.11+, and the existing project checkout. No new Python or Swift package dependencies are added. Codex CLI is optional and required only for the subscription provider; the tested installation is the Homebrew-prefix CLI with the built-in macOS `sandbox-exec`. Nonstandard CLI installations outside the allowed runtime directories may be refused rather than silently relaxing filesystem isolation. The builder uses the shared Python selector and writes machine-local paths into the ignored app bundle. The app is locally ad-hoc signed, not notarized or independently portable.

Private UI state lives outside core stores:

```text
~/Library/Application Support/ProtoMindNative/
    conversations.json       atomic v6 manifest, file permissions 0600
    .history.lock            persistent cooperative dialog read/write lock
    chat_objects/            immutable conversation JSON objects, 0700/0600
    history_backups/          retained manifests and pinned legacy/recovery copies
    preferences.json         atomic explicit cloud opt-in, permissions 0600
    work_sessions/           per-run public evidence, private 0700 directory
        <uuid>.json          atomic bounded run records, permissions 0600
        .writer.lock         cooperative normal-turn/manual-review writer lease
    learning_history/        explicitly saved immutable skill evidence, private 0700/0600
    project_memory/          explicit immutable project notes, private 0700/0600
    codex_threads.json       Native conversation/provider thread bindings, 0600
    codex-profile/           credentials/config and durable rollouts managed by Codex itself
    codex-user-home/         isolated child HOME
    codex-empty-workspace/   no project checkout exposed to Codex
```

Conversation history can contain private messages, answer evidence, raw core reports, selected-image/PDF paths/hashes/page metadata and per-run notice display preferences, but not attached image/PDF bytes or extracted PDF text. Answers may quote sources and are still persisted normally. Display preferences do not enter model history. It is not a redacted export. Current writes use a v6 manifest with separate immutable conversation objects; v1-v5 load without rewriting or document reads. The next save preserves the exact legacy archive before conversion. Invalid or unknown-version history blocks ordinary saves and offers explicit verified recovery. The previous global 50 MB ceiling is replaced with a 50 MiB per-dialog bound and 10,000-dialog limit. The last 20 automatic snapshots are retained in addition to pinned migration/recovery copies; cleanup only removes verified objects unused by all retained manifests. See the 0.46.0 contract below. `codex_threads.json` contains identifiers, not transcripts, but the separate Codex profile can contain the full provider rollout. Do not publish this directory. Backing up Native state/provider history is separate from the existing project `/memory backup` archive.

## Verification And Evidence Ceiling

The following is historical foundation evidence. Current suite counts and release checks are in the [Architect Ledger](PROTO_MIND_ARCHITECT_LEDGER.md#current-verification-baseline) and the latest release section.

- `scripts/run_tests.sh`: 1,497 tests pass (1,491 previous + 6 Computer Use discovery/configuration/privacy regressions); compileall passes and optional pytest is not installed.
- `scripts/test_native.sh`: 349 dependency-free Swift checks pass, adding explicit Web Search/Computer Use capability disclosure to the previous conversation-bound context/session, PDF, notice/review-availability, attachment-layout/drop, image, criteria/review, context/artifact, work-session, menu/sidebar, model/effort, library and grant regressions. Real stdio/PDFKit checks use code-only temporary fixtures and Command Line Tools without requiring XCTest from a full Xcode installation.
- `scripts/build_native_app.sh`: release build, plist validation, local signature verification.
- Initial Codex 0.136.0 compatibility probes covered initialize, signed-out `account/read`, and ephemeral `thread/start` with the expected read-only/no-network policy. Current Codex 0.151.0 compatibility and real Sol/menu acceptance are recorded above. Future macOS/CLI changes require rechecking this boundary; no unsupported option is silently ignored.
- Live native UI smoke uses temporary project data and UI state, not personal memories. A compositor screenshot is needed for visual QA; AppKit `cacheDisplay` alone can omit SwiftUI layers.
- v4.0b UI smoke covered a long source directory, file preview/attachment, Mock-only normal turn, Markdown/code rendering, rename, archive, restore, and persisted workspace binding. A native split-layout overflow found by visual QA was removed; long lists scroll inside the viewport without displacing the header/sidebar. Mock explicitly reports that it did not analyze source contents.
- v4.0c live UI smoke covered three library screens, Russian case-insensitive search, historical memory/archive filters, focused-goal priority, plaintext skill commands/HTML, long-line wrapping, and a visibly malformed synthetic source. No model call was made. Synthetic data hashes stayed unchanged until deliberate fixture corruption; library-only navigation created no native state directory. Personal stores read cleanly (20 memory records, two goals, two skills), with unchanged core/export hashes. This validates viewing, not semantic truth of those records or a new execution capability.
- Live `proto_mind/data` and `proto_mind/exports` retain all 48 pre-change SHA-256 values. Live Context Injection remains disabled. Existing accepted legacy warnings are not migrations to perform as part of this UI change. UI smoke state and any operator experimentation in that window were isolated in a temporary copy, not imported into the main stores.
- v4.0b checkpoints: `backups/proto_mind_backup_2026-08-31_05-59-34.tar.gz` and the UI-history-only `backups/proto_mind_native_history_2026-08-31_0605.tar.gz` (no credential copy). The personal native profile is bound to the actual project folder, and its cloud permission was enabled under the operator's explicit instruction.

### Live Subscription Acceptance: 2026-08-31

- Before the real chat smoke: project checkpoint `backups/proto_mind_backup_2026-08-31_07-56-50.tar.gz` and native history/preferences checkpoint `backups/proto_mind_native_history_2026-08-31_07-59-38.tar.gz`. The native checkpoint excludes the Codex credentials/profile.
- The operator completed personal browser sign-in. After reopening the official flow from Native and checking account status, the separate profile reported a connected ChatGPT Plus account. A browser ChatGPT session alone is not proof that the Native profile is connected; use the app's account status.
- Two actual Native turns completed with the account-default subscription model and `codex_subscription` backend evidence, without API-key or Mock fallback. The first returned the requested `Proto-Mind connection verified.` line.
- The second used the actual bound project folder: preview and explicitly attach only `native/Info.plist` (919 characters, SHA-256 prefix `7da907ae5732`), then request its version and bundle identifier. The answer correctly returned `0.2.0` and `local.proto-mind.native`; the UI showed the attachment manifest and completed-turn evidence. No model filesystem tool was granted or invoked.
- Both probes selected no memories, were judged non-durable, and stored no memory. All 48 files under `proto_mind/data` and `proto_mind/exports` retained their pre-smoke SHA-256 values; Context Injection stayed disabled. Native conversation/authentication state changed intentionally outside those stores. This is not a promise that all future successful normal turns are read-only: existing core memory decisions still apply.
- This proves the current Mac/profile's normal chat and explicit file-context path, not every subscription model, future quota/authentication failure, or independent deployment. Failure/refusal paths remain covered by isolated tests; Ollama was not live-tested in this acceptance.

## Next Steps

The current sequence and remaining capabilities are maintained in [Current Direction](PROTO_MIND_EVOLUTION_ROADMAP.md), avoiding a second, drifting task list here. After the reliability and structure batch, the operator chose everyday interface refinement, followed by a separately scoped functional expansion.

## Scalable Work Session History / Native 0.45.0

The journal previously stopped all new turns at 500 saved runs, scanned and parsed the whole directory before each turn, and exposed only the newest 30 runs. Older exact-linked messages could therefore fail to open their Work Session or Session Spine even though their source file remained intact.

Independent turns now check only their own unused UUID under the existing writer lock and retain the current bounded-record/CAS/fsync writes. They have no global run-count ceiling. An unrelated invalid record is preserved and produces a bounded browsing warning; its own ID cannot be overwritten. A continuation still validates the exact parent, fingerprint, conversation, project and workspace and scans for an existing child; incomplete or corrupt history cannot authorize a second continuation.

The read-only journal streams records and retains at most 30 candidates in Python. Each response still respects the 2 MiB record-payload budget. Its continuation cursor is bound to conversation, project and the last actually displayed timestamp/UUID, so newer incoming records do not shift older pages and the byte budget cannot skip an unseen record. Native validates page scope, order, distinct IDs and cursor progress, appends unique rows through **Загрузить более ранние**, shows the loaded/total count and discards late responses when the operator changes conversation.

Message and Session Spine actions use direct exact-ID lookup, independent of loaded pages. Native rechecks the message pair and immutable Turn Lineage before opening the run; missing or changed evidence never falls back to a neighbouring record. Refreshing an old selection reads it again so later Session Spine readiness retains fresh evidence. Reading, paging and lookup initialize no missing store and change no saved record. Existing JSON paths and schemas remain in place, with no migration or deletion.

Limits: listing a page and validating a continuation still examine the journal on disk; no persistent index or filesystem snapshot is introduced. Native retains explicitly loaded rows until refresh or conversation change. The detached P2e/P2f archive audit retains its independent 500-copied-run input budget; it does not cap the live journal or ordinary backups. Expanding that audit is separate work.

A disposable 3,002-run measurement on the development Mac recorded a complete synthetic turn in 1.32 ms with seven exact-record reads, a 30-record first page in 87.89 ms and about 399 KiB peak traced Python allocations for page reading. These are one local measurement with small synthetic records, not an end-to-end UI or long-term performance guarantee.

Verification: 2,137 Python tests (11 added), compile checks and 1,012 Native checks (37 added) pass. New cases cover more than 500 runs, byte-budget pagination without omissions, cursor scope, concurrent newer entries, read-only exact lookup, corruption isolation and continuation reuse prevention. Temporary Native bridge fixtures exercise all 66 historical runs, exact old-message and Session Spine navigation, changed/missing evidence, retained readiness, bounded layout and a conversation switch with a page in flight. Persona evals pass 7/7 + 7/7 + 8/8 and Agent evals 6/6. Optional pytest is absent. All 87 protected personal core/export/Native files retain their exact bytes and inventory.

Native 0.45.0 (52) builds successfully; plist validation and strict deep code-signature checks pass. The verified local app bundle replaces the previous bundle while preserving its files for the running process. The update is available on the next normal app restart.


## Dialog Storage And Recovery / Native 0.46.0

The previous `conversations.json` stored and rewrote every dialog on each save, shared a global 50 MB read ceiling and had no cross-process compare-and-swap. A second Native instance could overwrite a newer saved answer. Recovery from a damaged file required manual filesystem work.

### Storage And Migration

`ChatStore` now publishes immutable, SHA-256-addressed conversation objects in `chat_objects/` followed by one small atomic v6 manifest at the existing `conversations.json` path. A changed dialog is encoded and written once; unchanged dialogs reuse their objects, with file-revision checks before reuse. An unchanged archive creates no new snapshot or data write. File and directory fsyncs, private modes, regular-file checks and a persistent cooperative `.history.lock` protect the publication order. The writer compares the complete loaded manifest against current bytes under the exclusive lock. A conflict retains in-window data and offers export or loading the current history after a recovery copy.

Legacy v1-v5 archives load without a write. The next save pins the exact original archive as `history_backups/legacy-<sha>.json` before publishing v6. Legacy input is bounded below 512 MiB; the new format permits up to 10,000 dialogs, each object below 50 MiB, with a manifest below 50 MiB. A synthetic archive larger than the former global ceiling is verified. Startup still materializes all dialogs and messages in memory, and editing a very large single dialog still rewrites that dialog. These are current bounds, not an unlimited-history or fully lazy-loading claim. All app instances sharing a history should use the updated version: older binaries do not implement this lock/format contract.

### Verified Dialog Recovery

**Копии и восстановление…** is reachable from the Proto-Mind menu, Settings and a persistent save-failure notice. It exports a self-contained `.protomind-history` folder with a verified manifest and conversation objects, including visible unsaved replies and drafts. Existing destinations are never overwritten. Selecting an exported folder, an old standalone archive or a local snapshot first validates the complete copy and shows dialog/message counts. Confirmation rechecks both source and target, preserves the current on-disk bytes and in-window state, commits the selected history and verifies actual disk readback before reporting success. Changed input or target requires a new preview. Missing manifests with surviving history files open recovery instead of creating an empty replacement.

Automatic local retention keeps the latest 20 pre-save manifests. Original-format and pre-recovery copies are pinned separately. Cleanup happens after a successful commit and only removes verified objects unused by every retained snapshot. Snapshot dependency checks are cached by file revision so a large pinned legacy archive is not parsed on every draft save; changed or invalid evidence stops cleanup. A damaged pinned copy can therefore leave extra snapshots/objects in place until reviewed. Local snapshots share the same disk: exporting elsewhere is needed for disk-loss recovery.

The backup scope is **dialogs, drafts and dialog settings/evidence**. It excludes shared core memory, separate Work Sessions, project-memory and learning stores, provider session bindings/rollouts, credentials and original attachment files. Referenced runs and attachments remain usable only where their original separate data exists. Provider sessions are not rolled back and may still contain later messages; the restore preview states this before confirmation. This is not a full-machine restore or the detached P2e/P2f Session Spine archive-audit format. Restoring clears pending action grants and Spine readiness; it never submits a provider request or recreates access.

### Integration And Maintainability

The exact-turn Python adapter reads the complete v6 manifest and only the selected conversation object. Native and Python independently derive an identical byte envelope binding the entire manifest hash and exact conversation bytes into the existing v5 Spine handshake. Unrelated manifest changes still invalidate an old candidate. The first v5-to-v6 save invalidates the old P2l candidate before identity/Spine writes; a freshly reviewed v6 candidate can complete normally. The bridge holds the existing shared history lock through P2l preview/apply, preventing an updated Native process from changing history during that operation. Detached legacy audit budgets remain separate.

`AppModel` retains shared MainActor state while dialog, turn execution, work-journal, Spine and persistence flows live in five dedicated extensions. Python history routes have their own module. The former 29,053-line flow test file becomes a stable aggregate for 21 topic modules plus common fixtures; all 1,193 original test-method ASTs match the preceding release exactly. Test provenance counts the split sources. The current roadmap replaces obsolete future-state claims and names interface refinement as the next stage.

### Verification

The complete Python suite passes 2,147 tests, including 10 new exact-history and lock regressions; compileall passes and optional pytest is absent. Native passes 1,041 checks, including 29 new storage/recovery cases. Coverage includes a real competing process, stale-write refusal, unchanged-object reuse and tampering, publication failure, restore readback failure, source/target drift, recovery from corruption or a missing manifest, retained snapshot dependencies, the former 50 MB boundary and existing Session Spine gates. Persona evals pass 7/7 + 7/7 + 8/8; Agent evals pass 6/6.

An isolated signed QA app opens the actual recovery sheet from both menu and Settings, exports a portable copy, changes a draft and restores the earlier dialog through preview and confirmation. UI and independent disk checks confirm that the later draft remains in a recovery snapshot. No personal provider request or history migration is performed during acceptance. All 87 protected personal core/export/Native files retain their exact bytes and inventory.

Native 0.46.0 (53) is built in a separate staging directory, with plist validation and strict deep signature verification. The verified bundle replaces the local app while retaining the previous bundle for its running process. It becomes active on the next normal app restart. The first subsequent history save performs the backed-up legacy conversion if required.

## Everyday Interface / Native 0.47.0

The first everyday-interface pass gives the conversation a clearer hierarchy: a cool adaptive palette, more readable 15-point messages, a searchable sidebar and a welcome screen with idea, project and memory entry points. The sidebar keeps settings at the bottom and groups less frequent commands/diagnostics in its tools menu. Search supports ⌘F; a prepared prompt receives input focus without discarding an existing draft or sending automatically.

`ComposerView` keeps model and Mac access visible, groups context/criteria/skills/project recall in one request popover and adapts its controls to narrow widths. Selected file chips show names with full paths available on hover. Settings has four sections: models, communication, data/copies and advanced controls. Choosing model settings opens the relevant section; account, cloud consent, Brother activation, session reset and data recovery retain their existing actions and checks. Settings navigation is transient UI state, not a new stored preference.

Answers keep Copy visible and collect raw reports, memory checks, exact work-run and Session Spine links under “Подробнее”. The inspector translates known status values for display while retaining original values and reports. Public work evidence starts collapsed with the latest commentary available; “Ответ получен” describes completed model output separately from operator acceptance. The Stop button and Esc request the existing Codex cancellation path. Local Mock/Ollama/core operations still finish safely; this release does not add universal cancellation or undo earlier actions.

The source split puts sidebar, welcome and composer in dedicated files. This release changes presentation and keyboard focus only: dialog schema, provider requests, permissions, memory policy and writer gates retain their previous behavior. Specialized memory/learning/protocol forms retain their detailed workflows for later focused refinement.

Verification: all 2,147 Python tests and compileall pass; optional pytest is absent. All 1,051 Native checks pass, including 10 new geometry/state checks covering composer widths of 360/480/790 points, long model names, busy controls, each settings page and navigation without history writes or access grants. Existing provider progress/cancellation, drafts, attachments, persistence/recovery and exact-evidence checks pass.

Signed disposable QA apps verify light and dark appearance, a minimum-size window with the inspector, request-popover-to-criteria navigation, prepared-draft focus, ⌘F filtering, ordinary and delayed Mock responses, Esc reaching the stop request while the local operation finishes safely, paging from 80 to 140 visible messages in a 240-message dialog, an interrupted-run notice, answer-detail navigation and Settings-to-verified-backup preview. The UI run makes no cloud model request and does not claim a new live cloud-streaming test. No personal history is migrated or provider session reset; all 87 protected personal core/export/Native files retain their exact bytes and inventory.

Native 0.47.0 (54) is built in a separate staging directory with plist and strict deep signature verification. The local app is replaced while preserving the previous bundle for any running process. The new interface becomes active on the next normal app restart.

## Files And Browser Panel / Native 0.48.0

The operator's screenshots guide a familiar neutral appearance: charcoal conversation surface, lighter gray sidebar/user bubbles, 16-point messages, simpler project rows and an access-left/model-right composer with adaptive compact controls. Light appearance uses the same hierarchy. Search opens on demand and retains ⌘F. Short conversations now retain the initial 80-message rendering budget while growing; they no longer prematurely hide earlier rows under the paging button.

### Everyday workflow

**Файлы проекта**, **Браузер** and the top-right **Рабочая панель** button open a work surface beside the conversation. Its divider is draggable and keyboard-accessible; it starts with equal chat/panel space and supports expanded reading or hiding without closing tabs. The plus menu adds browser/file tabs. ⌘⌥T opens a new browser tab with address focus; ⌘⇧O opens the project folder workflow. **Подробнее → Память и проверки** opens the existing answer inspector in its own sheet, preserving access to raw reports, exact run navigation and Session Spine controls without replacing work tabs.

Tabs are process-only and survive ordinary conversation changes, but not app restart or explicit dialog restore. File snapshots retain their original conversation/workspace scope; a foreign tab cannot attach to the newly selected conversation. Closing a browser stops that tab. The 12-tab limit reports a visible error without silently evicting existing pages. Switching browser tabs preserves each actual WebKit page and its own navigation history.

### Documents and web pages

Project listing now includes PNG/JPEG/PDF entries alongside the existing text allowlist. Text/Markdown reads remain inside the selected project, bounded to 256 KiB with a 12,000-character preview. Markdown has rendered/source modes and panel-local links. Images reuse validated thumbnails. PDFs reuse verified extracted text and original-file hashes while moving between pages; this is a text-page preview, not a rendered facsimile. **Открыть** uses TextEdit for text, Preview for image/PDF originals, and an explicit Finder action. It does not execute a source file through its default file association.

Previewing a document never attaches it automatically. Explicit attachment reuses current conversation/workspace, source-hash and existing text/image/PDF limits; Send rechecks its sources. A late PDF response cannot reopen a closed tab or replace a different version. Existing busy-state read gates, sensitive-path/symlink exclusions and text-only model-context reads remain in place.

Each browser tab owns a real `WKWebView` with its own nonpersistent website data. Manual HTTP(S) navigation, back/forward, reload/stop, ordinary target-blank links and external-browser handoff are implemented. Pages do not enter chat history or model context, do not receive a Native script bridge and do not grant the model browser control. File/custom URL schemes, downloads and camera/microphone capture are refused; unsupported downloads/flows can be opened externally. Website logins and tabs are temporary; bookmarking, persistent sessions, full browser compatibility and model-driven browsing remain future work. The [Apple-documented web-view ATS exception](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowsarbitraryloadsinwebcontent) permits manually selected HTTP sites without changing URLSession's transport policy. No certificate-acceptance override is installed.

### Verification and delivery

All 2,148 Python tests and compileall pass; optional pytest is absent. All 1,094 Native checks pass, 43 more than 0.47.0. New coverage exercises panel lifecycle/capacity/scope, URL policy, explicit Markdown links, PDF/image integration, stale results, no preview-induced history/core/authority changes, 240/300-point composer layouts and short-transcript growth. Existing persistence, provider progress/cancellation and evidence contracts remain covered.

Signed disposable QA apps verify both appearances, rendered Markdown and relative links, images, PDF page navigation, browser back/forward and distinct tab contents, a local HTTP fixture, remote HTTP and HTTPS pages, panel drag/expansion/hiding, narrow-window controls, selected-tab visibility, keyboard search/address focus, a Mock reply and separate answer evidence. No cloud model request is made. All 135 files in this turn's protected personal core/export/Native inventory retain their original bytes, with no added or removed files; QA uses separate project/state roots.

Native 0.48.0 (55) is built in a separate staging directory with plist validation and strict deep signature verification. The verified local bundle replaces 0.47.0 while preserving the previous bundle for its running process. The new appearance and panel become active on the next normal app restart.

## Project Memory Controls / Native 0.49.0

The operator deferred visual fine-tuning and continued the practical roadmap. **Библиотека → Память проекта** opens the selected folder's explicitly saved notes; **Общая память** remains a separate legacy collection. The welcome screen's memory action follows the selected project when one is bound. Existing attachment-menu access remains available.

### User actions and current context

**Сохранить заметку** and **Сохранить изменения** perform a fresh exact preview and the existing confirmed save after one explicit button press. The form itself shows the proposed content and whether it replaces an earlier version. Native binds the response to the unchanged form/scope, supplies the checked token internally and refuses stale content; it does not require the operator to copy a technical code or separately confirm their own typed assertion. An omitted basis is honestly labelled as a manually entered user note. Success clears the search so the new version is visible. Earlier versions retain their original bytes and are excluded from current selection.

**Убрать из памяти проекта** excludes the exact current note from future automatic recall and manual selection. **История** includes removed and superseded notes, including in bounded local search; **Вернуть в память проекта** restores a removed current version without duplicating its text or attaching it automatically. Superseded versions cannot be restored over their replacement. Automatic suggestions do not re-offer an intentionally removed exact quote. Editing/removal clears affected pending note selections across dialogs in the current app; all note changes invalidate its context preview. Other processes' pending selections are independently refused by the existing source revalidation before Send.

These actions affect project-note selection, not erasure. Original notes, earlier replies, work evidence and provider history remain. Existing per-turn provider guidance marks historical project notes as historical; this release does not claim to delete already delivered context or guarantee a model's interpretation. Shared legacy core memory, cloud consent, Full Mac access, automatic learning and Session Spine authority are unchanged.

### Persistence and compatibility

Archive/restore appends one `proto_mind.native_project_note_state.v1` event in the existing private `project_memory` ledger. It contains exact project/workspace identity, note ID/record hash, predecessor event ID, action and operator provenance; no second copy of the note text. Readers derive state from one alternating linked chain. Missing/foreign references, competing roots/branches, invalid ordering or integrity errors block recall and further writes rather than selecting a winner by timestamp.

The event preview binds the inspected item, proposed body and complete ledger snapshot. The existing cooperative writer lock, atomic no-overwrite publication, fsync and readback remain; state saves require the snapshot check even for an already present event, preventing a stale duplicate from bypassing a later restore. Note versions remain limited to 200 across the private ledger; project-memory storage reserves up to 2,000 total records for notes plus lifecycle events, allowing removal/restoration when all note slots are occupied. Learning-history storage retains its previous 200-record limit. No cleanup or migration runs automatically.

Existing v1 note files load unchanged. Older Native versions cannot interpret the new event/state contract and should be restarted into the updated release before using these controls. All UI and fault-injection writes during acceptance use disposable state.

### Verification and delivery

All 2,160 Python tests and compileall pass; optional pytest is absent. Twelve new regressions cover the lifecycle, scope/history, automatic and manual selection, suggestion suppression, invalid/forked chains, stale/replayed changes and capacity. All 1,111 Native checks pass, including 17 new checks; the focused project-memory suite passes 41. Native checks exercise token/authority tampering, exact form saving, pending selections, source preservation, history search, restoration, correction, a competing process and restart.

A signed isolated QA app verifies **Library → Project Memory**, creation without token copying, removal from ordinary search, history search, restoration and editing from port 4200 to 4300 with the old version retained. No real model is called. All 135 files in the protected personal core/export/Native inventory retain their original bytes and inventory.

Native 0.49.0 (56) is built in a separate staging directory and passes plist validation and strict deep signature verification. The installed bundle replaces 0.48.0 while preserving the previous bundle for any running process; the new controls become active after the next normal restart.

## Everyday Continuity / Native 0.50.0

The concrete gap was navigation: sidebar search matched old message text but displayed only a dialog title, while exact continuation was buried in the detailed run journal. **История диалогов** in the sidebar and **Вернуться к работе** on the welcome screen now provide a direct path from finding a saved conversation to inspecting its answer and returning to work.

### Find and inspect

Local search reads the app's saved dialog snapshot: displayed message text, titles, project paths and unsent drafts. It includes active and archived dialogs by default, offers explicit filters and exposes each matching message. Search is a case/diacritic-insensitive substring match, not semantic retrieval. It does not read hidden raw evidence, provider prompts, files or the shared/project memory stores, and makes no model call. Requests are debounced and cooperatively cancellable; results are ordered by dialog activity and displayed in groups of 60 without a new persistent index.

The preview shows the match, last request and its subsequent reply, project folder and saved draft. A later error stays visible; an older answer is not relabelled as the response to an unanswered request. Excerpts are labelled and bounded, with the complete conversation available through navigation. Saved text is historical evidence, not an automatic task-success assessment.

**Открыть это сообщение** validates the destination and jumps to that exact message. Initially only an 80-message neighbourhood is rendered, even for a far older match; explicit previous/next controls load further blocks of 60. The last-message button returns to the recent transcript. Sidebar text-search selection also targets its newest matching message. Navigation state is temporary; no new disk schema, history migration or message mutation is introduced.

### Return and continue

**Продолжить диалог / К черновику** opens the existing conversation with its current provider/model/folder settings and preserved draft/context. Reading an archived conversation keeps it archived; restoration remains an explicit action. Switching conversations invalidates a stale context preview. Normal return keeps the existing provider-session/history behavior, including the bounded local history; it does not silently create a summary of the complete archive or reset a provider session.

For a verified linked answer (including the exact answer to a matched question), **Подготовить продолжение от ответа** reuses Work Session lookup, Turn Lineage and the existing read-only continuation RPC. Only after exact source resolution and revalidation does it select the destination and save the reconstruction draft. The current dialog's draft is preserved, and a target draft, attachments, criteria, selected notes or prepared skill block replacement. Changes to the target conversation/folder during loading, altered/missing evidence and a parent that already has a continuation are refused. Legacy answers without an exact link remain readable and their conversations remain usable; a link is not fabricated for them.

The reconstructed draft quotes bounded historical fragments, asks for the next goal and requires a separate Send. Existing source/workspace checks still apply; earlier files/images/PDF pages and historical permissions are not restored. No provider call, replay, automatic acceptance, new permission, memory write, background work or multi-turn Spine ingestion occurs during preparation. The composer retains a pending focus request while a read is busy or a sheet is closing, applies it when the parent window/field are ready, and permits immediate editing at the end of the draft. Reading a specific old message does not request composer focus.

### Verification and delivery

All 2,160 Python tests and compileall pass; optional pytest is absent. All 1,147 Native checks pass, including 36 new checks; the focused continuity suite passes 36. New checks exercise archive/text/folder/draft search, old and Unicode matches, honest latest-answer summaries, bounded transcript destinations, protected drafts and criteria, unchanged archive state, exact source lookup, changed folders during an asynchronous read, edited/missing evidence, restart, explicit Mock Send and refusal to replay an already continued parent. Existing provider progress/cancellation, source checks, memory and persistence suites also pass; no new live cloud-model run is claimed.

A signed isolated QA app uses three synthetic conversations, including an archived 240-message transcript and an exact linked turn. Live checks verify both archive filters, multiple matches, the exact highlighted jump, forward page loading, draft restoration, continuation preparation and immediate typing without clicking the editor. Disk readback verifies the other draft, all old messages, archive state and exact prepared reference; the UI created no new run. All 135 files in the protected personal core/export/Native inventory retain their original bytes, with no additions or removals.

Native 0.50.0 (57) is built in a separate staging directory with plist validation and strict deep signature verification. The verified bundle replaces 0.49.0 while preserving the previous app bundle for any running process; the updated functionality becomes active after a normal restart. The next product candidate is a complete, clearly scoped private-state backup flow; current dialog copies alone do not cover memory, the work journal or local provider/session links.

## Quieter Conversation / Native 0.51.0

Delivered on 2026-09-05 in response to the operator's eight screenshot-based UI requests.

- Composer and transcript use one centered 760-point column with 48-point minimum side margins; input and response text decrease from 16 to 15 points.
- Attachments, request settings, access and model selection open in panels above their buttons. Panels scroll within the available screen height, close with Escape/outside click, and return keyboard focus. Nested skill/recall settings expand inline. Model/effort width follows its label and can truncate long catalog names in narrow layouts.
- Live public commentary is readable by default; adjacent tools collapse into short action groups. Raw commands stay in details, with output constrained to a 230-point scrolling area. Completed timelines start collapsed. Model completion retains the truthful “Ответ получен” label.
- Skills, project-recall reports, general service notices and runtime warnings move to **Подробнее → Об ответе**. Source evidence, permission controls, run/Spine navigation and actionable recovery remain reachable.
- A final card groups observed completed file edits, shows the first three files, expands the remaining list and opens files in the workspace panel. The active turn does not expose file-change rows, diffs or counters, including inside expanded action groups. Interrupted/failed turns may show edits whose individual completion was recorded.
- Added/removed lines come from complete unified-diff hunks before preview truncation. Repeated notifications are deduplicated; repeated edits to a file are summed, rather than represented as a net Git diff. Missing/malformed/binary/old preview-only statistics remain unknown. Only provider-observed file edits are listed; arbitrary shell writes are not inferred. Each tool retains up to 64 exact paths within an 8 KiB path budget. Optional metadata is saved in existing Native dialog receipts; the separately bounded work-journal format is unchanged. No provider or user-state migration is performed.

Verification: `scripts/run_tests.sh` passes **2,166 Python tests** plus compileall; optional pytest is absent/skipped. `scripts/test_native.sh` passes **1,169 Native checks**. Tests cover complete versus truncated diffs, bounded metadata, duplicate/failed/repeated edits, receipt reload, live/final visibility, grouping order, intrinsic model-control sizing, screen-edge placement and source/permission preservation.

Isolated UI acceptance uses the real workspace/composer views with synthetic live/completed receipts and the actual release executable with a disposable Mock history. Checked wide/minimum windows, grouped activity, bounded command output, final file totals, all four composer panels, effort selection, request-setting expansion/scrolling and relocated notices. Actual release keyboard paste works before and immediately after the model panel closes. This is not a new live cloud task or a claim to capture file writes the provider did not report. Native **0.51.0 (58)** builds with valid plist and strict signature; the turn's **137 protected personal files** retain their original bytes and inventory. The previous application bundle is retained for rollback; the personal application is not restarted during installation.


## Conversation Polish / Native 0.51.1

Delivered on 2026-09-05 after the operator's final composer requests and activity-animation reference.

- Composer and transcript share a 752-point centered column with 50-point minimum side margins. The composer footer is removed and its bottom inset is 8 points. Send/Stop circles are 32 points; reasoning effort uses secondary text color while intrinsic label sizing is preserved.
- The running conversation shows a rotating ring. Active status text and currently running tool summaries receive a soft highlight moving left to right; historical/completed text remains static. Animation redraws stay inside the small indicators, pause when the scene is inactive, and honor macOS Reduce Motion.
- The local npm Codex CLI used by Proto-Mind was updated from **0.151.0 to 0.153.4**. Before/after account catalog reads confirmed that **gpt-6-astra** appeared after the update. Model choices still come from the account catalog; no model is forced, no credentials are transferred, and no cloud model turn was submitted. Ephemeral sessions in disposable profiles confirmed both chat and Full Mac policy handshakes with the updated CLI. The prior npm package is retained for rollback.

Verification: **2,166 Python tests** plus compileall and **1,169 Native checks** pass; optional pytest is absent/skipped. The signed UI fixture covers wide/minimum windows, light/dark themes, active/completed tasks, the ring, status highlight, model-panel placement and short/long effort labels. The actual release executable accepts keyboard paste before and immediately after menu dismissal in a disposable history; readback confirms the entire draft and editor focus. Reduce Motion handling is source-checked, not a change to the operator's system preference.

Native **0.51.1 (59)** builds with valid plist and strict signature. All **136 protected personal files** retain their original bytes and inventory; Codex-owned caches are outside that comparison. The previous app bundle is retained and the personal application is not restarted during installation. Storage formats, access grants and user selections are unchanged.

## GitHub Connection / Native 0.52.0

Delivered on 2026-09-05 as the operator's first requested external service connection.

- **Настройки → Подключения** inspects the active GitHub CLI account and explicitly connects or disconnects it for Proto-Mind. Existing `gh` login is reused; a missing login can be completed through the standard GitHub browser flow opened in Terminal. GitHub CLI must be installed at its Homebrew location. The current integration supports `github.com`, one selected account, and the default Mac GitHub CLI configuration.
- **GitHub** in the sidebar lists repositories in pages of 30, filters loaded names/descriptions, and shows up to 20 open pull requests and 20 open issues per repository. Links open GitHub; **Обсудить** appends a link to the current active dialog draft, returns to its current input and preserves existing text and continuation. It sends no message and grants no access. There is no background polling, remote mutation or automatic clone in these Native views.
- `native_github.py` validates account identity before each operation, constructs canonical GitHub links, bounds list sizes and uses fixed argv for Native requests. CLI subprocess errors do not expose raw output. Inherited tokens, custom hosts, debug flags and hooks are excluded from the GitHub child environment. The actual credential remains managed by GitHub CLI; Proto-Mind does not read or save it.
- Explicit connection publishes `integrations.json` with schema `proto_mind.native_integrations.v1` and the selected login. Publication holds `.integrations.lock`, validates existing settings, replaces atomically and verifies readback. Corrupt or symlinked settings are refused. A private `integration-bin/proto-github` wrapper is installed before enabling; it rechecks the connection when executed. Ordinary status reads do not create these files.
- Only Full Mac Codex execution receives the wrapper in PATH and a process-local HTTPS Git credential helper for `github.com`. The wrapper passes ordinary `gh` arguments through to the official CLI; only that child uses the real Mac home needed by Keychain. Codex keeps its isolated HOME, and no global Git configuration is changed. Full Mac remains broad user-level authority; connecting a service alone is not an instruction to push, publish, comment or merge. Disconnecting disables Proto-Mind's managed connection but preserves shared CLI login; it does not revoke the account token or already granted Full Mac access.
- The Full Mac instruction contract now explains the GitHub command and remote-action intent boundary. Existing instruction-version handling refreshes an affected durable provider session on its next explicit Send, retaining its old history. Chat instructions, permissions and provider selection are unchanged. Complete private-state backups remain the next roadmap candidate.

Verification: **2,187 Python tests** plus compileall and **1,176 Native checks** pass; optional pytest is absent/skipped. Tests cover corrupted/symlinked settings, account drift, failed publication, CLI errors, bounded repository data, argument rejection, connection/permission separation and preserving drafts. The actual release executable is checked in disposable state: account reuse, repository listing/filtering, an empty PR/issue view, draft handoff, disconnect/reconnect, restart and minimum-width layout.

Live read-only checks confirm the existing Mac account through GitHub CLI **2.83.2**, `proto-github` under the Codex **0.153.4** Full Mac environment (including a login shell), and HTTPS Git access to an existing private repository. No remote write, new OAuth login or cloud model turn is submitted. The operator's requested account is connected in the primary profile; the seven accessible repositories and the installed managed command are read back successfully. All **136 pre-existing protected personal files** retain their exact bytes; only the three connection files described above are added. Native **0.52.0 (60)** passes plist/signature validation; the previous application bundle is retained for recovery and the personal app is left for the operator to restart normally.


## Complete Private Backups and Codex Usage / Native 0.53.0

Delivered on 2026-09-05 as the next roadmap stage plus the operator's requested subscription metrics.

- **Полная копия данных…**, available in Data Settings and the app menu, creates a `.protomind-backup` folder package. A manifest records original project/state paths, file sizes and SHA-256 hashes. Included scopes are Native dialogs/drafts/settings, project memory, work/learning history, Session Spine identity/store/intents, provider binding metadata, the separate Python core, and local exports/logs. Credentials and Codex profiles/rollouts, managed helpers, original external attachments, project source files and other backup packages are excluded. Unknown Native storage namespaces are refused instead of silently omitted. Bounds are 50,000 files, 2 GiB total and 512 MiB per file; links and special files are refused.
- Export saves the current Native archive first, holds existing cooperative store locks, validates source stability and verifies the copied bytes before publication. Preview neither initializes stores nor writes them, validates package hashes and decodes Native history, and shows scope/counts before the destructive action. A copy for different absolute installation paths can be inspected but not restored automatically; exact evidence links are not silently remapped.
- Restore first preserves current on-disk data in a complete before-image and current in-window messages/drafts in a separate ordinary dialog package. An immutable content-addressed plan and blobs support explicit resume or rollback. Per-file atomic replacement is recoverable across stores, not a globally atomic transaction. Immutable chat objects publish before their manifest; persistent live locks are retained. Marker files in both Native state and the core block ordinary access while incomplete; unexpected edits or corrupted evidence keep recovery blocked without cleanup. Completion receipts and generation markers prevent old Native/MemoryStore/bridge instances from writing stale state, including when a completion response is lost.
- Both restore and rollback disable saved cloud consent, Context Injection, the GitHub connection and active Codex thread bindings. Original before-image bytes remain in the preserved package; existing external service credentials are not touched. The UI requires a normal restart and retains access to both recovery copies. It never resumes recovery automatically on startup.
- **Использование и лимиты…** in the Codex model picker, Model Settings and app menu reads the same managed ChatGPT account as Proto-Mind. The official `account/rateLimits/read` multi-bucket response supplies used/remaining percentages, actual window durations and reset dates; legacy single-bucket fallback is supported. `account/usage/read` supplies optional lifetime/peak/daily activity. Null or malformed metrics remain unknown, percentages for progress are bounded, elapsed reset dates require refresh, and endpoint errors remain separate. The view refreshes on opening or explicit **Обновить**, keeps no persistent usage cache, sends no model turn, performs no token-price conversion, and consumes no earned reset. [Official account protocol](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt) and installed CLI **0.153.4** were checked; live reads from the PM account returned Plus, two quota buckets and account activity. This reflects the account signed into PM and does not assume it matches another app's login.

Verification: **2,225 Python tests** plus compileall and **1,196 Native checks** pass; optional pytest is absent/skipped. Disposable tests exercise source/target drift, malformed packages, links, lock contention, partial writes at durable boundaries, resumed rollback, before-image preservation, permission reset, stale generations, lost replies, real Native-to-Python restore and unknown/partial usage data. UI checks cover creation, preview, restore confirmation, a restored draft after restart, startup after interrupted restore, explicit rollback, quota cards, token activity and bounded scrolling. The final dismissal/quit change also receives the focused backup/usage checks and release UI acceptance.

A first complete copy of the real saved private state was created and verified locally: **135 files, 1,855,305 bytes**. Its creation left all captured source bytes unchanged. The saved dialog/snapshot inventory changed while the personal app was open during this work, so this is not a claim that the entire earlier directory inventory stayed byte-identical. No personal restore was performed. Copies on the same disk do not protect against disk loss; use **Сохранить полную копию…** to choose another storage location. Native **0.53.0 (61)** retains the previous installed bundle for recovery; the operator's open app is left for a normal restart.

## Earned Resets and Projectless Mac Access / Native 0.54.0

Delivered on 2026-09-06 for the operator's two requested improvements before the next roadmap stage.

- **Использование и лимиты… → Сбросить лимит…** appears when the managed ChatGPT account reports earned resets. Confirmation consumes one existing reset through the official `account/rateLimitResetCredit/consume` endpoint. The service decides eligibility: `nothingToReset` and `noCredit` do not apply a reset; `reset` and `alreadyRedeemed` have distinct messages. Actual quota is fetched after the action, never inferred from the outcome. No credits are purchased and no email is sent.
- An account reference, optional exact credit ID and UUID identify the attempt. Under a persistent sidecar lock, the bridge rechecks current account/availability and saves the key before the external write. Timeout, unknown outcome, lost Native response and failure to save completion preserve the same attempt across restart. **Проверить попытку** reuses that key, even if the available count has since reached zero. A stale confirmation cannot replace another pending/completed attempt. Usage reads remain free of local writes or redemption calls. The bounded `codex-reset-attempts.json` journal is excluded from restored private backups so restoration cannot revive a previously spent attempt. The installed CLI may omit `accountId`; managed-login email then provides the local account reference, and supplied credit details bind the selected redemption.
- **Доступ к Mac** now works without a selected project. A projectless grant uses the home directory as its initial execution location while keeping the conversation's logical project absent. Project notes, provider bindings, work-session records and Persona retain that unbound scope. A selected project, even the same physical directory, remains a distinct grant scope. Changing project/provider, revoking cloud consent or restarting invalidates the in-memory authority. Login alone still enables no tools.

Verification: **2,248 Python tests** plus compileall and **1,207 Native checks** pass; optional pytest is absent/skipped. Focused projectless checks additionally exercise the default automatic skills/recall settings. Fake transports cover Chat/Full Mac continuation with no logical workspace, and disposable reset tests cover all outcomes, persistence failures, stale confirmations, account/credit drift, lock contention and uncertain retries. The signed release UI was checked in an isolated code/profile copy: grant without a folder picker, cancellation without a redemption, successful quota refresh, lost response, restart, retry with the same key at zero credits, and hiding the new-reset button when none remain. No real model/tool task or earned reset was run for UI acceptance.

Read-only live verification against the PM account and installed **Codex CLI 0.153.4** returned Plus and **3 available resets**, including exact credit details. No reset journal was created or changed. The protocol was checked against the [official earned-reset documentation](https://learn.chatgpt.com/docs/app-server#8-earned-rate-limit-resets-chatgpt). Native **0.54.0 (62)** retains the previous installed bundle for recovery; the personal app remains open for the operator's normal restart.

## Live Task Updates and Limits Menu / Native 0.55.0

Delivered 2026-09-06 at the operator's request:

- The sidebar footer is **Меню**, opening upwards with **Настройки** and **Лимиты**. Its compact values show the **used** percentages for the periods actually returned by Codex; the menu adds small progress bars and the last update time. The quota entry has moved out of the model picker. Missing percentages stay unknown, values above 100% stay distinguishable, and expired/old readings are marked instead of reset to an invented zero.
- Foreground quota refreshes run about once a minute, on menu demand and after model work. They use an independent account-only RPC connection and executor, omit daily activity/reset-journal work, and do not hold the model's busy state or serial queue. Account changes invalidate pending reads. Existing earned-reset confirmation and retry identity are preserved in the full limits sheet.
- During Codex Chat or Full Mac work, the composer accepts text updates via Return or the separate send arrow beside Stop. Messages submitted during preparation wait for the main model turn. A token binds each dispatch to the original request, conversation and active provider turn; internal skill-selection turns never expose the update channel. Stop prevents further queued sends. Neither model settings nor Mac permission scope changes through this route. Updates are text-only, bounded to 32 messages of 20,000 characters per task; Ollama/Mock can retain a draft during work but do not support live steering.
- Each update and delivery state is saved inside its original user message before sending, preserving the exact user/assistant lineage pair and ordinary backup coverage. Accepted, rejected and uncertain delivery remain distinct. Lost replies are not retried automatically; restored pending messages are not replayed. Confirmed updates join fresh provider-history bootstrapping, and all saved updates remain searchable. Completion preserves a newer draft. A new public user-message boundary clears superseded live output; the updated final answer stands on its own and earlier public answers remain in the work log.

Verification: **2,263 Python tests** plus compileall and **1,233 Native checks** pass; optional pytest is absent/skipped. The final draft/queue adjustments additionally pass **15 focused Native integration checks**. Disposable tests cover exact-turn targeting, duplicate/unknown attempts, late completion, immediate Stop, queue preparation, restart, lineage, search, quota failures/throttling/account changes and independent RPC scheduling. The signed release UI was checked in an isolated profile: both menu destinations, upward layout, live percentages, removed model-menu entry, two accepted updates, an update during a deliberately slow quota read, final output and a preserved draft. Saved immutable conversation bytes were verified after quitting.

Live acceptance used the PM account through **Codex CLI 0.153.4** with short ephemeral, tool-free **GPT-6 Astra** requests. The final check confirmed that `turn/steer` was accepted for the same active turn and that the resulting answer exactly reflected the correction. No file/tool task or earned reset was performed by those live checks. The protocol follows the [official active-turn steering contract](https://learn.chatgpt.com/docs/app-server#steer-an-active-turn). Native **0.55.0 (63)** retains the previous installed bundle for recovery and requires the operator's normal app restart.

## Live Task Input Polish / Native 0.55.1

Delivered 2026-09-06 for the operator's sidebar, quota and composer feedback:

- The sidebar **Меню** opens upwards within its own column. Its width is constrained before content measurement, its height scrolls within the window, and window movement or resizing dismisses it. The menu identifies the connected ChatGPT account and plan and explicitly shows **Использовано** and **Осталось**. Read-only checks found different accounts in Proto-Mind and Codex Desktop; the operator chose to retain Proto-Mind's existing Plus login. The reported percentages already represented usage correctly; account identity and labels now make the distinction visible.
- One composer action replaces the separate Send and Stop buttons: an active task with no text or selected attachment shows **Stop**; entering text or attaching an input shows **Send**. Removing that input restores Stop. Return submits the update, while Escape from the editor can still stop work with an unsent draft present. Model and access settings remain fixed for the active task.
- Selected project text, PNG/JPEG and PDF pages can be previewed and sent to the active Codex turn. Read-only previews use a separate bounded executor so they can run during model work. Delivery checks the original workspace, source hashes, protected paths, existing input bounds and current image capability before the model RPC. Attachment-only updates receive a short default prompt. Receipts store selected metadata, not inline input bytes; uncertain sends and restored pending updates are not automatically retried or reattached.
- Initial inputs move out of the pending composer selection when a task starts. Newly typed text and selected inputs survive completion; stopping or failing an original request does not restore its files into a different new draft. Update history retains the original user/assistant lineage, delivery states and attachment names.

Verification: **2,266 Python tests** plus compileall and **1,247 Native checks** pass; optional pytest is absent/skipped. Disposable integration checks cover live text/image/PDF inputs, exact extracted PDF context, changed-source rejection, duplicate and uncertain delivery, preview concurrency, saved history integrity, restart, draft recovery and narrow/off-origin popup placement. The signed release executable was checked in an isolated profile: the menu and full limits view agree, the popup stays in the sidebar, typing and image selection switch the single button, image-only steering is accepted, and Escape stops work while preserving a draft.

A short ephemeral, tool-free **GPT-6 Astra** turn through the PM account and **Codex CLI 0.153.4** accepted a synthetic text file and blue image through the same active-turn update and returned the exact requested file marker and image color. PDF delivery was checked through the real local PDF extraction/rendering path with a disposable provider fixture, rather than a new live cloud PDF request. No earned reset was consumed and no account was switched. Native **0.55.1 (64)** passes plist and strict signature validation; the previous installed bundle is retained for recovery and the personal app is left for the operator's normal restart.

## Consistent Quota Display / Native 0.55.2

Delivered 2026-09-06 after the operator reported contradictory-looking percentages and a chat jump when opening **Лимиты**.

- The menu, footer and full usage sheet now emphasize **Осталось** and use remaining quota for their bars. Used percentages remain explicitly labelled underneath. The supplied screenshot and a fresh read from the existing Plus account agreed: 2%/3% used meant 98%/97% remaining. The arithmetic and selected account were already correct; the two views had emphasized opposite values.
- Full usage reads join compact quota reads on the independent account queue and use their own Codex connection. Opening or refreshing the sheet no longer toggles chat `busy`, changes the Send/Stop state or triggers transcript scrolling. Reads remain available during model work. Actual earned-reset consumption keeps its existing confirmation, serialization and account-bound retry rules.
- Both views use the same current quota snapshot. New compact readings preserve separately fetched activity and reset-attempt details only for the same account. Older responses cannot roll percentages backwards; failed reads retain the previous reading with an error. Account invalidation rejects pending responses from either read path. Leaving the foreground stops future polling without discarding a completed, valid read for the same account.

Verification: **2,266 Python tests** plus compileall and **1,258 Native checks** pass; optional pytest is absent/skipped. The targeted subset includes **33 Python tests** and **35 Native checks** for independent reads, serialization, errors, account changes, stale responses, preserved drafts and reset details. The signed release UI was checked with disposable data and deliberately delayed quota/activity replies: menu and sheet changed together from 73%/52% remaining to 60%/40%, activity stayed available, and opening/closing the sheet preserved the exact scroll position and draft. Quota reads left the checked disposable dialog files byte-identical. A fixture task continued while the full usage view refreshed.

Native **0.55.2 (65)** passes plist and strict signature validation. Development and testing used a separate source checkout and disposable profile; no personal model task, earned reset, account switch or personal-state migration was performed. The previous installed app is preserved, and the operator's running app is left for a normal restart after their current work finishes.

## Readable Responses and Parallel Conversations / Native 0.56.0

Delivered 2026-09-06 for the operator's response-readability and multitasking feedback.

- Replies use 14.5-point regular text, quieter semibold emphasis, smaller headings and adaptive foreground contrast. Paragraphs have distinct spacing; bullets and numbered lists have hanging indentation, including wrapped and nested items. Quotes, dividers, code copying and existing link handling remain available. Public work commentary uses the same renderer. Rendering does not rewrite saved messages or their copied source text.
- Conversations can run concurrently while the app is open. Sidebar navigation, history destinations and new dialogs remain available during work. Each task has its own ring, stream, draft, attachments, Full Mac grant, Stop action and exact update queue. Background answers and late update receipts save to their original conversations without replacing the selected editor. Active conversations cannot be archived; shared recovery, authentication changes and exit wait for active tasks and pending update delivery.
- `ConversationExecution` owns a reusable bridge per conversation, including session-bound memory/skill workflows. Account/usage and journal metadata use a separate service connection. `AppModel` remains the sole Native history writer. Work sessions share the restore barrier and hold exclusive conversation/run ownership locks. Codex registry changes and session-log appends use cross-process locks; persistent sidecars use exclusive first creation to avoid a reproduced macOS creation race. Existing schemas, cloud consent and Mac permission defaults are unchanged. Parallel tasks do not isolate edits to the same project files.

Verification: **2,272 Python tests** plus compileall and **1,278 Native checks** pass; optional pytest is absent/skipped. The registry race reproduces before the fix and passes **100 repetitions with six concurrent processes** afterwards. Disposable integration checks exercise two real bridge processes, projectless Full Mac grants, queued and late steering, independent cancellation, background completion, history recovery gates, saved lineage, restart, and a pending core action after navigation. The signed release executable was checked with a disposable provider/profile: readable long replies, two sidebar rings, navigation through history during work, Stop affecting only the selected task, and both drafts surviving background completion.

Separate live acceptance used the existing Proto-Mind Plus account and **Codex CLI 0.153.4** for two simultaneous, ephemeral, tool-free **GPT-6 Astra** requests. Both returned their exact independent markers and their execution intervals overlapped by 4.88 seconds. This confirms real provider concurrency; the complete Native steering/permission flow above uses disposable fixtures. No earned reset, account switch or personal-state migration was performed. Native **0.56.0 (66)** passes plist and strict signature validation; the prior bundle is retained and the operator's running app is left for a normal restart after current work finishes.

## Dock and Answer-Detail Polish / Native 0.56.1

Delivered 2026-09-06 for the operator's follow-up visual feedback.

The answer's **Подробнее** menu explicitly uses the adaptive secondary color for its text, symbol and arrow. Its existing actions remain available. The Native Dock icon keeps the isometric cube, silver frame, cyan glyphs and graphite tile, with larger glyphs and simpler edges to improve small-size readability. The 1024-pixel master has genuine transparent outer padding; the built-in imagegen prompts are recorded beside the asset.

Verification: the release executable builds with two compiler jobs. All **5 existing app-icon checks** pass, and all **10 packaged ICNS representations** retain their expected pixel sizes and alpha channels. The 32- and 64-pixel exports were visually inspected. A signed release executable with disposable state confirms the gray menu label/arrow; opening the menu still exposes its four existing actions. Native **0.56.1 (67)** passes plist and strict deep signature validation. The broader 0.56.0 test baseline above was not rerun for this cosmetic patch. The PDF helper is unchanged and reused; personal state and the running personal app are left intact.

## Practical Project Recall / Native 0.57.0

Delivered 2026-09-06 as the next roadmap increment after interface polish.

Automatic project recall and library search share a local content matcher. RU/UK/EN aliases cover the existing technical vocabulary plus ordinary branches, responses, styles, payments and backup phrases. Filenames, paths, dotfiles and identifiers use normalized literal matching; supported service names and local/production/staging qualifiers narrow the candidates. A full path cannot silently match only another directory's basename. A single-word match is omitted when another note covers that same word and more of the question; independent topics remain eligible. Repetition cannot inflate relevance, and tie ordering is deterministic. Source/basis text remains visible but no longer supplies library relevance.

Current-note, correction, archive and exact-folder filters run before ranking. Limits remain three whole automatic notes within 6000 characters and five library results. Library matching counts now include matches beyond the displayed five. Explicit manual attachment still overrides automatic selection; source drift still blocks a reviewed send. This changes selection, not note contents, permissions, shared-core policy or provider history.

The new `local_content_terms_v3` report is requested explicitly by the new Native client. An older running client receives the compatible v2 report/ranking when that option is absent. v1/v2 historical reports remain readable without relabeling or rewriting. No schema migration is needed.

Verification: **2,283 Python tests** plus compileall and **1,288 Native checks** pass; optional pytest is absent/skipped. The full Native check harness uses the release PDF helper; compilation uses two jobs. The unchanged **53-question synthetic corpus** improves from **25/53 to 53/53** exact selections automatically and **21/53 to 53/53** in the library. [Measurement and boundaries](evals/project_recall/README.md) distinguish these development regressions from general semantic or answer-quality claims. Additional tests cover short paths, Unicode, missing files/services/environments, multiple topics, old clients, source drift, corrections and history. Fixture recall remains byte-stable, with model/process/network calls blocked in the corpus regression.

The signed release UI with disposable notes finds only Redis for a Ukrainian port question, distinguishes JSON from YAML, gives no result for an absent TOML file, and previews exactly the same Redis source before Send. No personal account, model turn, note migration or user-app restart was required. Native **0.57.0 (68)** passes plist and strict deep signature validation.


## Long-running Tasks — Native 0.57.1

The operator reported a real Full Mac task interrupted at exactly 15 minutes. New Native Codex tasks now run until provider completion, an operator Stop, a real connection/protocol failure or a durable-evidence failure. The old 900-second Full Mac deadline, 180-second chat deadline and 64-action execution cutoff no longer apply to new tasks. Individual RPC acknowledgements, Computer Use requests and the tool-free skill selector keep their separate bounded waits. Tasks still require the app to remain open; this does not add recovery after app exit, an automatic retry or a guarantee against provider/network interruptions.

Native explicitly requests agent contract v2, with null total time/action limits and an independent 64-item preview bound. Python and Native retain v1 history readers; an older client omitting the new request field retains its exact v1 Full Mac contract until Native restarts. Historical contracts are neither rewritten nor relabeled.

Public evidence keeps recent observations: up to 64 activity previews and 96 work-log entries, with a separate 96 KiB preview budget inside the existing 256 KiB durable record. Full input identities, permissions, contracts and turn lineage are never trimmed to make room. Tool rows referenced by a completion snapshot stay fixed. Truncated journals, artifact lists and file totals are marked partial; retained counts cannot masquerade as complete task statistics. Completed commentary releases its answer buffer, and an accepted correction releases earlier answer text while rejecting late superseded events. Chat-mode context compaction is allowed without granting tools.

The full Native integration check also exposed and fixed a projectless Full Mac mismatch: the logical project remains absent while the grant's starting directory is recorded inside the agent contract. Selected projects still require an exact workspace match; startup directories do not become implicit project-memory scope.

Verification: **2,297 Python tests** plus compileall and **1,293 Native checks** pass; optional pytest is absent/skipped. Accelerated clocks exercise at least twelve hours, silent event periods, completion, Stop and disconnect; these are deterministic simulations, not a twelve-hour live cloud run. Further checks exercise 300 tool actions, 500 public commentaries, correction boundaries, byte-pressure trimming with exact snapshot readback, v1/v2 history, projectless grants and two actual disposable Native bridge processes. The signed **0.57.1 (69)** release bundle passes plist and strict deep signature validation. Release and check compilation use two jobs. No real model turn, personal-state migration or user-app restart was required.
