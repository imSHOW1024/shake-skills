# Wardrobe Workflows

## 1. Purchased item intake

Trigger examples:
- User sends a shopping link and says they bought it.
- User sends a product link plus color/size.
- User asks to save a new clothing item into the wardrobe.

Steps:
1. Confirm whether the item is purchased or wishlist if ambiguous.
2. Extract user facts: color, size, price, any subjective notes.
3. Fetch product-page facts if useful.
   - If the original purchase page is unavailable, use a secondary reference page, screenshots, or user descriptions instead of blocking intake.
4. Normalize category, subcategory, fit, season, formality, and style tags.
5. Compute `item_id` and `dedupe_key`.
6. Save local image assets.
7. Create or update the note.
8. Add a short summary emphasizing recognition and outfit utility.

## 2. Wishlist intake

Use the same structure as purchased intake but:
- save under `Wishlist/`
- set `status: wishlist`
- avoid mixing wishlist with active wardrobe counts

## 3. Dedupe / update decision

Update an existing note when:
- same canonical URL and same purchased variant
- same SKU plus same color/size

Keep separate notes when:
- same product page but different purchased color/size
- uncertainty remains after comparing title, images, and variant facts

## 4. Outfit recommendation

Trigger examples:
- What should I wear tomorrow?
- Give me a smart-casual outfit from what I already own.
- I want a clean, mature look for dinner.

Steps:
1. Filter `Items/` by category, season, formality, and style.
2. Prioritize complete records with cover images and clear summaries.
3. Recommend specific combinations, not generic categories only.
4. Explain why the outfit works.
5. Mention wardrobe gaps only when useful.

## 5. Forgotten-item recall

When the user wants to rediscover underused items:
- surface low `wear_count` notes
- group by category or season
- highlight flexible items that pair with many existing pieces
