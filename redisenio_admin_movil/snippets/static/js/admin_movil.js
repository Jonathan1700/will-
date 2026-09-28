/* Panel admin móvil — navegación por grupos, sub-pestañas y diálogos.
   Copiar a static/js/admin_movil.js y cargar al final del <body> con defer. */
(function () {
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // --- Barra inferior: muestra un grupo y oculta los demás ---
  function ir(grupo) {
    const existe = $$('[data-grupo]').some(g => g.dataset.grupo === grupo);
    if (!existe) grupo = 'resumen';
    $$('[data-grupo]').forEach(g => (g.hidden = g.dataset.grupo !== grupo));
    $$('.bnav [data-ir]').forEach(b => b.classList.toggle('activo', b.dataset.ir === grupo));
    document.body.dataset.grupo = grupo; // el CSS lo usa para ocultar filtro y mostrar el FAB
    history.replaceState(null, '', '#' + grupo);
    window.scrollTo(0, 0);
  }
  $$('.bnav [data-ir]').forEach(b => b.addEventListener('click', () => ir(b.dataset.ir)));

  // --- Sub-pestañas dentro de cada grupo ---
  $$('.subtabs').forEach(barra => {
    const grupo = barra.closest('[data-grupo]');
    $$('[data-sub-btn]', barra).forEach(btn =>
      btn.addEventListener('click', () => {
        $$('[data-sub]', grupo).forEach(p => (p.hidden = p.dataset.sub !== btn.dataset.subBtn));
        $$('[data-sub-btn]', barra).forEach(b => b.classList.toggle('activo', b === btn));
      })
    );
  });

  // --- Abrir <dialog> con cualquier botón [data-abrir="id-del-dialog"] ---
  $$('[data-abrir]').forEach(btn =>
    btn.addEventListener('click', () => {
      const d = document.getElementById(btn.dataset.abrir);
      if (d && d.showModal) d.showModal();
    })
  );
  $$('dialog [data-cerrar]').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));

  ir(location.hash.slice(1) || 'resumen');
})();
