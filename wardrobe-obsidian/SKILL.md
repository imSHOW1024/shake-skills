---
name: wardrobe-obsidian
description: "Manage a personal wardrobe in Obsidian using one-note-per-item Markdown records with local images, structured frontmatter, and shopping-link intake. Use when the user wants to: (1) save purchased clothing, shoes, or accessories from e-commerce links into an Obsidian wardrobe database, (2) enrich items with color, size, price, material, style metadata, images, and AI-friendly summaries, (3) search or review what is already in the closet, (4) generate outfit ideas from existing items, or (5) avoid duplicate purchases by comparing against the current wardrobe."
---

# Wardrobe Obsidian

Keep the wardrobe as plain Markdown in Obsidian. Treat `Items/` as the source of truth, store at least one local image per item, and prefer stable taxonomy over free-form improvisation.

## Read these references when needed

- Read `references/schema.md` before creating or updating wardrobe item notes.
- Read `references/taxonomy.md` when normalizing category, fit, season, formality, or style tags.
- Read `references/workflows.md` when deciding between intake, wishlist, lookup, and outfit recommendation flows.
- Read `references/image-policy.md` when saving product images or deciding local-vs-remote image handling.

## Core rules

- Treat a shopping link plus user message as the purchase truth signal unless the user says it is only a wishlist item.
- User-provided facts override site data. Site data overrides model inference. Model inference only fills gaps.
- Store each purchased item as one Markdown note under `30 Personal/Wardrobe/Items/`.
- Use a human-friendly filename: `品牌 - 商品名 - 顏色 - 尺寸.md`.
- Use a stable `item_id` for assets, dedupe, and future updates.
- Store at least one local cover image; do not rely on remote URLs alone.
- If the original retailer page is gone, still create the item from user facts plus any secondary reference page or screenshots.
- Prefer conservative dedupe. If uncertain whether two items are the same, keep both and flag the ambiguity in notes.

## Workflow selection

### 1. Intake purchased item

Use this when the user sends a shopping/product link with color, size, price, notes, or a statement that they bought it.

1. Gather explicit user facts first.
2. Fetch product-page data if useful.
3. Normalize metadata using the taxonomy.
4. Save local image assets.
5. Create or update the item note from the schema/template.
6. Add a short AI-friendly summary focused on styling and recognition.

### 2. Save wishlist item

Use this when the user shares a product link but has not bought it yet.

- Save the note under `30 Personal/Wardrobe/Wishlist/`.
- Set `status: wishlist`.
- Keep the same taxonomy and image rules where practical.

### 3. Wardrobe lookup / review

Use this when the user asks what they own, wants category/style filtering, or needs help recalling forgotten items.

- Search the wardrobe notes first.
- Prefer concise grouped answers: by category, color, formality, season, or style.
- Call out uncertainty if notes are incomplete.

### 4. Outfit recommendation

Use this when the user asks what to wear for a context such as work, weather, date, trip, or vibe.

- Base recommendations on existing `Items/` notes first.
- Optimize for occasion, weather, formality, and style coherence.
- Mention specific item notes when possible.
- If wardrobe gaps are obvious, say so instead of forcing a weak outfit.

## Vault conventions

Primary paths:
- `30 Personal/Wardrobe/Items/`
- `30 Personal/Wardrobe/Looks/`
- `30 Personal/Wardrobe/Wishlist/`
- `30 Personal/Wardrobe/_templates/`
- `30 Personal/Wardrobe/_indexes/`
- `30 Personal/Wardrobe/_assets/items/<item_id>/`
- `30 Personal/Wardrobe/_assets/looks/<look_id>/`

Installed starter files:
- `30 Personal/Wardrobe/_templates/Wardrobe Item Template.md`
- `30 Personal/Wardrobe/_templates/Wardrobe Look Template.md`
- `30 Personal/Wardrobe/_indexes/Wardrobe Dashboard.md`

## Notes for future automation

If browser automation is available, use it to collect product title, brand, price, material, description, canonical URL, candidate images, and variant options. Do not let browser extraction override explicit user facts about the purchased variant.
