"""МАКЕТНЫЕ ЧИСЛА витрины инструментов.

!! Здесь НЕТ настоящих данных. Все числа взяты из макетов (Claude Design)
и к показателям Фонда отношения не имеют. Файл существует ровно потому,
что раскладку собрали раньше, чем появились данные под неё: в боевой базе
нет ни разреза по инструментам (Гарантирование / Кредитование /
Субсидирование), ни разбивки по программам, ни счётчика уникальных проектов.

Числа читают трое: главная (`pages/main.py`), страницы-примеров
(`pages/explore_example.py`) и карточки раздела. Набор один на всех
намеренно: увидеть на главной 1 501, а в примере 1 421 и гадать, откуда
разница, — худшее, что можно сделать с выдуманными числами.

**Как это устроено и почему так.** Числа собраны в одном файле, а не
разбросаны по разметке страниц, чтобы замена была механической: когда
разрезы появятся в хранилище, страницы начнут звать `core/data.py`
вместо этого модуля, а файл удаляется целиком. Пока же на экране рядом
с макетными блоками стоит честная плашка «Макетные числа».

Чем это отличается от демо-данных (`etl/make_samples.py`): те выдуманные
строки лежат в хранилище, участвуют в фильтрах и считаются как настоящие;
эти — просто константы для показа раскладки. Смешать их нельзя.

Считаемое (проценты, статус, ожидаемый темп) здесь именно СЧИТАЕТСЯ,
а не вписано числом: иначе при первой же правке плана проценты разъехались
бы с числами, из которых они якобы получены.
"""

from datetime import date

#: Оттенок карточки: 1 — основной цвет темы, 2 — второй цвет,
#: 3 — второй затемнённый. Цвета сами лежат в теме (core/theme.py),
#: здесь только номер: макет не должен знать, какой сейчас цвет.
TONE_MAIN, TONE_SECOND, TONE_THIRD = 1, 2, 3

#: Месяцы помесячных рядов — с января по июль, все закрытые месяцы
#: 2026 года. Будущих месяцев в рядах нет вовсе; там, где год показывают
#: целиком, недостающие месяцы рисуются пустыми (см. примеры 1, 4 и 5).
MONTHS7 = ("Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл")

#: Все двенадцать — для прошлого года, который закончился целиком.
MONTHS12 = ("Янв", "Фев", "Мар", "Апр", "Май", "Июн",
            "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек")

#: Во сколько раз числа прошлого года больше нынешних. Одно число на всё:
#: макет показывает, что переключатель годов меняет весь экран, а не
#: изображает точную историю — настоящие годы придут из хранилища.
LAST_YEAR_FACTOR = 1.28

#: Сколько последних месяцев видно в свёрнутом графике. Тумблер «Графики
#: за весь год» разворачивает до всех ПРОШЕДШИХ месяцев; будущие
#: не показываются ни в одном состоянии.
MONTHS_COLLAPSED = 6

