# Image Policy

Store product images locally for long-term wardrobe recall.

## Rules

- Save at least 1 local cover image per item.
- Prefer 1 cover + up to 2 detail images for v1.
- Keep remote image URLs in `source_images` only as references.
- Use `item_id` directories so note renames do not break asset organization.
- If the user later provides real-life try-on photos, save them in the same `item_id` directory and mention them in the note body.

## Paths

- Item images: `30 Personal/Wardrobe/_assets/items/<item_id>/`
- Look images: `30 Personal/Wardrobe/_assets/looks/<look_id>/`

## Cover image selection

Choose the most recognizable clean product image as `cover_image`.
Prefer front-facing full-item images over collages, model close-ups, or banner composites.

## When image handling is partial

If you cannot save images yet:
- still create the note
- keep `source_images`
- mark in the note that local image download is pending

Do not block wardrobe intake solely because image saving failed.
