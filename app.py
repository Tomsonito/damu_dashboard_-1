import dash 
import dash_bootstrap_components as dbc
from dash import html, dcc

app = dash.Dash (
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

server = app.server 

app.layout = html.Div([
    html.H1('Тестим начало'),
    dash.page_container,
])

if __name__ == "__main__":
    app.run(debug=True)