#: Инструменты: план и факт в млрд ₸, проекты и уникальные — в штуках.
#:
#: Помесячных рядов у каждого два и они устроены одинаково: `*_by_month` —
#: закрытые месяцы текущего года (Янв–Июл), `*_by_month_full` — все двенадцать
#: прошлого. Денежные ряды (`money_*`) **складываются ровно в `fact`** — оба.
#: Иначе на экране рядом стояли бы «освоено 1 501» и столбики на другую сумму,
#: и человек справедливо не поверил бы ни одному из двух чисел. За тем, что
#: они не разъехались, следит проверка `_check_sums()` сразу под списком.
#:
#: !! «Все инструменты» — не отдельная строка с СВОИМИ числами, а сумма
#: трёх остальных (считается ниже, `_all_instrument()`). До 13.08.2026 факт
#: и план стояли вписанными вручную (1 501 / 1 912) и разошлись с суммой
#: трёх инструментов (1 421) — на 80 единиц, без единой ошибки, потому что
#: складывать их никто не заставлял. Поймано пользователем на разбивке
#: по программам: там сумма считается по-настоящему, и она не совпала
#: с карточкой-итогом. Тот же принцип файла, что и `_check_sums()`
#: чуть ниже, применённый на уровень выше — к самому итогу, а не только
#: к его помесячным рядам.
_REAL_INSTRUMENTS = [
    {
        "key": "guarantee",
        "title": "Гарантирование",
        "tone": TONE_SECOND,
        "plan": 620, "fact": 540,
        "projects_plan": 500, "projects_fact": 430, "unique": 340,
        "money_by_month": (38, 55, 96, 71, 122, 65, 93),
        "money_by_month_full": (28, 34, 62, 46, 78, 42, 61,
                                55, 38, 47, 30, 19),
        "projects_by_month": (42, 18, 74, 55, 96, 63, 82),
        "projects_by_month_full": (42, 18, 74, 55, 96, 63, 82, 88, 71, 94, 80, 57),
    },
    {
        "key": "credit",
        "title": "Кредитование",
        "tone": TONE_SECOND,
        "plan": 810, "fact": 650,
        "projects_plan": 550, "projects_fact": 470, "unique": 360,
        "money_by_month": (44, 38, 128, 46, 175, 82, 137),
        "money_by_month_full": (34, 29, 88, 35, 116, 54, 92,
                                66, 45, 52, 25, 14),
        "projects_by_month": (55, 24, 88, 41, 102, 76, 84),
        "projects_by_month_full": (55, 24, 88, 41, 102, 76, 84, 91, 72, 101, 85, 61),
    },
    {
        "key": "subsidy",
        "title": "Субсидирование",
        "tone": TONE_THIRD,
        "plan": 482, "fact": 231,
        "projects_plan": 350, "projects_fact": 149, "unique": 75,
        "money_by_month": (14, 22, 34, 24, 51, 32, 54),
        "money_by_month_full": (11, 16, 24, 17, 35, 22, 37,
                                26, 14, 15, 9, 5),
        "projects_by_month": (12, 5, 31, 18, 42, 20, 21),
        "projects_by_month_full": (12, 5, 31, 18, 42, 20, 21, 22, 18, 26, 21, 15),
    },
]


def _sum_series(*series: tuple[int, ...]) -> tuple[int, ...]:
    """Поэлементная сумма нескольких помесячных рядов одинаковой длины."""
    return tuple(sum(v) for v in zip(*series))


def _all_instrument() -> dict:
    """«Все инструменты» — сумма трёх настоящих, посчитанная, а не вписанная."""
    return {
        "key": "all", "title": "Все инструменты", "tone": TONE_MAIN,
        "plan": sum(i["plan"] for i in _REAL_INSTRUMENTS),
        "fact": sum(i["fact"] for i in _REAL_INSTRUMENTS),
        "projects_plan": sum(i["projects_plan"] for i in _REAL_INSTRUMENTS),
        "projects_fact": sum(i["projects_fact"] for i in _REAL_INSTRUMENTS),
        "unique": sum(i["unique"] for i in _REAL_INSTRUMENTS),
        "money_by_month": _sum_series(*(i["money_by_month"] for i in _REAL_INSTRUMENTS)),
        "money_by_month_full": _sum_series(
            *(i["money_by_month_full"] for i in _REAL_INSTRUMENTS)),
        "projects_by_month": _sum_series(
            *(i["projects_by_month"] for i in _REAL_INSTRUMENTS)),
        "projects_by_month_full": _sum_series(
            *(i["projects_by_month_full"] for i in _REAL_INSTRUMENTS)),
    }


INSTRUMENTS = [_all_instrument(), *_REAL_INSTRUMENTS]


