# Damu dashboard design system

## Product context

Internal Damu dashboard for monitoring plan execution and financial-support instruments. The audience is analysts and decision-makers who need to compare programmes quickly and trust the displayed values. The main page is an operational dashboard, not a public marketing site.

## Target component: Programme breakdown

The component compares the three financial instruments — Guaranteeing, Lending and Subsidising — with programme rows inside each column. Every row must make two separate values legible: amount used (billions of tenge) and project count. Keep relative scale within its own instrument column, label the units explicitly, and avoid relying on colour alone.

## Visual direction

- Preserve the existing institutional Damu character: calm, analytical and highly legible.
- Use the project’s local Golos Text family and its standard dashboard type hierarchy; do not introduce a serif or display font.
- Use neutral light-grey canvas, white cards, compact 12–16px spacing rhythm, subtle 8–12px radii, and low-elevation shadows.
- Keep the configured Damu green as the primary brand accent. Use gold/ochre and teal only as consistent category identifiers for the other instruments.
- Treat data visualisation as the focus: strong numeric alignment, quiet supporting labels, hairline rules, accessible contrast and uncluttered legends.
- Support the existing `[data-theme="dark"]` mode with the same information hierarchy.

## Interaction and responsive behaviour

- Desktop: one comparison card with three equal columns; rows retain one scanning order and both measures stay aligned.
- Tablet: retain columns only if their labels remain readable; otherwise use horizontal scroll with persistent column headings.
- Mobile: show one instrument at a time through accessible tabs/segmented control, preserving both metrics in each row.
- Allow a programme row to expose a compact hover/focus state and optional drill-down affordance, but do not imply interaction that the product does not implement.

## Non-negotiables

- All labels stay in Russian/Kazakh product language already used by the dashboard.
- Do not add decorative photos, gradients, glassmorphism, neons, new brand marks or speculative KPIs.
- Keep actual data names and units from the supplied screen.
