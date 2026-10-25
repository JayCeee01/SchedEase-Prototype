/* Advisory totals; the existing server-side meeting validation remains authoritative. */
(() => {
  const output = document.querySelector('[data-meeting-hours]');
  if (!output) return;
  const form = output.closest('form');
  const requirements = JSON.parse(document.getElementById('meeting-requirements').textContent);
  const hours = minutes => `${Number((minutes / 60).toFixed(2))}h`;
  const update = () => {
    const required = requirements[form.elements.namedItem('subject').value];
    if (!required) { output.textContent = 'Choose a course to see its required hours.'; return; }
    const allocated = {LECTURE: 0, LABORATORY: 0};
    let invalid = false, defaults = false;
    form.querySelectorAll('[data-meeting-list] [data-meeting-form]').forEach(panel => {
      const field = name => panel.querySelector(`[name$="-${name}"]`);
      if (field('DELETE')?.checked) return;
      const component = field('component').value;
      const raw = field('duration_minutes').value;
      const minutes = Number(raw);
      if (!(component in allocated) || raw === '' || !Number.isInteger(minutes) || minutes < 0) {
        invalid = true; return;
      }
      allocated[component] += minutes || required[component];
      defaults ||= minutes === 0;
    });
    output.replaceChildren();
    Object.entries({LECTURE: 'Lecture', LABORATORY: 'Laboratory'}).forEach(([component, label]) => {
      if (!required[component] && !allocated[component]) return;
      const remaining = required[component] - allocated[component];
      const row = document.createElement('section');
      row.className = 'meeting-hours-card';
      row.dataset.component = component;
      const heading = document.createElement('strong');
      heading.textContent = label;
      const metrics = document.createElement('dl');
      [['Required', required[component]], ['Allocated', allocated[component]], ['Remaining', Math.max(0, remaining)]].forEach(([name, minutes]) => {
        const group = document.createElement('div');
        const term = document.createElement('dt'); term.textContent = name;
        const value = document.createElement('dd'); value.textContent = hours(minutes); value.title = `${minutes} minutes`;
        group.append(term, value); metrics.append(group);
      });
      const status = document.createElement('small');
      status.className = 'assignment-guidance-status';
      status.dataset.state = remaining < 0 ? 'unqualified' : remaining > 0 || invalid ? 'override' : 'qualified';
      status.textContent = remaining < 0 ? `Overallocated by ${hours(-remaining)}` : remaining > 0 ? 'Hours remaining' : invalid ? 'Check incomplete meetings' : 'Complete';
      row.append(heading, metrics, status);
      output.append(row);
    });
    if (invalid || defaults || !output.children.length) {
      const note = document.createElement('p');
      note.className = 'meeting-hours-note subtle';
      note.textContent = invalid ? 'Complete each meeting with Lecture or Laboratory and a whole-number duration to check all allocations.' :
        defaults ? 'Totals include the course default for meetings with a duration of 0.' : 'This course has no required lecture or laboratory hours.';
      output.append(note);
    }
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  update();
})();