def _check_sums() -> None:
    """Денежные ряды обязаны складываться в `fact` — проверяем при импорте.

    Ряды правят руками (это макет), и опечатка в одной цифре не сломала бы
    ничего заметно: столбики просто нарисовались бы от другой суммы, а число
    рядом осталось прежним. Расхождение чисел, которые якобы получены одно
    из другого, — ровно то, ради чего в этом файле всё считается, а не лежит
    отдельно. Дешевле поймать при запуске, чем глазами на экране.
    """
    for item in INSTRUMENTS:
        for key in ("money_by_month", "money_by_month_full"):
            total = sum(item[key])
            if total != item["fact"]:
                raise ValueError(
                    f"{item['key']}.{key}: сумма {total} != факт {item['fact']}"
                )


_check_sums()

#: Разбивка по программам: четыре колонки, в каждой строки
#: «название — освоено (млрд ₸) — проектов (шт)».
#:
#: !! Строки трёх инструментов ниже (гарантирование/кредитование/
#: субсидирование) — не готовые числа, а ФОРМА: пропорция между
#: программами (какая крупнее, какая мельче) настоящая, вручную
#: подобранная, а сама сумма пересчитывается под факт инструмента через
#: `_scale_rows()`. До 13.08.2026 суммы были независимо вписаны и
#: расходились с фактом на карточке — местами в разы (например у
#: «Кредитования» строки по проектам складывались в 19 714 штук при факте
#: 470). Колонка «Все инструменты» и вовсе не считалась вообще — теперь
#: её три строки берутся прямо из `_REAL_INSTRUMENTS`, тем же числом,
#: что и карточка.
def _scale_rows(rows: list[tuple], target_amount: int, target_count: int) -> list[tuple]:
    """Пересчитывает столбец строк так, чтобы суммы совпали с фактом
    инструмента, а форма (какая программа больше, какая меньше) осталась.

    Наибольший остаток, а не поштучное округление: округлить каждую
    строку по отдельности не гарантирует, что сумма сойдётся ровно —
    полтора десятка округлений дают разброс в несколько единиц, и это
    была бы та же самая ошибка на меньшем масштабе.

    !! Мелкой программе гарантирован минимум 1, если она не пустая
    изначально: у «Кредитования» разброс исходных весов доходил до 833
    раз (12 500 против 15), и обычное пропорциональное округление
    обнуляло мелкие строки — на экране выходило «128 млрд ₸, 0 шт»,
    деньги есть, а проектов как бы нет. Занимает у самых крупных строк,
    сумма всё равно остаётся точной.
    """
    def scale(values: list[int], target: int) -> list[int]:
        total = sum(values)
        if not total:
            return [0] * len(values)
        nonzero = sum(1 for v in values if v > 0)
        if target < nonzero:
            # Меньше единиц, чем ненулевых строк, — гарантию не выполнить,
            # остаётся обычное распределение по наибольшему остатку
            raw = [v * target / total for v in values]
            floors = [int(v) for v in raw]
            remainder = target - sum(floors)
            order = sorted(range(len(values)), key=lambda i: raw[i] - floors[i],
                           reverse=True)
            for i in order[:remainder]:
                floors[i] += 1
            return floors

        guaranteed = [1 if v > 0 else 0 for v in values]
        rest_target = target - sum(guaranteed)
        raw = [v * rest_target / total for v in values]
        floors = [int(v) for v in raw]
        remainder = rest_target - sum(floors)
        order = sorted(range(len(values)), key=lambda i: raw[i] - floors[i],
                       reverse=True)
        for i in order[:remainder]:
            floors[i] += 1
        return [g + f for g, f in zip(guaranteed, floors)]

    names = [r[0] for r in rows]
    amounts = scale([r[1] for r in rows], target_amount)
    counts = scale([r[2] for r in rows], target_count)
    return list(zip(names, amounts, counts))


