# The Forest UCM — safe PS4 browser proof

**This is a standalone web page, NOT a mod injected into The Forest.** No PKG is rebuilt or installed. No PRX, debugger, hooks, memory patches or game data are accessed.

## Purpose

Test the UCM graphical layout on a real PS4 screen with the console's Internet Browser. Mirror all **10 categories / 13 entries** in the current C UI core; all gameplay actions stay **locked**. The only active commands are showing/hiding the keyboard guide and closing/reopening the demo.

**Proof scope:** GUI appearance, clickable items and browser-provided basic controller navigation. It does **not** validate in-game rendering, PS4 AOT class registration, direct gamepad button reads, L1+R1, or any game-changing action.

## Real PS4 browser input limitation

Sony's official [Web Content Guidelines for PlayStation 4 (v12.00)](https://www.sie.com/content/dam/corporate/jp/guideline/PS4_Web_Content-Guidelines_e.pdf), section **3: Input Operation Events**, states:
- The DualShock 4 can control a cursor with the left stick and activate buttons with the browser's Enter action (Cross or Circle depending on region).
- The D-pad can jump between clickable elements and emits generic keyboard events.
- Web pages **cannot access individual DS4 buttons or its touchpad**. The document also lists the Gamepad feature as unsupported.

Thus this prototype uses **HTML buttons, click and arrow keyboard events**, not Gamepad API or raw hardware masks. If D-pad behavior differs, use the browser's on-screen cursor. The actual in-game Unity/Rewired DS4 input adapter is a separate project component.

## Try with Mac and PS4 on the same LAN

1. Download the safe browser demo ZIP from the conversation, unzip it onto the Mac.
2. Double-click `start-mac.command`; if Gatekeeper asks, right-click > Open. **Do not disable Gatekeeper**.
3. The Terminal window prints a URL such as `http://192.168.1.25:8765/index.html`; enter the **actual** displayed address in the PS4 Internet Browser.
4. Test D-pad focus/click, category navigation, blocked game actions, close/open.
5. Stop the local server with `Ctrl+C`. The small Python HTTP server listens on your LAN; keep the demo in a dedicated directory with no private files.

The script prefers `python3 -m http.server` and falls back to `/usr/bin/python -m SimpleHTTPServer` for Catalina systems that retain Python 2. The URL example is illustrative; no user's IP is baked in.

## Offline tests

```sh
node tests/js/test_ps4_browser_demo.js
```

This exercises the ES5 menu model and alignment with `src/overlay.c`. Additionally the browser GUI has been run manually in a local headless Chromium test at 1280×720, 1540×754, 1920×1080, and 740×900. **None of those desktop tests constitute PS4-browser hardware verification.**

The original AOT Unity/PS4 injection problem remains unsolved. Do not present this browser-only UI as an in-game overlay, console-native homebrew or a substitute for the project's target.
