/* Applies proposals to the existing formset only; Save remains authoritative. */
(() => {
  const controls = document.querySelector('[data-arrangement-controls]');
  if (!controls) return;
  const form = controls.closest('form');
  const suggestions = JSON.parse(document.getElementById('arrangement-suggestions').textContent);
  const requirements = JSON.parse(document.getElementById('meeting-requirements').textContent);
  const list = form.querySelector('[data-meeting-list]');
  const template = form.querySelector('[data-empty-meeting]');
  const total = form.elements.namedItem('meetings-TOTAL_FORMS');
  const field = (panel, name) => panel.querySelector(`[name$="-${name}"]`);
  const panels = () => [...list.querySelectorAll('[data-meeting-form]')];
  const widgets = [];
  for (const [component, title] of [['LECTURE', 'Lecture'], ['LABORATORY', 'Laboratory']]) {
    const card = document.createElement('section'); card.className = 'meeting-hours-card arrangement-card';
    const label = document.createElement('label'); label.textContent = `${title} Arrangement`;
    const select = document.createElement('select'); select.id = `arrangement-${component}`; label.htmlFor = select.id;
    const preview = document.createElement('p'); preview.className = 'helptext'; preview.setAttribute('aria-live', 'polite'); preview.id = `arrangement-preview-${component}`; select.setAttribute('aria-describedby', preview.id);
    const roomLabel = document.createElement('label'); roomLabel.textContent = 'Room type for new meetings';
    const room = template.content.querySelector('[name$="-required_room_type_override"]').cloneNode(true);
    room.removeAttribute('name'); room.id = `arrangement-room-${component}`; roomLabel.htmlFor = room.id;
    room.options[0].textContent = 'Choose if adding new meetings';
    // Never create a laboratory meeting with a lecture-room requirement.
    if (component === 'LABORATORY') [...room.options].filter(o => o.value === 'LECTURE').forEach(o => o.remove());
    if (component === 'LECTURE') [...room.options].filter(o => o.value && o.value !== 'LECTURE').forEach(o => o.remove());
    const apply = document.createElement('button'); apply.type = 'button'; apply.className = 'button primary'; apply.textContent = 'Apply Arrangement';
    const notice = document.createElement('p'); notice.className = 'helptext'; notice.setAttribute('role', 'status');
    const updateRoom = () => {
      const values = select.value ? JSON.parse(select.value) : [];
      const count = panels().filter(p => !field(p, 'DELETE').checked && field(p, 'component').value === component).length;
      room.hidden = roomLabel.hidden = values.length <= count;
    };
    form.addEventListener('input', updateRoom);
    form.addEventListener('change', updateRoom);
    const describe = () => {
      const values = select.value ? JSON.parse(select.value) : [];
      preview.textContent = values.length ? `${values.join(' + ')} min = ${values.reduce((a, b) => a + b, 0)} min total` : !form.elements.subject.value ? 'Select a course to see suggestions.' : select.disabled ? 'No suggestions for this session type. Configure meetings manually.' : 'Keep your current meetings.';
      updateRoom();
      apply.disabled = !values.length;
    };
    select.addEventListener('change', () => { notice.textContent = ''; notice.classList.remove('arrangement-warning'); describe(); });
    apply.addEventListener('click', () => {
      if (!select.value) return;
      const durations = JSON.parse(select.value);
      const existing = panels().filter(p => !field(p, 'DELETE').checked && field(p, 'component').value === component);
      const unused = [...existing];
      const plan = durations.map(minutes => {
        const index = unused.findIndex(p => (Number(field(p, 'duration_minutes').value) || requirements[form.elements.subject.value][component]) === minutes);
        return {minutes, panel: index < 0 ? null : unused.splice(index, 1)[0], unchanged: index >= 0};
      });
      plan.filter(item => !item.panel).forEach(item => { item.panel = unused.shift() || null; });
      const added = plan.filter(item => !item.panel).length;
      if (added && !room.value) { notice.classList.add('arrangement-warning'); notice.textContent = 'Choose a room type for the new meetings.'; room.focus(); return; }
      const maximum = Number(form.elements.namedItem('meetings-MAX_NUM_FORMS').value) || 1000;
      if (Number(total.value) + added > maximum) { notice.textContent = 'The meeting form limit has been reached. Save or reload before adding more.'; return; }
      if (existing.length && !window.confirm('Apply this arrangement? Matching meetings keep their identities and settings. Other meetings may change duration or be removed, discarding their meeting-specific settings. The other session type stays unchanged.')) return;
      let number = Math.max(0, ...panels().map(p => Number(field(p, 'meeting_index').value) || 0));
      unused.forEach(p => { field(p, 'DELETE').checked = true; });
      plan.forEach(item => {
        if (!item.panel) {
          const index = Number(total.value);
          list.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__prefix__', String(index)).replaceAll('__number__', String(index + 1)));
          total.value = String(index + 1);
          item.panel = panels().at(-1);
          field(item.panel, 'meeting_index').value = String(++number);
          field(item.panel, 'component').value = component;
          field(item.panel, 'required_room_type_override').value = room.value;
        }
        if (!item.unchanged) field(item.panel, 'duration_minutes').value = String(item.minutes);
      });
      form.dispatchEvent(new Event('meetings:refresh'));
      form.dispatchEvent(new Event('change', {bubbles: true}));
      notice.classList.remove('arrangement-warning'); notice.textContent = 'Applied. Review the meetings, then save.';
    });
    card.append(label, select, preview, roomLabel, room, apply, notice); controls.append(card);
    widgets.push({component, select, describe, notice, room});
  }
  const refresh = () => widgets.forEach(({component, select, describe, notice, room}) => {
    const options = suggestions[form.elements.subject.value]?.[component] || [];
    select.replaceChildren(new Option('Custom', ''));
    options.forEach(values => select.add(new Option(`${values.length} x ${values[0]} minutes`, JSON.stringify(values))));
    select.disabled = !options.length; room.value = ''; notice.textContent = ''; notice.classList.remove('arrangement-warning');
    describe();
  });
  form.elements.subject.addEventListener('change', refresh);
  form.elements.term.addEventListener('change', refresh);
  controls.hidden = false;
  refresh();
})();
