/* Мелкая логика страницы раздела: прокрутка к секции, подсветка вкладки
   при прокрутке и сворачивание списка разделов.

   Почему это здесь, а не коллбэком Dash. Всё три вещи — про вид, а не
   про данные, и происходят десятками раз в секунду (движение колеса мыши).
   Коллбэк на каждое такое движение слал бы запрос на сервер, и страница
   тормозила бы на ровном месте. Здесь же браузер справляется сам,
   не выходя наружу.

   Dash подхватывает всё из assets/ сам — подключать файл в коде не нужно.

   Разметку рисует pages/section.py, договор между ними — data-атрибуты:

     data-scroll-to     на вкладке  — id секции, к которой прокрутить
     data-members       на вкладке  — ключи секций, которые она закрывает
                                      (у группы их несколько)
     data-tab-key       на вкладке  — её собственный ключ
     data-key           на секции   — ключ этой секции
     data-group-row     на ряду     — ключ группы, которой принадлежит ряд
                                      «пилюль»; ряд виден только когда
                                      выбрана сама группа
     data-sub-key       на пилюле   — ключ секции этой пилюли
     data-toggle-sidebar на кнопке ☰

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

    function highlight() {
        var key = targetKey || currentSectionKey();
        if (key === null) {
            return;                 // мы не на странице раздела
        }

        var activeTab = null;
        document.querySelectorAll('.damu-sec-tab').forEach(function (tab) {
            var members = (tab.getAttribute('data-members') || '').split(',');
            var isActive = members.indexOf(key) !== -1;
            tab.classList.toggle('active', isActive);
            if (isActive) {
                activeTab = tab.getAttribute('data-tab-key');
            }
        });

        /* Ряд «пилюль» показываем только у выбранной группы. Пустая строка
           в style.display возвращает элемент к тому, что сказано в CSS
           (display: flex), а не делает его block — это важно, иначе
           пилюли встали бы в столбик. */
        document.querySelectorAll('[data-group-row]').forEach(function (row) {
            var mine = row.getAttribute('data-group-row') === activeTab;
            row.style.display = mine ? '' : 'none';
        });

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

        var top = window.scrollY + target.getBoundingClientRect().top
                  - stickyHeight() - TAB_GAP;
        window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });

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
    }).observe(document.body, {
        childList: true,
        subtree: true
    });

    /* ── Example 6: разворот примера 5 в раскладку главной ──
       Договор с Python: обёртка #damu-ex6 с атрибутом data-mode
       ("compact" | "full"), внутри два слота .damu-ex6-compact
       и .damu-ex6-full. Здесь только переключение атрибута — всё
       движение делает CSS (блок «Пример 6» в custom.css).
       Сервер не трогаем намеренно: перерисованное дерево анимировать
       нечем, браузеру не с чем сравнивать прежнее состояние. */
    document.addEventListener('click', function (e) {
        var ex6Btn = e.target.closest('#damu-ex6-toggle');
        if (!ex6Btn) return;
        var ex6 = document.getElementById('damu-ex6');
        if (!ex6) return;
        var isFull = ex6.getAttribute('data-mode') === 'full';
        ex6.setAttribute('data-mode', isFull ? 'compact' : 'full');
        ex6Btn.textContent = isFull ? 'Развернуть как на главной ▾' : 'Свернуть ▴';

        /* !! Карта строится сразу, но лежит в схлопнутом блоке нулевой
           высоты, а Plotly меряет место при первой отрисовке — без этого
           вызова она осталась бы полоской в ноль пикселей. Ждём конца
           перехода (0,55 с в custom.css) плюс запас. */
        if (!isFull && window.Plotly) {
            setTimeout(function () {
                ex6.querySelectorAll('.js-plotly-plot').forEach(function (plot) {
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

    schedule();
    restoreSidebar();
}());
