// Presentation only. Required scope and authorization are checked by Django.
(() => {
  const kind = document.querySelector('[name="kind"]');
  if (!kind) return;
  const update = () => {
    for (const field of document.querySelectorAll('[data-repair-field]')) {
      const name = field.dataset.repairField;
      const needed = name === 'faculty' ? kind.value === 'faculty'
        : name === 'room' ? kind.value === 'room'
        : name === 'sections' ? kind.value === 'sections'
        : ['day', 'start', 'end'].includes(name) ? kind.value !== 'sections'
        : true;
      field.hidden = !needed;
    }
    const optional = document.querySelector('details');
    optional.hidden = kind.value !== 'faculty';
    // Disabled irrelevant fields cannot accidentally authorize replacements
    // after switching scenarios. Values remain available when switching back.
    for (const input of optional.querySelectorAll('input')) input.disabled = optional.hidden;
  };
  kind.addEventListener('change', update);
  update();
})();
