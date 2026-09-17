# Proto-Mind for macOS — beta

Requires an **Apple Silicon Mac (M1 or newer), macOS 14 or newer**. Intel Macs
are not supported by this package. The main workflow is available in English and Russian. Choose a language in
the welcome screen or Settings → Appearance; the interface updates immediately.
Technical core reports may still contain Russian.

## Install and connect

1. Open the DMG and drag **Proto-Mind.app** to **Applications**. Eject the DMG,
   then launch Proto-Mind from Applications.
2. Follow the welcome screen. Sign into your **own ChatGPT account with Codex
   access** in the browser, then return to Proto-Mind. Available models and
   limits depend on that account. No API key is needed for text tasks.
3. Enable cloud processing when you are ready to send messages to OpenAI.
   This consent is separate from signing in. You can skip setup and reopen it
   from Menu → Settings → Models → first connection help.

Python and Codex are included. Homebrew, Node, Xcode and the source repository
are not needed to run the app. Developer tools needed by your own projects
are still separate installations.

**This build is locally signed for beta testing, without Apple notarization.**
macOS may block a downloaded copy because the developer cannot be verified.
If you trust this beta, first try opening the copied app, then go to
**System Settings → Privacy & Security → Open Anyway** for Proto-Mind and confirm
the system prompt yourself. This makes an exception for this app only; do not
disable Gatekeeper or other system protections. If macOS reports malware or a
damaged app, stop instead of overriding that warning.

See [Apple's instructions](https://support.apple.com/en-us/102445). A Developer
ID-signed and notarized release is a separate distribution step. This beta has
been checked locally with a disposable profile; a second-Mac trial is still
pending.

## Browser material and results

Open a page in a panel, optionally select a passage, then choose **Use in a task**.
Review the captured text and destination, add it to a draft and send. The source
link and bounded text snapshot are saved in the message. Forms, images and
embedded frames are excluded; no page is continuously shared. The same explicit
workflow is available by voice. A completed response can be opened beside chat.

The DMG includes `DemoProject`, a fictional brief and a walkthrough. It contains
no account, API key or pre-generated answer.

## Optional features

- **Voice:** Menu → Settings → Voice. Connect your own OpenAI API key; API
  usage is billed separately from ChatGPT. macOS asks for microphone permission
  when voice is first enabled. Opening setup does not activate the microphone.
- **Mac access:** use the access selector in the composer. Chat-only is the
  default. Full access allows operations on this Mac, including outside a
  selected project, and can be remembered when you explicitly choose it.
- **Screen control:** additionally needs the signed Computer Use helper from
  Codex Desktop and its macOS permissions. It is not redistributed in this app.
  Without it, permitted file/command work can still run; screen control cannot.
- **GitHub:** connect your own account in Settings → Connections. GitHub CLI
  (`gh`) is currently a separate prerequisite; follow the connection screen.
- **Local models:** install and run Ollama separately, then select it in
  Settings → Models. Cloud processing permission is not needed for Ollama.

## Your data and updates

The portable app keeps its profile in
`~/Library/Application Support/ProtoMind/`:

- `native/`: dialog history, preferences, project memory, private Codex profile;
- `core/`: cognitive memory and core-owned logs/exports.

The application bundle contains code and runtimes, never the maker's dialogs,
memory, login or API key. Replacing the app in Applications leaves your profile
in place. Quit it after running tasks finish before replacing it. There is no
automatic updater in this beta.

Use Settings → Data and backups to create a private backup before an update.
Recovery currently requires the same profile paths; automatic migration to a
different macOS user or Mac is not implemented. These backups exclude service
credentials, provider history, source attachments and files in your working
projects. Deleting the app alone does not delete your profile.

The development edition **Proto-Mind Native.app** uses its existing, separate
`ProtoMindNative` profile and repository-owned core memory. This beta does not
silently import or modify that profile. An explicit migration can be prepared
later if you want to move from the development edition.
