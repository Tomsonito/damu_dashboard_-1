/* Мелкая логика страницы раздела: прокрутка к секции, подсветка вкладки
   при прокрутке и сворачивание списка разделов.

   Почему это здесь, а не коллбэком Dash. Всё три вещи — про вид, а не
   про данные, и происходят десятками раз в секунду (движение колеса мыши).
   Коллбэк на каждое такое движение слал бы запрос на сервер, и страница
   тормозила бы на ровном месте. Здесь же браузер справляется сам,
   не выходя наружу.

   Dash подхватывает всё из assets/ сам — подключать файл в коде не нужно.

   Разметку рисует pages/section.py, договор между ними — data-атрибуты:

     data-scroll-to     на пилюле   — id секции, к которой прокрутить
     data-target-key    на пилюле   — ключ секции-цели: подсвечиваем её
                                      сразу, не дожидаясь конца прокрутки
     data-sub-key       на пилюле   — ключ секции этой пилюли
     data-key           на секции   — ключ этой секции
     data-chart         на обёртке  — вид диаграммы: по нему решаем, можно
                        графика       ли подсвечивать по клику категорию
                                      (у «Годов» клик занят раскрытием года)
     data-toggle-sidebar на кнопке ☰

   !! Вкладок ВЕРХНЕГО уровня в этом списке больше нет (17.08.2026):
   с тех пор как вкладка переключает содержимое, ими целиком распоряжается
   сервер, и атрибуты `data-tab-key`, `data-members`, `data-group-row`
   не выставляются вовсе. Разбор — в шапке pages/section.py.

   Никакой логики в самих атрибутах нет: это просто способ передать
   браузеру то, что и так знает config.yaml. */

