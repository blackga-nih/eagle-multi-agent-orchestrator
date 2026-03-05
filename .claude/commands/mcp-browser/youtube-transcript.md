---
description: Extract YouTube video transcript and description via browser automation
argument-hint: <video-id-or-url> [output-dir]
---

# YouTube Transcript Extractor

Extract a YouTube video's full transcript and description using your real Chrome browser (already signed into YouTube). This bypasses API rate limits, bot detection, and cookie locks.

## Variables

| Variable | Value | Description |
|----------|-------|-------------|
| SKILL | `claude-bowser` | Uses your real Chrome (signed into YouTube) |
| MODE | `headed` | Visible browser for debugging |
| VIDEO_ID | $1 | YouTube video ID or full URL |
| OUTPUT_DIR | $2 or `.claude/context/tac-scan` | Where to save transcript |

Parse VIDEO_ID from $1:
- If starts with `http` → extract ID from `v=` param
- Otherwise → use as-is

## Workflow

### Phase 1: Navigate and Expand

1. Navigate to `https://www.youtube.com/watch?v={VIDEO_ID}`
2. Wait for page to load (look for the video title heading)
3. If a cookie consent dialog appears, accept it
4. If "Sign in to confirm you're not a bot" appears, wait — the page still renders metadata below it
5. Find and click the "...more" button to expand the full description
6. Wait for description to fully expand

### Phase 2: Extract Description

7. Extract the full description text including:
   - All plain text content
   - All URLs/links (especially GitHub repo links)
   - Hashtags
8. Save description to: `{OUTPUT_DIR}/{VIDEO_ID}_description.txt`

### Phase 3: Open Transcript Panel

9. Look for the "Show transcript" button in the description area and click it
10. Wait for the transcript panel to open (look for "Transcript" heading)
11. If transcript panel doesn't appear within 5 seconds, note this and skip to Phase 5

### Phase 4: Extract Transcript

12. Use `run-code` to extract all transcript segments from the panel:

```javascript
// Extract transcript segments
const segments = document.querySelectorAll('ytd-transcript-segment-renderer');
if (segments.length === 0) {
  // Try alternative selectors for newer YouTube layouts
  const panel = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]');
  if (panel) {
    const items = panel.querySelectorAll('[class*="segment"]');
    return Array.from(items).map(el => el.textContent.trim()).join('\n');
  }
  return 'NO_SEGMENTS_FOUND';
}
return Array.from(segments).map(seg => {
  const timestamp = seg.querySelector('.segment-timestamp')?.textContent?.trim() || '';
  const text = seg.querySelector('.segment-text')?.textContent?.trim() || seg.textContent?.trim() || '';
  return timestamp ? `[${timestamp}] ${text}` : text;
}).join('\n');
```

13. If segments found, scroll down in the transcript panel to load all segments (YouTube lazy-loads them):

```javascript
// Scroll transcript panel to load all segments
const panel = document.querySelector('#segments-container') ||
              document.querySelector('ytd-transcript-segment-list-renderer');
if (panel) {
  const scrollParent = panel.closest('[style*="overflow"]') || panel.parentElement;
  let lastCount = 0;
  const scroll = () => {
    scrollParent.scrollTop = scrollParent.scrollHeight;
    const currentCount = document.querySelectorAll('ytd-transcript-segment-renderer').length;
    if (currentCount > lastCount) {
      lastCount = currentCount;
      setTimeout(scroll, 500);
    }
  };
  scroll();
}
```

14. After scrolling completes, re-extract all segments
15. Save full transcript to: `{OUTPUT_DIR}/{VIDEO_ID}_transcript.txt`

### Phase 5: Extract Metadata

16. Extract video metadata:
    - Title (from heading)
    - Channel name
    - View count
    - Upload date
    - Like count (if visible)

17. Save metadata to: `{OUTPUT_DIR}/{VIDEO_ID}_metadata.json`

```json
{
  "video_id": "{VIDEO_ID}",
  "title": "{TITLE}",
  "channel": "{CHANNEL}",
  "views": "{VIEWS}",
  "date": "{DATE}",
  "likes": "{LIKES}",
  "description_file": "{VIDEO_ID}_description.txt",
  "transcript_file": "{VIDEO_ID}_transcript.txt",
  "transcript_available": true|false,
  "github_links": ["{URL1}", "{URL2}"]
}
```

### Phase 6: Report

18. Report results:
    - Video title and channel
    - Transcript: N segments extracted (or "not available — description used as fallback")
    - Description: N characters, N GitHub links found
    - Files saved to OUTPUT_DIR
