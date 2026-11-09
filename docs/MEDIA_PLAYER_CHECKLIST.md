# Elder media player: manual checklist (phone Chrome over the https tunnel)

Run after any change to `web/src/elder/MediaScreen.tsx` / `ytPlayer.ts`. Dev only: open `/?debug=yt` to see each embed's
`onReady` / `onError(code)` / `onStateChange` and the exact iframe src (the page is not in production builds).
Error codes: 2 bad id, 5 HTML5 player error, 100 removed/private, 101/150 embedding blocked, 153 missing referrer/origin.

Test on: (1) laptop Chrome via `http://localhost:5173`, (2) phone Chrome via the `https://....trycloudflare.com` / `.ts.net`
URL, (3) an Android WebView if you have one (the family app / an in-app browser).

| # | Do | Expect |
|---|---|---|
| 1 | Say "भजन लाव" (a normal video) | The video area loads, a big **सुरू करा** button shows, the video does NOT start by itself |
| 2 | Tap **सुरू करा** | Video plays with sound; the button goes away |
| 3 | Tap the pause/play button twice | Pauses, then resumes |
| 4 | **कमी** x2, **जास्त** x2 | Volume steps down and up; never muted |
| 5 | Open a playlist (a family playlist link) and tap **पुढचा** | Next song plays |
| 6 | **बंद करा** | Back to the home screen; Arjun listens again |
| 7 | Say "बातम्या लाव" with a family news channel | Plays the channel's newest upload (not a live stream) |
| 8 | Open a video whose embedding is blocked (the "Despacito" id in the debug page) | "हा व्हिडिओ इथे चालत नाही, दुसरा लावतो"; the next search result loads; after 3 failures a big **YouTube मध्ये उघडा** button |
| 9 | Tap **YouTube मध्ये उघडा** on Android | Opens the YouTube app (or the page) on that video |
| 10 | Turn the elder language to Hindi / English in Settings | Buttons read बंद करें / शुरू करें / अगला / कम / ज़्यादा, resp. Close / Start / Next / Lower / Louder |
| 11 | Open DevTools > Network on the tunnel page | Requests to `youtube-nocookie.com/embed/...`; response headers of the page carry `Referrer-Policy: strict-origin-when-cross-origin` |

Never expected: a dark box with nothing to tap, or a video that starts before a tap.
