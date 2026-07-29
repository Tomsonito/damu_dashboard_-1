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

    /* Насколько ниже верха окна проходит «линия чтения». Секция считается
       текущей, если её заголовок уже выше этой линии. Число примерно равно
       высоте липких вкладок — иначе подсветка переключалась бы на секцию,
       которую вкладки как раз закрывают собой. */
    var READING_LINE = 150;

    function currentSectionKey() {
        var blocks = document.querySelectorAll('.damu-sec-block');
        if (!blocks.length) {
            return null;
        }
        /* Считаем от края ОКНА (getBoundingClientRect), а не от начала
           документа: у секций есть позиционированный предок, и offsetTop
           у них отсчитывается от него, а не от страницы — сравнение
           с прокруткой окна давало бы промах на высоту шапки. */
        var key = blocks[0].getAttribute('data-key');
        blocks.forEach(function (block) {
            if (block.getBoundingClientRect().top <= READING_LINE) {
                key = block.getAttribute('data-key');
            }
        });
        return key;
    }

    function highlight() {
        var key = currentSectionKey();
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
            highlight();
        });
    }

    document.addEventListener('click', function (event) {
        var toggle = event.target.closest('[data-toggle-sidebar]');
        if (toggle) {
            var wrap = document.querySelector('.damu-sec-wrap');
            var side = document.getElementById('section-sidebar');
            if (wrap && side) {
                side.classList.toggle('damu-collapsed');
                wrap.classList.toggle('damu-side-hidden');
            }
            return;
        }

        var tab = event.target.closest('[data-scroll-to]');
        if (!tab) {
            return;
        }
        var target = document.getElementById(tab.getAttribute('data-scroll-to'));
        if (target) {
            /* Отступ под липкие вкладки браузер берёт из CSS-свойства
               scroll-margin-top у самой секции — вычитать его руками
               не нужно. */
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });

    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);

    /* Dash перерисовывает страницу без перезагрузки, поэтому одного запуска
       при загрузке мало: наблюдаем за появлением новых узлов. Следим только
       за childList — изменения атрибутов не отслеживаются намеренно, иначе
       highlight() будил бы сам себя, ведь он как раз меняет классы. */
    new MutationObserver(schedule).observe(document.body, {
        childList: true,
        subtree: true
    });

    schedule();
}());
