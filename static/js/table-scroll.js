/* Each overflowing table owns a native, sticky horizontal-scroll footer. */
(() => {
  const selector = '.table-wrap, .import-scroll';
  const records = new Map();
  let frame = 0, running = false;
  const resize = new ResizeObserver(schedule);
  const mutations = new MutationObserver(changes => {
    if (changes.every(change => change.target.closest?.('.table-scroll-proxy'))) return;
    schedule();
  });
  function schedule() {
    if (running && !frame) frame = requestAnimationFrame(update);
  }
  function create(wrapper) {
    const container = document.createElement('div');
    container.className = 'table-scroll-frame';
    wrapper.before(container);
    container.appendChild(wrapper);
    const bar = document.createElement('div');
    bar.className = 'table-scroll-proxy';
    bar.hidden = true;
    bar.tabIndex = 0;
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', `Horizontal scrolling: ${wrapper.getAttribute('aria-label') || wrapper.querySelector('caption')?.textContent.trim() || 'data table'}`);
    const spacer = bar.appendChild(document.createElement('div'));
    container.appendChild(bar);
    const fromTable = () => {
      if (Math.abs(bar.scrollLeft - wrapper.scrollLeft) > 1) bar.scrollLeft = wrapper.scrollLeft;
    };
    const fromBar = () => {
      if (Math.abs(wrapper.scrollLeft - bar.scrollLeft) > 1) wrapper.scrollLeft = bar.scrollLeft;
    };
    wrapper.addEventListener('scroll', fromTable, {passive: true});
    bar.addEventListener('scroll', fromBar, {passive: true});
    const record = {container, bar, spacer, fromTable, fromBar, table: wrapper.querySelector('table'), range: ''};
    resize.observe(wrapper); resize.observe(record.table);
    records.set(wrapper, record);
    return record;
  }
  function remove(wrapper, record) {
    wrapper.removeEventListener('scroll', record.fromTable);
    record.bar.removeEventListener('scroll', record.fromBar);
    resize.unobserve(wrapper); resize.unobserve(record.table);
    wrapper.classList.remove('table-scroll-enhanced');
    if (wrapper.parentElement === record.container) record.container.before(wrapper);
    record.container.remove();
    records.delete(wrapper);
  }
  function update() {
    frame = 0;
    const found = new Set([...document.querySelectorAll(selector)].filter(wrapper => {
      const table = wrapper.querySelector('table');
      return table && !table.matches('.room-schedule-grid, .timetable-grid') && table.closest(selector) === wrapper;
    }));
    for (const [wrapper, record] of records) if (!found.has(wrapper)) remove(wrapper, record);
    for (const wrapper of found) {
      const record = records.get(wrapper) || create(wrapper);
      const table = wrapper.querySelector('table');
      if (record.table !== table) { resize.unobserve(record.table); resize.observe(table); record.table = table; }
      // Independently vertically scrolling panes already have reachable native bars.
      const overflow = wrapper.clientWidth > 0 && wrapper.scrollWidth > wrapper.clientWidth + 1 && wrapper.scrollHeight <= wrapper.clientHeight + 1;
      if (record.bar.hidden === overflow) record.bar.hidden = !overflow;
      if (wrapper.classList.contains('table-scroll-enhanced') !== overflow) wrapper.classList.toggle('table-scroll-enhanced', overflow);
      if (!overflow) { record.range = ''; continue; }
      const width = `${wrapper.offsetWidth}px`;
      if (record.bar.style.width !== width) record.bar.style.width = width;
      const range = `${wrapper.clientWidth}/${wrapper.scrollWidth}/${record.bar.clientWidth}`;
      if (range !== record.range) {
        record.spacer.style.width = `${record.bar.clientWidth + wrapper.scrollWidth - wrapper.clientWidth}px`;
        record.range = range;
        record.fromTable();
      }
    }
  }
  function start() {
    if (running) return;
    running = true;
    mutations.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'class', 'style', 'open']});
    for (const [wrapper, record] of records) { resize.observe(wrapper); resize.observe(record.table); }
    schedule();
  }
  function stop() {
    running = false; cancelAnimationFrame(frame); frame = 0;
    resize.disconnect(); mutations.disconnect();
  }
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', start);
  start();
})();
