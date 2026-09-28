/* Panel admin movil: barra inferior de 5 items, sub-pestanas dentro de un grupo y
 * dialogos (<dialog>) genericos. No sabe nada de graficos ni de datos del dashboard:
 * si la pagina define window.onPanelMovilNav(grupo, sub), se llama cada vez que se
 * muestra un grupo/sub-pestana (por ejemplo para redibujar un grafico SVG que
 * necesita medir su contenedor ya visible).
 */
(() => {
    const raiz = document.querySelector('.panel-admin-movil');
    if (!raiz) return;

    const $$ = (s, r = raiz) => [...r.querySelectorAll(s)];

    function subInicial(grupo) {
        const grupoEl = raiz.querySelector('[data-grupo="' + grupo + '"]');
        const primero = grupoEl && grupoEl.querySelector('[data-sub-btn]');
        return primero ? primero.dataset.subBtn : null;
    }

    function subActiva(grupo) {
        const grupoEl = raiz.querySelector('[data-grupo="' + grupo + '"]');
        const activo = grupoEl && grupoEl.querySelector('[data-sub-btn].activo');
        return activo ? activo.dataset.subBtn : null;
    }

    function tabActual() {
        const grupo = raiz.dataset.grupo || 'resumen';
        const sub = subActiva(grupo);
        return sub ? grupo + ':' + sub : grupo;
    }

    function ir(grupo, sub) {
        const existe = $$('[data-grupo]').some(g => g.dataset.grupo === grupo);
        if (!existe) grupo = 'resumen';
        if (!sub) sub = subInicial(grupo);

        $$('[data-grupo]').forEach(g => (g.hidden = g.dataset.grupo !== grupo));
        $$('.bnav [data-ir]').forEach(b => b.classList.toggle('activo', b.dataset.ir === grupo));
        raiz.dataset.grupo = grupo;

        const grupoEl = raiz.querySelector('[data-grupo="' + grupo + '"]');
        if (grupoEl && sub) {
            $$('[data-sub]', grupoEl).forEach(p => (p.hidden = p.dataset.sub !== sub));
            $$('[data-sub-btn]', grupoEl).forEach(b => b.classList.toggle('activo', b.dataset.subBtn === sub));
        }

        const hash = sub ? grupo + ':' + sub : grupo;
        history.replaceState(null, '', '#' + hash);
        try { localStorage.setItem('admin-movil-tab', hash); } catch (e) {}
        window.scrollTo(0, 0);
        if (window.onPanelMovilNav) window.onPanelMovilNav(grupo, sub);
    }

    $$('.bnav [data-ir]').forEach(b => b.addEventListener('click', () => ir(b.dataset.ir)));

    $$('.subtabs').forEach(barra => {
        const grupo = barra.closest('[data-grupo]');
        $$('[data-sub-btn]', barra).forEach(btn =>
            btn.addEventListener('click', () => ir(grupo.dataset.grupo, btn.dataset.subBtn))
        );
    });

    // Abrir/cerrar cualquier <dialog> desde un boton [data-abrir="id-del-dialog"]
    document.querySelectorAll('[data-abrir]').forEach(btn =>
        btn.addEventListener('click', () => {
            const d = document.getElementById(btn.dataset.abrir);
            if (d && d.showModal) d.showModal();
        })
    );
    document.querySelectorAll('dialog [data-cerrar]').forEach(b =>
        b.addEventListener('click', () => b.closest('dialog').close())
    );

    // El filtro Dia/Semana/Mes y la navegacion de fecha recargan la pagina entera
    // (son enlaces/formularios GET normales): se les agrega la pestana actual como
    // hash para volver al mismo grupo/sub-pestana despues de recargar.
    $$('.filtro-periodo a, .filtro-periodo .nav-fecha').forEach(el => {
        if (el.tagName === 'FORM') {
            el.addEventListener('submit', () => { el.action = location.pathname + '#' + tabActual(); });
        } else {
            el.addEventListener('click', () => { el.href = el.href.split('#')[0] + '#' + tabActual(); });
        }
    });

    let inicial = location.hash.slice(1);
    if (!inicial) {
        try { inicial = localStorage.getItem('admin-movil-tab') || ''; } catch (e) { inicial = ''; }
    }
    const [g0, s0] = inicial.split(':');
    ir(g0 || 'resumen', s0);
})();
