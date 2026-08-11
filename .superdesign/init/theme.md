# Theme

## Compact token summary

- Framework: Dash + Bootstrap 5 (`dash-bootstrap-components`), custom CSS in `assets/custom.css`.
- Typeface: local Golos Text font files are bundled in `assets/fonts`; the active family can be changed in Settings.
- Product palette: Damu brand green is the primary accent; complementary gold/ochre and teal accents distinguish financial instruments. The UI is data-dense, quiet and institutional rather than promotional.
- Surfaces: light neutral page background, white cards, restrained shadow, thin neutral separators. Dark mode is supported through `[data-theme="dark"]`.
- Main CSS variables are injected by `core/theme.py:css_variables()` and include `--damu-accent`, `--damu-accent-2`, `--damu-accent-3`, `--damu-ink`, `--damu-muted`, `--damu-bg`, and `--damu-card`.
- Responsive structure: Bootstrap container/grid; programme comparison is three columns on desktop and needs a deliberate tablet/mobile presentation.

## Source locations

- Runtime theme configuration and CSS-variable output: `core/theme.py`.
- All component selectors, responsive rules, dark-theme overrides and `@font-face` declarations: `assets/custom.css`.
- Brand asset: `assets/logo.png`.

