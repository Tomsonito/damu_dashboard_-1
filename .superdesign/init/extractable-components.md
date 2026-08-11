# Extractable components

## AppShell

- Source: `app.py` (`serve_layout`)
- Category: layout
- Description: shared navigation and page-container shell.
- Extractable props: activePath, isAdmin, updatedDate, updatedTime.
- Hardcoded: Damu brand treatment, navigation labels and theme-toggle icon treatment.

## TopNavigation

- Source: `app.py` (`navbar`)
- Category: layout
- Description: brand, primary navigation, data freshness and utility actions.
- Extractable props: activeItem, isAdmin, updatedAt.
- Hardcoded: primary route labels, logo and standard action icons.

## ProgrammesComparison

- Source: `pages/main.py` (`programs_block`, `_prog_rows_glass_fly_v*`)
- Category: basic
- Description: three instrument columns comparing amount and project count by programme.
- Extractable props: columns, amountLabel, countLabel, activeMetric, selectedProgramme.
- Hardcoded: instrument colour mapping and neutral baseline tracks.

