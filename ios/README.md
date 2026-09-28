# PM Remote for iPhone

Native iOS 17+ companion to the **running Proto-Mind Mac app**. It shares PM's
existing conversations and per-conversation execution; it does not run another
model backend on the phone. An iPad layout is included in the same target.

## First version

- Projects and explicitly shared chats, current model/account/access labels.
- Saved messages, earlier-message pages, current streamed answer and task state.
- Send a new task or update a running Codex/Claude task; stop its exact turn.
- Create a chat using the selected chat's project/model/account. Full Mac and API
  tool permission are **not** inherited. Enable those separately on the Mac.
- Phone drafts and pending command IDs survive an app restart. Mac drafts and
  navigation are preserved. Closing the phone client does not stop accepted work.
- Russian/English follows the iPhone language; Dynamic Type and light/dark system
  appearance are supported.

Attachments, provider/account switching, structured question buttons, push
notifications, background polling and voice are not part of this version. Files
remain on the Mac. The phone shows response completion, not verified task success.
The transcript is text only; long messages/live output and task-update previews
are bounded. No provider credentials or raw tool logs are transferred.

## Build and install

Open `ProtoMindRemote.xcodeproj` in full Xcode with its iOS platform installed.
Choose your **Personal Team** in Signing & Capabilities and pair your iPhone in
Xcode Device Hub. iOS 27+ supports first pairing over Wi-Fi; on earlier iOS versions,
connect and unlock the phone with a data cable for the first pairing. Enable
Developer Mode if iOS requests it, select the phone, and Run. After pairing, Xcode
can install over the same Wi-Fi network. An iPhone XS Max on iOS 18 is supported
by this app, but still needs that initial cable connection.
The bundle ID is `com.virencore.ProtoMindRemote`; change it to a unique ID if your
team needs one. No paid Apple membership is needed for testing on your own device.
Free provisioning is time-limited (Apple currently specifies seven days); rerun
from Xcode to renew it. This is not an App Store/TestFlight distribution.

For an unsigned simulator build:

```sh
bash scripts/build_ios.sh
```

The script requires the full Xcode/iOS SDK and never changes `xcode-select`.
The generated project is checked in. If target/source configuration changes,
install XcodeGen with Homebrew and run `xcodegen generate --spec ios/project.yml`.
Do not commit a personal team, signing credentials or `xcuserdata`.

## Private connection, including away from home

1. Install [Tailscale](https://tailscale.com/download) on the Mac and iPhone and
   connect them to the same private tailnet. Personal use has a free plan. Do not
   enable Funnel or make a public tunnel for this listener.
2. On the Mac, run `tailscale serve --bg 8765`. Follow Tailscale's HTTPS setup and
   copy the resulting `https://your-mac.your-tailnet.ts.net` address. If using the
   standalone Mac app without its CLI integration, its executable is
   `/Applications/Tailscale.app/Contents/MacOS/Tailscale`.
3. In PM: **Settings → Connections → iPhone · PM Remote**. Save that HTTPS address
   and enable **Accept commands from PM Remote**. Choose **Shared chats**.
4. Create a pairing QR code. In PM Remote, scan it (or paste the pairing link).
   Return to the Mac and approve the requesting iPhone by name.
5. Keep the Mac awake, PM open and Tailscale connected. PM remote access starts
   **off after every PM restart**, even if Tailscale Serve is still configured.

The listener binds only to `127.0.0.1:8765`. TLS is terminated by the operator's
private Tailscale Serve endpoint. Configure tailnet ACLs for your own devices if
other people use that tailnet. Pairing also requires its one-time secret and a
separate local approval. HTTPS certificates are validated normally; redirects,
cookies, credential stores and browser-origin requests are not used.

To disable the route, stop the connection in PM and run
`tailscale serve --https=443 off` for the dedicated Serve configuration. If you
already use Serve for another service, configure a separate endpoint rather than
overwriting its existing route. This project never runs Serve/Funnel commands or
changes the user's VPN automatically.

## Authority, storage and failure behavior

Each phone generates a random 256-bit bearer token stored only in its device-bound
Keychain item. The Mac keeps its SHA-256 digest, a device name and ID. Pairing links
expire after ten minutes, use a URL fragment and are consumed before approval.
Never publish them. Removing a phone or unsharing a chat immediately revokes
future access, while already accepted tasks continue. A phone can use the existing
permissions of a shared chat, including Full Mac: share those chats intentionally.

Connection metadata/receipts live outside PM's restored data in
`<Native-profile-parent>/ProtoMindConnections/<profile-hash>/mobile/`, protected
by a persistent exclusive lock and compare-before-write. They contain no token,
prompt or draft text. Private restore generation changes invalidate all devices
and the chat allowlist. Phone drafts/pending text use protected local Application
Support storage excluded from backups; transcripts are kept in memory only.

Before a command can reach a task, the phone saves its exact ID and the Mac
durably reserves it. A repeated ID with identical input returns its receipt;
different input conflicts. Interrupted reservations become `unknown`. Commands
older than ten minutes cannot execute anew; receipts are retained for a day.
Stop and live updates bind to the displayed run ID. There is no automatic retry
of a mutation after a timeout, reconnect, reload or app restart. The client only
queries its receipt; unresolved delivery requires checking the conversation.

## Verification

`bash scripts/test_native.sh --mobile-only` exercises the real loopback HTTP
listener, pairing/approval, allowlist, two parallel fixture tasks, steering, exact
stop, history persistence, revocation, restore invalidation, HTTP framing and
client lost-reply/restart reconciliation. The exact `ios/Shared` client code is
compiled by that test on macOS. It uses disposable profiles and fake provider
transports, with no paid model calls.

This does not replace the iOS SDK build, simulator/UI check, Keychain/camera check
on a phone, or a real Tailscale link over cellular. Record those separately in the
release notes; never infer them from the portable protocol tests.

References: [Apple account capabilities](https://developer.apple.com/help/account/basics/about-your-developer-account),
[Apple device pairing](https://developer.apple.com/documentation/xcode/pairing-your-devices-with-your-mac),
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve),
[Tailscale personal plan](https://tailscale.com/pricing).
