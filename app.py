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
    # dev_tools_hot_reload=False — иначе Dash сам перезагружает страницу при любой
    # правке файла, и все выбранные фильтры слетают на исходные. Понятные сообщения
    # об ошибках от debug=True при этом остаются.
    # Правки кода теперь видны после ручного обновления страницы (F5).
    app.run(debug=True, dev_tools_hot_reload=False)