# Reusable UI components

The project is a server-rendered Python Dash application using `dash-bootstrap-components`; visual components are factory functions, not React files.

## `pages/main.py` — `programs_block`

- Description: a three-column comparison of Damu financial instruments, with total amount, programme rows and two proportional measures per row.
- Key inputs: `core.mockup.PROGRAMS`; each row is `(name, amount, count)`.
- Important visual subcomponents: `damu-prog-grid`, `damu-prog-col`, `damu-prog-head`, `damu-prog-row`, and the glass/butterfly row variants.

```python
def programs_block() -> dbc.Card:
    tones = {"Гарантирование": 1, "Кредитование": 2, "Субсидирование": 3}
    columns = []
    for column, (build_rows, variant) in zip(mockup.PROGRAMS[1:], PROG_VARIANTS):
        short = column["title"].split(" — ")[0]
        top_amount = max(row[1] for row in column["rows"])
        top_count = max(row[2] for row in column["rows"])
        columns.append(html.Div([
            html.Div([
                html.Span(short, className="damu-prog-head flex-grow-1"),
                html.Span(num(sum(r[1] for r in column["rows"])),
                          style={"marginLeft": "auto", "fontSize": "0.81rem", "fontWeight": 800,
                                 "color": "var(--damu-c)"}),
            ], className="d-flex align-items-baseline gap-2 pb-2"),
            html.Div(variant, className="damu-prog-variant"),
            *build_rows(column["rows"], top_amount, top_count),
        ], className=f"damu-prog-col damu-c-{tones[short]}"))
    return dbc.Card(dbc.CardBody([
        html.Div(columns, className="damu-prog-grid",
                 style={"gridTemplateColumns": "repeat(3, minmax(0,1fr))"}),
    ]), class_name="shadow-sm")
```

## `pages/main.py` — programme-row variants

- `_prog_rows_glass_fly_v1`: symmetric two-track “butterfly” with a centre node.
- `_prog_rows_glass_fly_v2`: continuous capsule with a centred divider.
- `_prog_rows_glass_fly_v3`: denser inline layout with programme name at left.
- These variants are currently displayed side-by-side to evaluate composition; the production design should choose one coherent, accessible pattern.

## `pages/main.py` — `band` and `instrument_card`

- Description: the other reusable home-page data-visualisation cards.
- Use them as the visual reference for the redesigned programmes component.

