// Presentation only. Required scope and authorization are checked by Django.
(() => {
  for (const form of document.querySelectorAll('[data-repair-form]')) {
    const buttons = [...form.querySelectorAll('button')].map(button => [button, button.disabled]);
    window.addEventListener('pageshow', () => {
      delete form.dataset.submitting;
      form.removeAttribute('aria-busy');
      for (const [button, disabled] of buttons) {
        button.disabled = disabled;
        button.classList.remove('loading');
      }
      form.querySelectorAll('[data-repair-transient]').forEach(node => node.remove());
    });
    form.addEventListener('submit', event => {
      if (form.dataset.submitting) { event.preventDefault(); return; }
      form.dataset.submitting = 'yes';
      form.setAttribute('aria-busy', 'true');
      if (event.submitter?.name) {
        const action = document.createElement('input');
        action.type = 'hidden'; action.name = event.submitter.name;
        action.dataset.repairTransient = '';
        action.value = event.submitter.value; form.append(action);
      }
      for (const button of form.querySelectorAll('button')) button.disabled = true;
      const notice = document.createElement('p');
      notice.dataset.repairTransient = '';
      notice.setAttribute('role', 'status'); notice.textContent = 'Working… Please wait.';
      form.append(notice);
    });
  }
  const kind = document.querySelector('[name="kind"]');
  if (!kind) return;
  const update = () => {
    for (const field of document.querySelectorAll('[data-repair-field]')) {
      const name = field.dataset.repairField;
      const needed = name === 'faculty' ? kind.value === 'faculty'
        : name === 'room' ? kind.value === 'room'
        : name === 'sections' ? kind.value === 'sections'
        : ['days', 'start', 'end'].includes(name) ? kind.value !== 'sections'
        : true;
      field.hidden = !needed;
    }
    const optional = document.querySelector('#repair-replacements');
    optional.hidden = kind.value !== 'faculty';
    // Disabled irrelevant fields cannot accidentally authorize replacements
    // after switching scenarios. Values remain available when switching back.
    for (const input of optional.querySelectorAll('input')) input.disabled = optional.hidden;
  };
  kind.addEventListener('change', update);
  update();
})();
