# Key page dependency trees

## `/` — Home dashboard

Entry: `pages/main.py`

Dependencies:

- `core/data.py` — years and dashboard data availability
- `core/mockup.py` — programme and instrument presentation data
- `core/charts.py` — map/chart rendering
- `core/theme.py` — user-configurable brand tokens
- `app.py`
  - `navbar()`
  - `filters_bar()`
  - `sections_modal()`
  - `serve_layout()`
- `assets/custom.css`
- `assets/dashboard.js`
- `assets/logo.png`

Relevant home render branch:

- `pages/main.py:showcase()` builds the desktop main content.
- `pages/main.py:programs_block()` renders the target programme breakdown card.
- `pages/main.py:_prog_rows_glass_fly_v1/v2/v3()` render the three temporary comparison patterns visible in the supplied reference.

## `/section/<key>` — Detail dashboard

Entry: `pages/section.py`

Dependencies:

- `core/data.py`
- `core/widgets.py`
- `core/charts.py`
- `assets/custom.css`

## `/settings` — Brand configuration

Entry: `pages/settings.py`

Dependencies:

- `core/theme.py`
- `core/auth.py`
- `assets/custom.css`