(function () {
    'use strict';

    /* Зазор между липкой полосой и заголовком секции после прокрутки.
       Уменьшил до 0 по просьбе пользователя («сделай просто скролл ниже»),
       чтобы секция заезжала чуть выше и гарантированно активировалась. */
    var TAB_GAP = 0;

    /* Насколько ниже верха окна проходит «линия чтения»: секция считается
       текущей, если её заголовок уже выше этой линии.

       Считается, а не задана числом: сверху липнут шапка и полоса вкладок,
       а их суммарная высота меняется — у шапки от выбранного размера текста,
       у полосы от того, раскрыт ли ряд «пилюль». С числом «на все случаи»
       подсветка переключалась бы на секцию, которую эти полосы как раз
       закрывают собой. */
    function readingLine() {
        return stickyHeight() + 20;
    }

    /* СТАБИЛЬНАЯ линия чтения — для определения текущей секции.

       Отличается от readingLine() тем, что НЕ учитывает высоту ряда
       «пилюль» (.damu-sec-subtabs). Зачем: ряд «пилюль» появляется и
       исчезает именно по результату определения текущей секции, и если
       readingLine зависит от его высоты, возникает петля обратной связи:

         1. highlight() показывает пилюли → readingLine сдвигается вниз
         2. currentSectionKey() определяет СЛЕДУЮЩУЮ секцию (вне группы)
         3. highlight() прячет пилюли → readingLine сдвигается обратно
         4. currentSectionKey() определяет ПРЕЖНЮЮ секцию → goto 1

       Результат — подсекции мигают каждый кадр (замечено 10.08.2026 на СЭЭ
       при прокрутке «Сохранённые раб. места» → «Отрасли»).

       Стабильная линия считает высоту шапки + ОСНОВНЫЕ вкладки, но без
       пилюль. Так показ/скрытие пилюль не влияет на определение секции,
       и петля разрывается. */
    function stableReadingLine() {
        var total = stickyHeight();
        
        /* Вычитаем высоту ряда пилюль, если он сейчас показан.
           Так линия чтения всегда равна высоте «чистой» шапки без пилюль,
           и показ/скрытие пилюль не заставляет секцию переключаться обратно. */
        document.querySelectorAll('.damu-sec-subtabs').forEach(function(row) {
            if (row.style.display !== 'none') {
                total -= row.offsetHeight;
            }
        });
        
        /* +150px — очень агрессивный отступ. Как только заголовок секции 
           поднимается ближе чем на 150px к липкой шапке, мы считаем секцию текущей.
           Это гарантирует переключение даже при погрешностях прокрутки или скролла мышью. */
        return total + 150;
    }

    /* Последний ключ, определённый highlight(). Используется как гистерезис:
       на самой границе между группой и следующей секцией даём допуск
       в HYSTERESIS px, чтобы мелкие колебания прокрутки не переключали
       подсветку туда-сюда. */
    var lastKey = null;
    var HYSTERESIS = 30;

    /* Куда мы сейчас едем по нажатию вкладки. Пока едем, подсветка держит
       ЦЕЛЬ, а не то, что под линией чтения прямо сейчас.

       Зачем: у группы (ГФ1) при подсветке появляется ряд «пилюль», а он
       делает полосу вкладок выше. Если бы подсветка шла за живой прокруткой,
       ряд то появлялся, то исчезал по дороге — страница дёргалась бы,
       а плавная прокрутка не доезжала до цели, потому что цель на ходу
       сдвигается вниз. */
    var targetKey = null;
    var releaseTimer = null;

    /* Куда именно прокручивать по нажатию на вкладку или «пилюлю».

       Правило простое, но считается, а не задано числом: человек должен
       увидеть СОДЕРЖИМОЕ секции целиком и не крутить дальше сам.

       Раньше сюда приезжал верх всего блока — а первым в блоке стоит его
       подпись («ВЫПУСК ПРОДУКЦИИ»). Она занимала верх экрана, и ровно
       на её высоту не помещался низ графика: приходилось докручивать
       (замечено пользователем 11.08.2026). Подпись при этом ничего нового
       не сообщает — то же название подсвечено в «пилюле» выше и написано
       на карточке-показателе.

       Поэтому едем НЕ к верху блока, а к точке сразу под подписью — это
       и есть «скролл ниже» из просьбы: прокрутка становится немного
       ГЛУБЖЕ прежней (на высоту подписи), а не мельче. Подпись при этом
       уезжает под липкую полосу вкладок, а не пропадает — просто её не
       видно поверх контента, как «Регионы»/«Отрасли» не видно на скрине.

       !! Двух формул с одинаковым знаком неравенства НЕ применяем.
       В первой версии здесь стоял `if (bottomLimit < top) top = bottomLimit`
       — он должен был не пускать прокрутку ЗА пределы блока, а на деле
       откатывал её НАЗАД до того же места, что и раньше, отменяя
       весь смысл правки (проверено арифметикой: 1432 против 1349 —
       меньшее число отменяло пропуск подписи). Верно наоборот: если блок
       короче, чем свободное место, `bottomLimit` сам получится МЕНЬШЕ
       `top`, и большего (`top`) достаточно — оно не даёт съехать дальше
       конца блока. Проверять надо через `Math.max`, а не `if <`. */
    function scrollTargetFor(block) {
        var rect = block.getBoundingClientRect();
        var top = window.scrollY + rect.top - stickyHeight() - TAB_GAP;

        /* Пропускаем подпись блока — вместе с её нижним отступом. */
        var head = block.querySelector('.damu-sec-block-title');
        if (head) {
            var style = window.getComputedStyle(head);
            top += head.offsetHeight + (parseFloat(style.marginBottom) || 0);
        }

        return Math.max(0, top);
    }

    /* Высота всего, что липнет к верху окна: шапка сайта плюс полоса вкладок
       раздела. От неё зависят и линия чтения, и место, куда прокручивать. */
    function stickyHeight() {
        var total = 0;
        var nav = document.querySelector('.damu-nav');
        if (nav && window.getComputedStyle(nav).position === 'sticky') {
            total += nav.offsetHeight;
        }
        var bar = document.querySelector('.damu-sec-tabbar');
        if (bar) {
            total += bar.offsetHeight;
        }
        return total;
    }

    /* Высоту шапки отдаём в CSS переменной: от неё отсчитывают свой `top`
       все остальные липкие элементы (полоса вкладок, список разделов,
       кнопка ☰). Замер, а не число в стилях: шапка выше при крупном тексте
       и ниже при компактном, а стили об этом знать не могут.

       Ставим только при изменении — присвоение переменной каждый кадр
       заставляло бы браузер пересчитывать стили на пустом месте. */
    var navHeightSet = null;
    function syncNavHeight() {
        var nav = document.querySelector('.damu-nav');
        if (!nav) {
            return;
        }
        var height = nav.offsetHeight;
        if (height && height !== navHeightSet) {
            navHeightSet = height;
            document.documentElement.style.setProperty('--damu-nav-h', height + 'px');
        }
    }

    /* То же, но для СУММЫ липких полос — шапки и полосы вкладок вместе.
       От неё отсчитывает свой `top` липкая подпись секции: она должна
       вставать вплотную под вкладками, а не под одной шапкой.

       Своя переменная, а не сумма в CSS через calc: высота полосы вкладок
       меняется на ходу — второй ряд появляется, когда раскрыта группа
       (замерено раньше: 45 px против 92). CSS об этом знать неоткуда,
       а здесь мы и так мерим это на каждый кадр для линии чтения.

       !! Вызывать ПОСЛЕ highlight(): это он показывает и прячет ряд
       «пилюль», то есть меняет ту самую высоту. До него измерили бы
       прошлое состояние и подпись прыгала бы на кадр позже. */
    var stickyHeightSet = null;
    function syncStickyHeight() {
        var height = stickyHeight();
        if (height && height !== stickyHeightSet) {
            stickyHeightSet = height;
            document.documentElement.style.setProperty('--damu-sticky-h', height + 'px');
        }
    }

    function currentSectionKey() {
        var blocks = document.querySelectorAll('.damu-sec-block');
        if (!blocks.length) {
            return null;
        }
        /* Считаем от края ОКНА (getBoundingClientRect), а не от начала
           документа: у секций есть позиционированный предок, и offsetTop
           у них отсчитывается от него, а не от страницы — сравнение
           с прокруткой окна давало бы промах на высоту шапки.

           !! Используем stableReadingLine(), а НЕ readingLine():
           та зависит от высоты пилюльного ряда, и показ/скрытие пилюль
           переключал бы секцию туда-обратно — мигание (10.08.2026). */
        var line = stableReadingLine();
        var key = blocks[0].getAttribute('data-key');
        blocks.forEach(function (block) {
            if (block.getBoundingClientRect().top <= line) {
                key = block.getAttribute('data-key');
            }
        });

        /* Гистерезис: если ключ изменился и новый блок ЕДВА пересёк линию
           чтения — даём допуск HYSTERESIS px, чтобы мелкие колебания
           прокрутки (дрожание мыши, инерция) не переключали подсветку.
           Допуск работает только «вниз» — переключение на следующую
           секцию задерживается, пока заголовок не уедет выше на HYSTERESIS,
           а переключение обратно на предыдущую происходит сразу. */
        if (lastKey && key !== lastKey) {
            var newBlock = document.getElementById('sec-block-' + key);
            if (newBlock) {
                var dist = line - newBlock.getBoundingClientRect().top;
                if (dist >= 0 && dist < HYSTERESIS) {
                    return lastKey;
                }
            }
        }
        lastKey = key;
        return key;
    }

    /* Подсвечивает «пилюлю» той подсекции, которую сейчас читают.

       !! Вкладки ВЕРХНЕГО уровня здесь больше не трогаются (17.08.2026).
       Раньше трогались: пока вкладка только прокручивала ленту, «активная»
       означала «докуда домотали», и знал это один браузер. Теперь вкладка
       переключает содержимое, то есть активная — это выбор человека,
       и хранит его страница (`section-tab`, pages/section.py). Возьмись
       за класс `active` оба — сервер по выбору и браузер по прокрутке, —
       они бы перетирали друг друга: щёлкнул по «Отрасли», сервер подсветил
       «Отрасли», а первый же поворот колеса вернул бы подсветку на ту
       вкладку, чья секция оказалась под линией чтения.

       Ряд пилюль тоже больше не прячется отсюда: его состав приходит
       с сервера и в нём всегда только одна группа — открытая. */
    function highlight() {
        var key = targetKey || currentSectionKey();
        if (key === null) {
            return;                 // мы не на странице раздела
        }

        document.querySelectorAll('.damu-sec-subtab').forEach(function (pill) {
            pill.classList.toggle(
                'active', pill.getAttribute('data-sub-key') === key
            );
        });
    }

    /* Пересчёт не чаще одного раза на кадр: событий прокрутки прилетает
       куда больше, чем экран успевает перерисовать. */
    var scheduled = false;
    function schedule() {
        if (scheduled) {
            return;
        }
        scheduled = true;
        window.requestAnimationFrame(function () {
            scheduled = false;
            syncNavHeight();
            highlight();
            /* Строго после highlight — он меняет высоту полосы вкладок,
               показывая или пряча ряд «пилюль» */
            syncStickyHeight();
        });
    }

    document.addEventListener('click', function (event) {
        /* Переключатель светлой и тёмной темы. Выбор личный и живёт
           в браузере: сервер отдаёт всем одинаковую страницу, а тему
           ставит атрибутом на <html> вот этот обработчик и близнец
           в <head> (app.py, THEME_BOOT), который успевает до отрисовки. */
        if (event.target.closest('[data-theme-toggle]')) {
            var root = document.documentElement;
            var dark = root.getAttribute('data-theme') === 'dark';
            if (dark) {
                root.removeAttribute('data-theme');
            } else {
                root.setAttribute('data-theme', 'dark');
            }
            try {
                localStorage.setItem('damu-theme', dark ? 'light' : 'dark');
            } catch (e) { /* приватный режим — тема продержится до перехода */ }
            return;
        }

        var toggle = event.target.closest('[data-toggle-sidebar]');
        if (toggle) {
            var wrap = document.querySelector('.damu-sec-wrap');
            var side = document.getElementById('section-sidebar');
            if (wrap && side) {
                side.classList.toggle('damu-collapsed');
                wrap.classList.toggle('damu-side-hidden');
                /* Запоминаем состояние в sessionStorage — при переходе
                   на другой раздел панель останется в том же виде */
                try {
                    var collapsed = side.classList.contains('damu-collapsed');
                    sessionStorage.setItem('damu-sidebar', collapsed ? 'collapsed' : 'expanded');
                } catch (e) { /* приватный режим */ }
            }
            return;
        }

        var tab = event.target.closest('[data-scroll-to]');
        if (!tab) {
            return;
        }
        var target = document.getElementById(tab.getAttribute('data-scroll-to'));
        if (!target) {
            return;
        }

        /* Порядок здесь важен и неочевиден:

           1. запоминаем цель и подсвечиваем её СРАЗУ — если цель в группе,
              ряд «пилюль» появляется ещё до прокрутки;
           2. только теперь мерим высоту полосы вкладок: она уже с рядом
              пилюль, то есть настоящая;
           3. едем на измеренное место.

           Раньше здесь стоял scrollIntoView с отступом из CSS
           (scroll-margin-top). Отступ был числом на все случаи, а полоса
           вкладок бывает и в один ряд, и в два — при нажатии на ГФ1
           прокрутка не доезжала, и заголовок секции оставался под вкладками
           (замечено пользователем 30.07.2026). */
        targetKey = tab.getAttribute('data-target-key');
        highlight();

        window.scrollTo({ top: scrollTargetFor(target), behavior: 'smooth' });

        /* Отпускаем цель, когда доехали. Точного события об окончании
           плавной прокрутки в старых браузерах нет, поэтому по таймеру;
           а если человек сам крутанул колесо — отпускаем сразу, чтобы
           подсветка снова шла за ним. */
        clearTimeout(releaseTimer);
        releaseTimer = setTimeout(function () {
            /* !! lastKey обнуляется вместе с targetKey. Без этого гистерезис
               (HYSTERESIS px допуска) после клика по вкладке удерживал
               ПРЕЖНИЙ ключ: секция-цель оказывалась в зоне допуска, и
               currentSectionKey() возвращал старый ключ. Результат — клик
               на «Отрасли» прокручивал ленту, но подсветка оставалась
               на «Динамике по годам» (замечено 10.08.2026). */
            lastKey = null;
            targetKey = null;
            schedule();
        }, 900);
    });

    window.addEventListener('wheel', function () {
        targetKey = null;
    }, { passive: true });

    /* Восстановление состояния боковой панели при переходе между разделами.
       Dash при навигации перерисовывает DOM — классы damu-collapsed и
       damu-side-hidden пропадают. Здесь мы применяем сохранённое
       в sessionStorage состояние к свежей разметке. */
    var sidebarRestored = null;  /* id элемента, которому уже применили */
    function restoreSidebar() {
        var side = document.getElementById('section-sidebar');
        if (!side || side === sidebarRestored) return;
        sidebarRestored = side;
        try {
            var state = sessionStorage.getItem('damu-sidebar');
            if (state === 'collapsed') {
                side.classList.add('damu-collapsed');
                var wrap = side.closest('.damu-sec-wrap');
                if (wrap) wrap.classList.add('damu-side-hidden');
            }
        } catch (e) { /* приватный режим */ }
    }

    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);

    /* Dash перерисовывает страницу без перезагрузки, поэтому одного запуска
       при загрузке мало: наблюдаем за появлением новых узлов. Следим только
       за childList — изменения атрибутов не отслеживаются намеренно, иначе
       highlight() будил бы сам себя, ведь он как раз меняет классы. */
    new MutationObserver(function () {
        schedule();
        restoreSidebar();
        bindPinning();
        /* Строки разреза перерисовывает сервер (сменили год, области,
           версию), и классы подсветки уходят вместе со старой разметкой.
           Возвращаем — иначе выбранная отрасль тихо гасла бы в одном
           разрезе из четырёх, и сравнение врало бы.

           Кольца, как у Plotly, тут не будет: мы меняем классы, а не
           перестраиваем разметку, и наблюдатель следит только за
           `childList`, но не за атрибутами. */
        applyRowPin();
    }).observe(document.body, {
        childList: true,
        subtree: true
    });

    /* ── Подсветка категории: почему здесь пусто ──

       Здесь жила подсветка через Plotly: клик по полосе или по надписи
       гасил остальные столбцы во всех диаграммах разреза. Снята 17.08.2026
       вместе с самими диаграммами — разрезы теперь рисуются строками-`div`
       (`cut_panel` в pages/section.py), и подсветка переехала ниже,
       в «Подсветка строки разреза», где занимает пятнадцать строк вместо
       ста восьмидесяти.

       `!!` Оставлять код было нельзя, и не из-за объёма. Именно он вешал
       вкладку: `plotly_afterplot` возвращал в `Plotly.restyle`, а `restyle`
       снова поднимал `plotly_afterplot` — кольцо. Против него пришлось
       завести два тормоза, обход двоичных массивов Plotly и приватное
       `_fullData`. Всё это стало недостижимым (виды-разрезы больше
       не строятся Plotly), но недостижимый код с такой историей — это
       заряженное ружьё на стене: рано или поздно кто-нибудь снимет
       с него условие и вернёт зависание. Разбор — CODE_GUIDE,
       «Третий заход».
    */


    /* ── Подсветка строки разреза (полосы-дивы) ──

       С 17.08.2026 разрезы на странице раздела рисует не Plotly, а обычные
       строки-`div` (`cut_panel` в pages/section.py). Здесь от этого остаётся
       ровно три дела: запомнить имя, повесить классы, снять.

       Сравните с тем, что для того же самого требовалось на Plotly: обход
       двоичных массивов, приватное `_fullData`, `Plotly.restyle` на каждую
       диаграмму, два тормоза против кольца «restyle → перерисовка → restyle»
       (оно вешало вкладку) и `captureevents` на надписях, работавший только
       у СЭЭ. Ничего из этого больше не нужно.

       Подсветка общая на всю секцию: имя ищется во ВСЕХ разрезах вкладки,
       чтобы «Обрабатывающая пром.» зажглась разом и в выпуске продукции,
       и в рабочих местах, и в налогах. Ради этого вопроса разрезы и стоят
       рядом. */
    var pinnedRow = null;

    function applyRowPin() {
        document.querySelectorAll('.damu-sec-block').forEach(function (block) {
            var rows = block.querySelectorAll('.damu-cut-row');
            if (!rows.length) return;
            var found = false;
            rows.forEach(function (row) {
                var mine = pinnedRow !== null
                    && row.getAttribute('data-cat') === pinnedRow;
                row.classList.toggle('damu-pinned', mine);
                if (mine) found = true;
            });
            /* !! Пометка на секции гасит непомеченные строки — но ставится,
               только если выбранное имя в этой секции ВООБЩЕ есть. Иначе
               разрез, где такой категории нет (у регионов нет «Обрабатывающей
               пром.»), погас бы целиком, и это читалось бы поломкой,
               а не «здесь этого нет». */
            block.classList.toggle('damu-has-pin', found);
        });
    }

    document.addEventListener('click', function (event) {
        var row = event.target.closest('.damu-cut-row');
        if (!row) return;
        var name = row.getAttribute('data-cat');
        pinnedRow = (pinnedRow === name) ? null : name;
        applyRowPin();
    });

    /* ── Примеры 5 и 6: разворот в раскладку главной ──
       Договор с Python: обёртка с классом .damu-ex6 и атрибутом data-mode
       ("compact" | "full"), внутри два слота .damu-ex6-compact
       и .damu-ex6-full. Здесь только переключение атрибута — всё
       движение делает CSS (блок «Пример 6» в custom.css).
       Сервер не трогаем намеренно: перерисованное дерево анимировать
       нечем, браузеру не с чем сравнивать прежнее состояние.

       !! И кнопка, и обёртка ищутся по КЛАССУ, а не по id (18.08.2026):
       кнопок на странице ДВЕ — «Развернуть» в шапке разбивки по программам
       и «Свернуть» в развёрнутой витрине, у каждой свой id. Обработчик,
       завязанный на одно имя, работал бы ровно на одной из них.

       !! Подписи кнопок здесь БОЛЬШЕ НЕ ПЕРЕПИСЫВАЮТСЯ (19.08.2026).
       Пока кнопка была одна, она меняла текст после каждого нажатия.
       Теперь у каждого состояния своя кнопка с постоянной подписью:
       перепиши мы её — «Развернуть» превратилась бы в «Свернуть» ровно
       в тот миг, когда её саму скрывают, и обратно уже не вернулась бы. */
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.damu-ex6-toggle');
        if (!btn) return;
        var wrap = document.querySelector('.damu-ex6');
        if (!wrap) return;
        var isFull = wrap.getAttribute('data-mode') === 'full';
        wrap.setAttribute('data-mode', isFull ? 'compact' : 'full');

        /* !! Карта строится сразу, но лежит в схлопнутом блоке нулевой
           высоты, а Plotly меряет место при первой отрисовке — без этого
           вызова она осталась бы полоской в ноль пикселей. Ждём конца
           перехода (0,55 с в custom.css) плюс запас. */
        if (!isFull && window.Plotly) {
            setTimeout(function () {
                wrap.querySelectorAll('.js-plotly-plot').forEach(function (plot) {
                    window.Plotly.Plots.resize(plot);
                });
            }, 620);
        }
    });

    /* ── Example 3: Global dynamics toggle ── */
    document.addEventListener('click', function (e) {
        var dynBtn = e.target.closest('#damu-dyn-toggle');
        if (dynBtn) {
            var card = dynBtn.closest('[style]');
            while (card && !card.querySelector('.damu-proj-dynamics')) {
                card = card.parentElement;
            }
            if (!card) return;
            card.classList.toggle('damu-dyn-open');
            var isOpen = card.classList.contains('damu-dyn-open');
            dynBtn.textContent = isOpen ? 'Скрыть динамику ▴' : 'Показать динамику ▾';
            return;
        }
        
        var yearBtn2026 = e.target.closest('#damu-btn-2026');
        var yearBtn2025 = e.target.closest('#damu-btn-2025');
        if (yearBtn2026 || yearBtn2025) {
            var is2025 = !!yearBtn2025;
            var btn26 = document.getElementById('damu-btn-2026');
            var btn25 = document.getElementById('damu-btn-2025');
            var rows26 = document.getElementById('damu-rows-2026');
            var rows25 = document.getElementById('damu-rows-2025');
            
            if (btn26 && btn25 && rows26 && rows25) {
                if (is2025) {
                    btn25.style.fontWeight = '700';
                    btn25.style.background = 'var(--damu-accent, #1f7a4d)';
                    btn25.style.color = 'var(--damu-on-accent, #fff)';

                    btn26.style.fontWeight = '500';
                    btn26.style.background = 'transparent';
                    btn26.style.color = 'var(--damu-muted)';

                    rows26.style.display = 'none';
                    rows25.style.display = 'block';
                } else {
                    btn26.style.fontWeight = '700';
                    btn26.style.background = 'var(--damu-accent, #1f7a4d)';
                    btn26.style.color = 'var(--damu-on-accent, #fff)';

                    btn25.style.fontWeight = '500';
                    btn25.style.background = 'transparent';
                    btn25.style.color = 'var(--damu-muted)';
                    
                    rows25.style.display = 'none';
                    rows26.style.display = 'block';
                }
            }
        }
    });

    /* ── Вкладка «Динамика по годам»: свёрнутый показ лет (08.08.2026,
       пока только у СЭЭ, pages/section.py — _years_toggle) ──

       Кнопка стоит внутри той же карточки, что её график: обработчик
       находит Plotly-график обычным обходом DOM (closest/querySelector),
       а не по id — тогда не нужно знать, как Dash сериализует id виджета
       в JSON-строку для pattern-matching компонентов.

       Сервер уже прислал ВСЕ года в фигуре (core/charts.py, _years_total).
       Кнопка ничего не запрашивает у сервера — только раздвигает видимое
       окно оси через Plotly.relayout, совсем как подсветка вкладок выше:
       без коллбэка на каждый клик.

       !! Ширину карточки кнопка НЕ меняет. Так было в первой версии
       (08.08.2026): графики стояли по двое в ряд, и кнопка заодно
       разворачивала свой на всю линию. Теперь каждый график и так во всю
       линию — своей подсекцией, — и от раскладочной части не осталось
       ничего, кнопка отвечает только за года. */
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-years-toggle]');
        if (!btn) {
            return;
        }
        var card = btn.closest('.card');
        var graph = card ? card.querySelector('.js-plotly-plot') : null;
        if (!graph || !window.Plotly) {
            return;
        }

        var open = btn.getAttribute('data-open') === '1';
        btn.setAttribute('data-open', open ? '0' : '1');
        btn.textContent = open ? 'Показать динамику ▾' : 'Скрыть ▴';

        /* Ось значений всегда возвращается к автомасштабу — и при
           раскрытии, и при укрытии. Кнопка отвечает за года, то есть
           за ОДНУ ось, но если вторая почему-то оказалась в приближении,
           «Показать динамику» обязана вернуть график к целому виду:
           иначе года встанут на место, а высота столбцов останется
           обрезанной, и человек так и будет смотреть на сломанное.
           (До 10.08.2026 в такое приближение можно было попасть случайной
           протяжкой мыши — теперь оно выключено в core/charts.py,
           но открытые вкладки со старой фигурой лечатся этой строкой.) */
        if (open) {
            var lo = Number(btn.getAttribute('data-range-lo'));
            var hi = Number(btn.getAttribute('data-range-hi'));
            Plotly.relayout(graph, {
                'xaxis.range': [lo, hi],
                'yaxis.autorange': true
            });
        } else {
            /* !! Именно `autorange: true`, а НЕ `range: null`. С null всё
               выглядит рабочим ровно один раз: первое раскрытие даёт полные
               15 лет, а каждое следующее — восемь ([-1, 6] вместо
               [-0.5, 14.5], воспроизведено в браузере 08.08.2026). Причина:
               явно заданный range выставляет `autorange: false`, и обнуление
               самого range автомасштаб обратно не включает — ось остаётся
               без границ и досчитывает их как попало. */
            Plotly.relayout(graph, {
                'xaxis.autorange': true,
                'yaxis.autorange': true
            });
        }
    });

    /* !! Выравнивание подписей оси Y по левому краю (СЭЭ) здесь БЫЛО
       и отсюда УБРАНО 11.08.2026 — не как правка стиля, а как починка
       производительности. Прежняя версия на каждое изменение DOM ГДЕ
       УГОДНО на странице (MutationObserver на document.body, subtree)
       заново перебирала все графики и звала `getBBox()` в цикле по
       каждой подписи каждого — а `getBBox()` заставляет браузер
       немедленно и синхронно пересчитать раскладку страницы. На
       четырёх больших графиках СЭЭ это были сотни таких пересчётов
       на каждый чих, отсюда и «графики грузятся по 5 секунд».

       Автор правки — не этот файл: её сделал Gemini через Antigravity
       по просьбе пользователя (переименовать один заголовок), но заодно
       добавил и это. Найдено сравнением с историей 11.08.2026.

       Тот же результат — подписи столбиком от одного края — теперь
       делает СЕРВЕР при постройке фигуры: core/charts.py,
       `_left_align_categories`. Там это `annotations` с обычным
       `xanchor="left"`, без единого обращения к DOM в браузере.
       Разбор — в CODE_GUIDE. */

    /* ── Какие секции ленты уже показывались ──────────────────────────
       Договор с Python: pages/section.py держит `dcc.Store` со списком
       ключей секций, для которых сервер СТРОИТ диаграммы. Пока ключа
       в списке нет — место под график пустует, и сервер на него не
       тратится. Эта функция дополняет список по мере прокрутки.

       Зачем. Раздел — одна длинная лента, и раньше сервер строил
       диаграммы ВСЕХ её разрезов сразу: на СЭЭ двенадцать штук за один
       запрос, 2,2 с только на них (замерено 12.08.2026). Видно при этом
       от силы две.

       !! Список только РАСТЁТ, и это главное в устройстве. Если бы он
       повторял «что на экране прямо сейчас», то при прокрутке вверх-вниз
       секции выпадали бы и возвращались, а каждое такое изменение —
       запрос к серверу и перестройка. Накопительный список меняется
       ровно столько раз, сколько на ленте секций, и ни разу больше.

       !! Здесь НЕТ обработчика прокрутки, хотя задача про прокрутку.
       Соседний highlight() ходит по DOM на каждое движение колеса, но он
       остаётся в браузере; а этот список — вход коллбэка, то есть каждое
       его изменение стоит запроса. Поэтому опрос редкий (интервал в
       section.py) и почти всегда заканчивается `no_update`: список
       перестаёт меняться, как только вся лента показана.

       Запас в один экран вперёд — чтобы диаграмма успела построиться
       ДО того, как человек до неё домотает, и он увидел готовую, а не
       пустое место. */
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.damu = {
        visibleSections: function (n_intervals, known) {
            var shown = (known || []).slice();
            var seen = {};
            shown.forEach(function (key) { seen[key] = true; });

            var ahead = window.innerHeight * 2;
            var added = false;
            var blocks = document.querySelectorAll('.damu-sec-block');
            blocks.forEach(function (block) {
                var key = block.getAttribute('data-key');
                if (!key || seen[key]) return;
                /* Секции ВЫШЕ окна тоже берём: их уже проматывали.
                   Отсекается только то, что глубоко внизу и ещё не скоро
                   понадобится. */
                if (block.getBoundingClientRect().top < ahead) {
                    shown.push(key);
                    seen[key] = true;
                    added = true;
                }
            });

            /* !! Сам таймер не гас никогда — тикал каждые 250 мс и после
               того, как лента полностью показана, и на пустой странице
               (например, если .damu-sec-block ещё не в DOM). Каждый тик —
               это коллбэк, а Dash на время любого коллбэка (даже
               клиентского и даже вернувшего no_update) красит заголовок
               вкладки в «Updating…»: отсюда бесконечное мигание заголовка,
               замеченное 18.08.2026. Как только все секции ленты показаны —
               выключаем интервал сами; `switch_tab` в pages/section.py
               включает его обратно при смене вкладки верхнего уровня,
               когда в ленте появляются свежие, ещё не показанные секции. */
            var allShown = blocks.length > 0 && shown.length >= blocks.length;

            /* Ничего нового — молчим. Вернуть тот же список значило бы
               разбудить серверный коллбэк впустую, четыре раза в секунду. */
            return [
                added ? shown : window.dash_clientside.no_update,
                allShown ? true : window.dash_clientside.no_update
            ];
        }
    };

    schedule();
    restoreSidebar();
}());
