import dash 
import dash_bootstrap_components as dbc
from dash import html

app = dash.Dash (
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

server = app.server

app.layout = html.Div([
    dbc.NavbarSimple(
        brand='Дашборд Даму',
        color='dark',
        dark=True,
        fluid=True,
    ),
    dash.page_container,
])

if __name__ == "__main__":
    app.run(debug=True)