PROGRAMS = [
    {
        "title": "Все инструменты",
        "tone": TONE_MAIN,
        "rows": [(i["title"], i["fact"], i["projects_fact"])
                 for i in _REAL_INSTRUMENTS],
    },
    {
        "title": "Гарантирование — программы",
        "tone": TONE_SECOND,
        "rows": _scale_rows([
            ("ГФ2", 128, 145),
            ("ГФ1", 96, 110),
            ("АПК", 74, 88),
            ("МТИ", 51, 62),
            ("Агробизнес", 33, 40),
            ("Моно", 18, 21),
        ], _REAL_INSTRUMENTS[0]["fact"], _REAL_INSTRUMENTS[0]["projects_fact"]),
    },
    {
        "title": "Кредитование — программы",
        "tone": TONE_SECOND,
        "rows": _scale_rows([
            ("Крупный биз.", 450, 20),
            ("Обработка", 180, 150),
            ("Өрлеу", 118, 1320),
            ("Ислам фин", 77, 84),
            ("Лизинг", 58, 630),
            ("Даму Регион", 42, 4700),
            ("Үміт", 29, 310),
            ("Микро", 15, 12500),
        ], _REAL_INSTRUMENTS[1]["fact"], _REAL_INSTRUMENTS[1]["projects_fact"]),
    },
    {
        "title": "Субсидирование — программы",
        "tone": TONE_THIRD,
        "rows": _scale_rows([
            ("Факторинг", 320, 15),
            ("Іскер Аймақ", 150, 400),
            ("Даму-Көпір", 47, 850),
            ("ИП Старт", 31, 5200),
            ("Сервис", 19, 820),
            ("Кооперация", 9, 12),
        ], _REAL_INSTRUMENTS[2]["fact"], _REAL_INSTRUMENTS[2]["projects_fact"]),
    },
]


def _check_programs() -> None:
    """Разбивка по программам обязана складываться в факт своей карточки.

    `_scale_rows()` это гарантирует арифметически, но проверка при
    импорте — на случай, если кто-то однажды впишет строку в `PROGRAMS`
    в обход неё (тем же способом, что и `_check_sums()` выше: дешевле
    поймать при запуске, чем глазами на экране)."""
    for program, instrument in zip(PROGRAMS[1:], _REAL_INSTRUMENTS):
        amount = sum(r[1] for r in program["rows"])
        count = sum(r[2] for r in program["rows"])
        if amount != instrument["fact"]:
            raise ValueError(
                f"{instrument['key']}: сумма программ {amount} != факт "
                f"{instrument['fact']}"
            )
        if count != instrument["projects_fact"]:
            raise ValueError(
                f"{instrument['key']}: сумма проектов {count} != факт "
                f"{instrument['projects_fact']}"
            )


_check_programs()


def expected_pace(today: date | None = None) -> tuple[float, int, int]:
    """Ожидаемый темп: какая доля года прошла, в процентах.

    Главная мысль макета: сравнивать факт не с годовым планом целиком,
    а с тем, сколько к сегодняшнему дню **должно** быть освоено, если
    осваивать ровно. На 29 июля прошло 210 дней из 365 — значит ожидаем
    57.5 %, и 48 % у субсидирования это отставание, хотя «почти половина».

    Считается от сегодняшней даты, а не вписано числом: иначе к сентябрю
    страница бы уверенно врала про июльский темп. Возвращает и сами дни —
    их показываем рядом, чтобы число не выглядело взятым с потолка.
    """
    today = today or date.today()
    day_of_year = today.timetuple().tm_yday
    days_in_year = date(today.year, 12, 31).timetuple().tm_yday
    return day_of_year / days_in_year * 100, day_of_year, days_in_year


