
**Task: Build a TikTok-style video learning app (prototype)**

**Stack:** Vite + React + TypeScript + Tailwind CSS + PWA

**What it does:**
A vertical swipe video feed (like TikTok) that plays short French-learning videos with bilingual subtitles (French/Chinese). Users can swipe through videos, toggle subtitle languages, and view translated comments.

**Core components to build:**
- **VideoFeed** — full-screen vertical scroll with CSS scroll-snap, autoplay on visible (IntersectionObserver), pause on scroll away
- **VideoPlayer** — native `<video>` with `<track>` for VTT subtitles, subtitle language toggle (FR / ZH / both)
- **CommentsPanel** — slide-up drawer showing comments with FR/ZH toggle, sorted by likes
- **ChannelBar** — author info + stats overlay on each video

**Data source:** FastAPI backend serving video metadata, comments, and static files (mp4, vtt). All endpoints under `/api/videos`.

**PWA:** Add `manifest.json` + basic service worker so it can be installed as a full-screen app on mobile.

**Design target:** Full-screen on mobile, centered card on desktop. Responsive.

**Priority:** Get the swipe feed + video playback + subtitles working first. Comments panel second.
