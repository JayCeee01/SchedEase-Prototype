/* Advisory labels only: never select a faculty member or change form values. */
(() => {
  const panel = document.querySelector('[data-faculty-suggestions]');
  if (!panel) return;
  const form = panel.closest('form');
  const faculty = form.elements.namedItem('faculty');
  const subject = form.elements.namedItem('subject');
  const term = form.elements.namedItem('term');
  const feedback = panel.querySelector('[data-faculty-feedback]');
  const original = [...faculty.options].map(option => ({option, text: option.textContent}));
  const labels = {qualified: 'Meets credential requirements', override: 'Override for saved meetings only', unqualified: 'Credential requirements not met'};
  const rank = {qualified: 0, override: 1, unqualified: 2};
  let sequence = 0, controller, results;
  faculty.setAttribute('aria-describedby', [faculty.getAttribute('aria-describedby'), 'faculty-credential-guidance'].filter(Boolean).join(' '));
  const restore = () => {
    const selected = faculty.value;
    original.forEach(({option, text}) => { option.textContent = text; faculty.append(option); });
    faculty.value = selected;
  };
  const describe = () => {
    if (!results) return;
    const count = results.filter(row => row.status === 'qualified').length;
    const selected = results.find(row => String(row.id) === faculty.value);
    feedback.replaceChildren();
    const status = document.createElement('strong');
    status.className = 'assignment-guidance-status';
    status.dataset.state = selected?.status || 'neutral';
    const titles = {qualified: 'Qualified', unqualified: 'Not qualified: override required', override: 'Approved override (saved meetings)'};
    status.textContent = selected ? titles[selected.status] : 'Select a faculty member';
    const total = document.createElement('small');
    total.className = 'subtle';
    total.textContent = `${count} eligible faculty ${count === 1 ? 'member' : 'members'}`;
    feedback.append(status, total);
    const reasons = selected?.status === 'unqualified' ? (selected.reasons?.length ? selected.reasons : [`Check credentials and validity dates for: ${selected.missing.join(', ')}.`]) :
      selected?.status === 'override' ? ['New meetings need their own approval.'] : [];
    if (reasons.length) {
      const list = document.createElement('ul');
      list.className = 'credential-reasons';
      reasons.forEach(reason => { const item = document.createElement('li'); item.textContent = reason; list.append(item); });
      feedback.append(list);
    }
  };
  const refresh = async () => {
    const current = ++sequence;
    controller?.abort();
    results = null;
    restore();
    if (!subject.value || !term.value) {
      feedback.textContent = 'Choose a course and academic term to check credentials.';
      return;
    }
    feedback.textContent = 'Checking credential requirements...';
    controller = new AbortController();
    try {
      const url = new URL(panel.dataset.url, location.href);
      url.searchParams.set('subject', subject.value);
      url.searchParams.set('term', term.value);
      if (panel.dataset.assignment) url.searchParams.set('assignment', panel.dataset.assignment);
      const response = await fetch(url, {signal: controller.signal, credentials: 'same-origin', cache: 'no-store', headers: {Accept: 'application/json'}});
      if (!response.ok) throw new Error('Unavailable');
      const data = await response.json();
      if (current !== sequence) return;
      results = data.faculty;
      const byId = new Map(results.map(row => [String(row.id), row]));
      const selected = faculty.value;
      [...original].sort((a, b) => (a.option.value ? rank[byId.get(a.option.value)?.status] ?? 3 : -1) - (b.option.value ? rank[byId.get(b.option.value)?.status] ?? 3 : -1)).forEach(({option, text}) => {
        const row = byId.get(option.value);
        option.textContent = row ? `${text} \u2014 ${labels[row.status]}` : text;
        faculty.append(option);
      });
      faculty.value = selected;
      describe();
    } catch (error) {
      if (current !== sequence || error.name === 'AbortError') return;
      results = null;
      restore();
      feedback.textContent = 'Credential guidance could not be loaded. You can still select faculty; credentials will be checked when you save.';
    }
  };
  subject.addEventListener('change', refresh);
  term.addEventListener('change', refresh);
  faculty.addEventListener('change', describe);
  refresh();
})();
