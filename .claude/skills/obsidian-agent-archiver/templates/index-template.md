---
type: index
category: {{category}}
banner: "[[_assets/banners/{{category}}-banner.png]]"
cssclasses: [cards, cards-cover, cards-2-3]
human_reviewed: false
tac_original: false
---

![[{{category}}-banner.png|banner]]

# {{Category}} Index

> All {{Category}}s in the knowledge base.

## Gallery View

```dataview
TABLE WITHOUT ID
  link(file.link, name) as "Name",
  status as "Status",
  file.mday as "Modified"
FROM "AI-Agent-KB/{{folder}}"
WHERE type = "{{type}}"
SORT file.mday DESC
```

---

[[_Dashboard|<- Back to Dashboard]]
