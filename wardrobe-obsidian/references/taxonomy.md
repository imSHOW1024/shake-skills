# Wardrobe Taxonomy v1

Keep tags normalized. Prefer this controlled vocabulary over ad-hoc synonyms.

## category

- `top`
- `outer`
- `bottom`
- `shoes`
- `bag`
- `accessory`
- `set`

## subcategory

### top
- `tshirt`
- `shirt`
- `polo`
- `knit`
- `hoodie`
- `sweatshirt`

### outer
- `blazer`
- `jacket`
- `coat`
- `cardigan`
- `windbreaker`
- `vest`

### bottom
- `trousers`
- `jeans`
- `chinos`
- `shorts`

### shoes
- `sneakers`
- `loafers`
- `boots`
- `derby`
- `sandals`

### bag
- `backpack`
- `tote`
- `crossbody`
- `briefcase`

### accessory
- `cap`
- `belt`
- `watch`
- `scarf`
- `socks`
- `glasses`

## fit

- `slim`
- `regular`
- `relaxed`
- `oversized`
- `straight`
- `tapered`
- `wide`

## formality

- `casual`
- `smart-casual`
- `business-casual`
- `formal`

## season

- `spring`
- `summer`
- `autumn`
- `winter`
- `all-season`

## style_tags

- `minimal`
- `clean`
- `japanese`
- `smart`
- `classic`
- `street`
- `functional`
- `mature`
- `relaxed`

## pattern

- `solid`
- `stripe`
- `check`
- `graphic`
- `denim`
- `texture`

## Normalization hints

- Map plain-language Chinese labels into the normalized English key values above.
- Keep the controlled vocabulary small. If a new term is truly needed, add it deliberately instead of improvising per note.
- It is okay for `features` to stay more descriptive and less constrained than taxonomy fields.
