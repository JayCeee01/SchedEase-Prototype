(() => {
  const scope = document.getElementById('workload-scope');
  if (!scope) return;
  const term = scope.querySelector('[name=term]');
  const department = scope.querySelector('[name=department]');
  const pickers = [...scope.querySelectorAll('.scope-picker')];
  function invalidateScope() {
    const output = document.getElementById('workload-output');
    output.hidden = true;
    output.querySelectorAll('button[type=submit],button[name=action]').forEach(b => b.disabled = true);
    document.getElementById('scope-notice').textContent = 'Scope changed. Click Analyze Workload to refresh eligibility and proposals.';
  }
  function updatePicker(picker) {
    const search = picker.querySelector('[data-picker-search]').value.toLowerCase().trim();
    const inputs = [...picker.querySelectorAll('input[type=checkbox]')];
    const selected = inputs.filter(c => c.checked);
    let invalid = 0, locked = 0, shown = 0;
    for (const box of inputs) {
      const label = box.closest('label');
      const valid = !!department.value && box.dataset.department === department.value && (!box.dataset.term || box.dataset.term === term.value);
      box.setAttribute('aria-invalid', box.checked && !valid ? 'true' : 'false');
      if (box.checked && !valid) invalid++;
      if (box.checked && box.dataset.locked === 'true' && box.name === 'assignments') locked++;
      const visible = (valid || box.checked) && (label.textContent.toLowerCase().includes(search) || box.checked);
      label.parentElement.hidden = !visible;
      if (visible) shown++;
    }
    picker.querySelector('[data-picker-count]').textContent = `${selected.length} selected · ${shown} shown`;
    const summary = picker.querySelector('[data-picker-summary]');
    summary.replaceChildren();
    for (const box of selected) {
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'button';
      const text = box.closest('label').textContent.trim();
      remove.textContent = `Remove: ${text}`;
      remove.addEventListener('click', () => { box.checked = false; box.dispatchEvent(new Event('change', {bubbles:true})); picker.querySelector('[data-picker-search]').focus(); });
      summary.append(remove);
    }
    const otherName = {assignments:'exclude_assignments',faculty:'exclude_faculty',exclude_assignments:'assignments',exclude_faculty:'faculty'}[picker.dataset.picker];
    const contradictory = selected.some(box => [...scope.querySelectorAll(`input[name="${otherName}"]:checked`)].some(other => other.value === box.value));
    picker.querySelector('[data-picker-feedback]').textContent = invalid ? `${invalid} selections are outside this term or department. Remove them before analyzing.` : contradictory ? 'An item is both included and excluded. Remove one selection.' : locked ? `${locked} selected assignments are locked and will be excluded from balancing.` : 'Candidate eligibility will be checked during analysis.';
  }
  pickers.forEach(picker => {
    picker.querySelector('[data-picker-search]').addEventListener('input', () => updatePicker(picker));
    updatePicker(picker);
  });
  scope.addEventListener('change', event => {
    if (event.target.matches('select,input[type=checkbox]')) {
      pickers.forEach(updatePicker);
      invalidateScope();
    }
  });
  if (scope.querySelector('.errorlist')) document.getElementById('workload-advanced').open = true;
  const batch = document.getElementById('batch-selection');
  batch?.addEventListener('change', event => {
    if (event.target.name !== 'selected') return;
    document.querySelectorAll('[data-batch-metrics]').forEach(e => e.hidden = true);
    batch.querySelector('[value=approve]').disabled = true;
    batch.querySelector('[name=confirm]').checked = false;
    document.getElementById('selection-notice').textContent = 'Selection changed. Preview the combined impact before approving.';
  });
  document.querySelectorAll('#workload-scope, #workload-output form').forEach(form => {
    form.addEventListener('submit', event => {
      if (form.dataset.submitting) { event.preventDefault(); return; }
      form.dataset.submitting = 'yes'; form.setAttribute('aria-busy', 'true');
      if (event.submitter?.name) {
        const action = document.createElement('input'); action.type = 'hidden'; action.name = event.submitter.name; action.value = event.submitter.value; form.append(action);
      }
      form.querySelectorAll('button[name=action]').forEach(b => b.disabled = true);
      const notice = document.createElement('p'); notice.setAttribute('role','status'); notice.textContent = 'Working… Please wait.'; form.append(notice);
    });
  });
  const heading = document.getElementById('preview-heading') || document.getElementById('eligibility-heading');
  if (heading) heading.focus({preventScroll:false});
})();