def for_year(year: int | None = None, expanded: bool = False,
             today: date | None = None) -> list[dict]:
    """Инструменты, пересчитанные под выбранный год, со всем считаемым.

    Что делает год. Текущий — числа как есть, ожидаемый темп считается
    по сегодняшней дате, в графике только **закрытые** месяцы. Прошлый —
    числа умножаются на `LAST_YEAR_FACTOR`, темп равен 100 % (год кончился),
    в графике все двенадцать месяцев.

    Будущие месяцы не показываются ни в одном состоянии — это требование
    макета, и оно же здравый смысл: столбик за декабрь в июле означал бы
    ноль, который читался бы как провал.
    """
    today = today or date.today()
    pace, day, days = expected_pace(today)
    current = year is None or int(year) >= today.year
    if not current:
        pace, day, days = 100.0, days, days

    out = []
    for item in INSTRUMENTS:
        factor = 1.0 if current else LAST_YEAR_FACTOR
        fact = round(item["fact"] * factor)
        projects_fact = round(item["projects_fact"] * factor)
        unique = round(item["unique"] * factor)

        months = (item["projects_by_month"] if current
                  else item["projects_by_month_full"])
        labels = MONTHS7 if current else MONTHS12
        months = [round(v * factor) for v in months]
        # !! Итог за год считается ДО обрезки списка. Раньше страница
        # складывала показанные месяцы и подписывала «за год»: в свёрнутом
        # виде это была сумма шести месяцев, и при развороте число прыгало
        # (поймано пользователем 10.08.2026). Год не зависит от того,
        # сколько месяцев поместилось на экран.
        months_total = sum(months)
        if not expanded and len(months) > MONTHS_COLLAPSED:
            months = months[-MONTHS_COLLAPSED:]
            labels = labels[-MONTHS_COLLAPSED:]

        percent = fact / item["plan"] * 100 if item["plan"] else 0.0
        projects_percent = (projects_fact / item["projects_plan"] * 100
                            if item["projects_plan"] else 0.0)
        # Доля уникальных среди состоявшихся проектов. Считается здесь,
        # рядом с остальным производным, а не в разметке страницы: правило
        # файла — то, что выводится из чисел, выводится в одном месте,
        # иначе однажды разойдётся с ними
        unique_share = (unique / projects_fact * 100) if projects_fact else 0.0
        gap = percent - pace
        out.append({
            **item,
            "fact": fact, "projects_fact": projects_fact, "unique": unique,
            "repeat": projects_fact - unique, "unique_share": unique_share,
            "months": months, "month_labels": tuple(labels),
            "months_total": months_total,
            "percent": percent, "projects_percent": projects_percent,
            "pace": pace, "pace_day": day, "pace_days": days,
            # Плашка статуса («По графику»/«Отставание») убрана 13.08.2026 —
            # решение пользователя после разбора: цвет тревоги (тёплое золото)
            # путался с цветом «Кредитования», у которого золото — это личность
            # инструмента, а не сигнал. `on_track`/`gap` остаются: на них
            # держится словесная фраза «отстаёт от плана на X п.п.»
            "gap": gap, "on_track": gap >= 0,
        })
    return out


def can_expand(year: int | None = None, today: date | None = None) -> bool:
    """Есть ли что разворачивать: прошло ли месяцев больше, чем видно сразу."""
    today = today or date.today()
    current = year is None or int(year) >= today.year
    months = (INSTRUMENTS[0]["projects_by_month"] if current
              else INSTRUMENTS[0]["projects_by_month_full"])
    return len(months) > MONTHS_COLLAPSED


def card_numbers(item: dict, today: date | None = None) -> dict:
    """Всё считаемое для одной карточки инструмента.

    Проценты и статус выводятся из плана и факта, а не лежат рядом с ними
    отдельными числами — иначе они бы однажды разошлись.
    """
    pace, _, _ = expected_pace(today)
    percent = item["fact"] / item["plan"] * 100 if item["plan"] else 0.0
    projects = (
        item["projects_fact"] / item["projects_plan"] * 100
        if item["projects_plan"] else 0.0
    )
    gap = percent - pace
    # Словами разрыв описывает страница (pages/main.py): здесь числа,
    # там — как их писать. Иначе форматирование чисел жило бы в двух местах
    # и однажды разошлось бы (в шкале запятая, в подписи точка).
    return {
        "percent": percent,
        "projects_percent": projects,
        "pace": pace,
        "gap": gap,
        "on_track": gap >= 0,
    }
