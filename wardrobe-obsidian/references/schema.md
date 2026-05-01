# Wardrobe Item Schema

Use this schema for purchased items in `30 Personal/Wardrobe/Items/`.

## Required fields

- `item_id`: Stable machine-friendly unique ID. Recommended pattern: `YYYYMMDD-brand-shortname-color-size`.
- `name`: Human-readable product name.
- `brand`: Brand name.
- `category`: Top-level category from taxonomy.
- `subcategory`: Subcategory from taxonomy.
- `color.primary`: Main color.
- `size`: Purchased size.
- `fit`: Fit/silhouette from taxonomy.
- `material`: List of major materials.
- `season`: List from taxonomy.
- `formality`: Formality level from taxonomy.
- `style_tags`: Small normalized list of style tags.
- `features`: Key recognizable features or functions.
- `price`: Numeric purchase price if known.
- `currency`: Currency code. Default `TWD`.
- `purchased_on`: ISO date when bought if known.
- `merchant`: Store or platform.
- `source_url`: Original user-shared product URL.
- `canonical_url`: Cleaned canonical product URL if known.
- `cover_image`: Local main image path.
- `gallery`: Local supporting image paths.
- `status`: `active`, `wishlist`, or `archived`.
- `wear_count`: Integer count, default `0`.
- `summary`: One short AI-friendly description for recognition and styling.
- `dedupe_key`: Conservative dedupe key, usually based on brand + product + color + size.

## Optional fields

- `color.secondary`: Additional colors.
- `pattern`: Pattern such as `solid`, `stripe`, `check`, `graphic`.
- `sku`: Product or variant SKU if available.
- `source_images`: Original remote image URLs.
- `last_worn`: ISO date or null.
- `care_notes`: Washing/care cautions.
- `layering`: Layering notes such as `good over tee`, `works under blazer`.
- `temperature_range`: Optional subjective comfort note.
- `climate_notes`: Optional note about local-weather suitability such as `too hot for Taiwan peak summer`.
- `styling_risk`: Optional note about proportion or vibe failure modes such as `can shorten legs if mismatched`.
- `confidence`: Optional note if some fields are inferred rather than explicit.

## Body sections

After frontmatter, keep these sections in order when possible:

1. `# 商品名稱`
2. Cover image embed
3. `## 核心辨識`
4. `## 穿搭用途`
5. `## 可搭配單品`
6. `## 注意事項`
7. `## 原始商品描述`
8. `## 圖片`
9. `## 更新紀錄`

## Source priority

1. Explicit user facts
2. Product page facts
3. Model inference

Never let lower-priority sources overwrite higher-priority sources.
