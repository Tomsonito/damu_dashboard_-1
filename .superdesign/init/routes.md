# Routes

Dash Pages supplies routing via `dash.register_page`.

| Path | Module | Purpose |
| --- | --- | --- |
| `/` | `pages/main.py` | Home dashboard: plan execution, instruments and programme breakdown |
| `/section/<key>` | `pages/section.py` | Section-level KPIs and configurable widgets |
| `/explore` | `pages/explore.py` | Gallery of data-exploration examples |
| `/explore/<key>` | `pages/explore_example.py` | Individual example |
| `/plan` | `pages/plan_input.py` | Plan data input and publication workflow |
| `/widgets` | `pages/widgets_edit.py` | Widget configuration |
| `/settings` | `pages/settings.py` | Brand and theme configuration |

The shared shell is created by `app.py:serve_layout`; page contents are inserted via `dash.page_container`.

