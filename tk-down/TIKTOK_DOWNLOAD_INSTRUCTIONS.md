# TikTok Download Instructions

Use this document when another project needs to recreate the TikTok download flow implemented in this repo.

## Goal

Given a TikTok URL:

- resolve short or mobile TikTok links to a canonical post URL
- extract the TikTok post ID
- skip work if that post was already downloaded locally
- download the non-HD `Without watermark` video from `ssstik.io`
- save the file into `~/Public/Tiktok`
- name the file from a short title plus the TikTok post ID suffix

## Current Behavior

The existing implementation lives in [`bin/yt-down.mjs`](/Users/brett-m1/Documents/GitHub/yt-down/bin/yt-down.mjs).

The TikTok flow prefers browser automation first and falls back to an HTTP-only SSSTik flow if browser automation fails.

## Inputs And Outputs

Input:

- a TikTok URL such as `https://www.tiktok.com/@user/video/1234567890`
- short links such as `vm.tiktok.com` and `vt.tiktok.com` are supported

Output:

- a local file path on success
- target directory: `~/Public/Tiktok`
- filename shape: `<normalized_title>_<post_id>.mp4`

Example:

```text
~/Public/Tiktok/funny_cat_reaction_6718335390845095173.mp4
```

## Required Dependencies

- Node.js
- `curl`
- `openclaw`
- optional local MLX title generation:
  - `mlx_lm.generate`, or
  - `python3 -m mlx_lm.generate`, or
  - `./.venv/bin/mlx_lm.generate`

## Platform Detection

Treat the URL as TikTok when the hostname ends with one of:

- `tiktok.com`
- `vm.tiktok.com`

The current implementation also accepts other TikTok hostnames that still end with `tiktok.com`, including mobile and short-link variants after resolution.

## Step 1: Resolve The TikTok URL

Before extracting the post ID, resolve redirects for these hosts:

- `vm.tiktok.com`
- `vt.tiktok.com`
- `www.tiktok.com`
- `m.tiktok.com`

The current implementation uses:

```bash
curl -sS -L -o /dev/null -w '%{url_effective}' -A '<browser user agent>' '<input-url>'
```

Use the final effective URL if one is returned.

## Step 2: Extract The Post ID

Extract the numeric TikTok post ID from one of these path formats:

- `/@user/video/<id>`
- `/v/<id>`
- `/video/<id>`

Fail fast if no numeric ID can be extracted.

## Step 3: Duplicate Detection

Before downloading, scan `~/Public/Tiktok` for an existing filename that already ends with the same post ID.

The current implementation treats any existing file matching the post ID suffix as a hit and returns that path immediately instead of downloading again.

## Step 4: Preferred Browser Automation Flow

OpenClaw is the primary path.

### Browser setup

1. Start the OpenClaw browser session.
2. Close any existing tabs.
3. Open `https://ssstik.io/`.
4. Wait for `domcontentloaded`.

### Form interaction

Fill the TikTok input using this selector:

- `#main_page_text`

Submit the form using this selector:

- `#_gcaptcha_pt`

The current code uses `form.requestSubmit()`.

### Wait for result

Poll until the page exposes:

- description from `p.maintext`
- author from `#avatarAndTextUsual h2` or `.result_overlay h2`
- a usable download link from `a.download_link`

Pick only the non-HD `Without watermark` link:

- text must equal `Without watermark`
- class must include `without_watermark`
- class must not include `quality-best`
- class must not include `without_watermark_hd`

### Download capture

When the result is ready:

1. Snapshot the current contents of `~/Downloads`.
2. Click the selected `Without watermark` link in the browser.
3. Wait for a new download to appear in `~/Downloads`.
4. Treat `.crdownload` as an in-progress partial.
5. Treat `mp4`, `mp3`, `m4a`, or `webm` as completed downloads.
6. Wait until the downloaded file size is stable.
7. Copy the finished file to `~/Public/Tiktok/<final-name>`.
8. Delete the temporary file from `~/Downloads`.
9. Close extra tabs and the working tab.

## Step 5: HTTP Fallback Flow

If browser automation fails, fall back to direct SSSTik HTTP calls.

### Homepage config scrape

Fetch `https://ssstik.io/` and extract:

- `s_n` as the host
- `s_furl` as the form path
- `s_tt` as the token

### Result request

POST to:

```text
https://<host>/<formPath>?url=dl
```

Send:

- header `HX-Request: true`
- header `HX-Current-URL: https://ssstik.io/`
- header `HX-Target: target`
- form field `id=<original tiktok url>`
- form field `locale=en`
- form field `tt=<token>`

### Result parsing

Parse the returned HTML for:

- description from `<p class="maintext">...`
- author from `<h2>...`
- the non-HD `Without watermark` download link

Use the same non-HD filtering rules as the browser flow.

### File download

Download the selected file with `curl`, preserving a browser-like user agent and `Referer: https://ssstik.io/`.

The current implementation uses retry flags and fails if the resulting file is empty.

## Step 6: Filename Generation

The output filename is:

```text
<normalized_title>_<post_id>.<extension>
```

### Title source order

1. MLX-generated short summary from the TikTok description
2. raw TikTok description
3. TikTok author
4. fallback literal `tiktok_video`

### MLX summary prompt

The current implementation asks for:

- summary only
- no explanation
- maximum 6 words

Then it cleans the output and keeps a short usable title.

If MLX is missing or fails, fall back to a cleaned version of the description.

### Normalization rules

- remove invalid filename characters
- collapse whitespace
- keep the content ID suffix
- default extension to `.mp4` if none is obvious

## Error Handling

Recommended behavior:

- invalid URL: fail immediately
- missing TikTok ID: fail immediately
- existing local file: return it without downloading
- browser automation failure: try HTTP fallback
- missing SSSTik result link: fail with a clear error
- empty downloaded file: fail with a clear error

## Rebuild Checklist

If you recreate this in another project, preserve these behaviors:

- canonicalize TikTok URLs before ID extraction
- use post-ID duplicate detection, not title-based duplicate detection
- prefer the non-HD `Without watermark` SSSTik result
- support browser-first plus HTTP fallback
- save into `~/Public/Tiktok`
- append the TikTok post ID to the final filename
- keep title generation optional so downloads still work without MLX

## Reference

Relevant implementation areas:

- [`bin/yt-down.mjs`](/Users/brett-m1/Documents/GitHub/yt-down/bin/yt-down.mjs)
- [`README.md`](/Users/brett-m1/Documents/GitHub/yt-down/README.md)
