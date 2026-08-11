# Shared layouts

## `app.py` — `serve_layout`

The global application shell renders the top navigation, hidden global filters, a sections modal, a publish banner and Dash's page container.

```python
def serve_layout():
    return html.Div([
        dcc.Interval(id="data-poll", interval=30 * 1000),
        dcc.Store(id="data-version", data=_safe_version()),
        navbar(),
        html.Div(filters_bar(), id="filters-wrap"),
        sections_modal(),
        html.Div([html.Div(id="publish-banner"), dash.page_container],
                 className="damu-content"),
    ])
```

## `app.py` — `navbar`

The top navigation contains the configured Damu brand/logo, Home, an Explore dropdown, a Sections modal trigger, theme toggle, optional admin settings and data freshness status. It uses `.damu-nav` and reads `data-navbar` for the selected light/dark navbar variant.

## `pages/main.py` — home-page composition

`showcase(year, expanded)` composes: title row → annual band → instrument card grid → programmes card. The programmes card therefore belongs below overview metrics and should remain a compact analytical component rather than a marketing section.

