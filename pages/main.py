import dash 
from dash import html

dash.register_page(__name__, path='/', name='Главная', title='Дашборд Даму')

layout = html.Div([
    html.H2('Привет, это главная страница'),
    html.P("ёжик сдлелал проверку текста начальные инвестиции:150 000 tenge"),
    html.P("Проверка символов: 1 234 567 ₸ · 87,5 % · «кавычки» — тире")
])
