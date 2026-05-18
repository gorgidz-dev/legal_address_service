# Design Review: Public Legal Address Marketplace

Date: 2026-05-18
Reviewed screen: public catalog / marketplace landing
Baseline direction: Premium B2B, pragmatic Linear-like, indigo palette

## Screenshots Captured

- `screenshots/review-public-catalog-top-desktop-1280.png`
- `screenshots/review-public-catalog-top-tablet-768.png`
- `screenshots/review-public-catalog-top-mobile-375.png`
- `screenshots/review-public-catalog-grid-desktop-1280.png`
- `screenshots/review-public-catalog-grid-tablet-768.png`
- `screenshots/review-public-catalog-grid-mobile-375.png`
- `screenshots/review-public-catalog-desktop-1280.png`
- `screenshots/review-public-catalog-tablet-768.png`
- `screenshots/review-public-catalog-mobile-375.png`

## What Works

- The public catalog already has a coherent product spine: hero, stats, guided configurator, sticky filters, card grid, comparison, application CTA, owner path, FAQ.
- The indigo design system is scoped cleanly under `.ds-*` and is separated from the legacy dashboard styling.
- The card grid is understandable and task-oriented: price, term, correspondence option, IFNS, and application CTA are all visible without opening a modal.
- Desktop and tablet layouts are usable and close to a shippable SaaS/B2B marketplace baseline.

## Must Fix

- Mobile top nav overflows horizontally: the primary CTA is clipped at 375px. The header needs a mobile-specific action layout, likely brand + compact icon action or a two-row header.
- Mobile configurator is too dense: fields stay in a two-column grid, so labels and controls compress. Use a single-column/mobile-first form rhythm below 640px.
- The page repeats two filter systems: the large configurator and the sticky catalog filter bar expose overlapping controls. They should have distinct jobs or be merged.

## Should Fix

- The hero is typographically strong but visually empty for a marketplace. It needs one credible product/market signal: a preview strip, verified-address module, document stack, or map/list hybrid.
- Fallback card artwork feels illustrative and synthetic, while the spec asks for real building photos / owner uploads. Until real photos are available, fallback imagery should look like a deliberate placeholder system rather than primary art.
- Card hierarchy is close but crowded: compare, new badge, photo count, term toggle, correspondence checkbox, price, and CTA compete. Move compare into a less dominant control or reserve it for hover/selection mode on desktop.
- The sticky filter bar is useful but visually heavy on tablet/mobile. It should collapse to a compact search + filters button pattern on small screens.

## Design Options

### Option A: Pragmatic SaaS Polish

Keep the current Linear-like direction. Fix mobile, reduce duplicated filters, tighten cards, and add a restrained trust/document module in the hero. Lowest risk and fastest path.

### Option B: Marketplace Editorial

Make the page more visual: larger real-address media, more spatial storytelling, richer owner/client sections, and more editorial card treatment. Better first impression, higher content/image dependency.

### Option C: Operational Procurement Tool

Shift toward dense comparison and selection: sticky side filter, more table-like cards, stronger IFNS/service facets, comparison drawer. Best for repeat users and accountants, less emotional for first-time buyers.

## Recommendation

Use Option A as the base, borrow one controlled visual move from Option B for the hero, and reserve Option C patterns for comparison/search power features. This preserves the product work already done while making the page feel more credible and less generated.
