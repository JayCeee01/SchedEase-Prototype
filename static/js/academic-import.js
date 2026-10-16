(() => {
  document.querySelectorAll('[data-import-form]').forEach((form) => {
    let submitting = false;
    const reset = () => {
      submitting = false;
      form.removeAttribute('aria-busy');
      form.querySelector('[data-import-progress]').hidden = true;
      form.querySelectorAll('button[type="submit"]').forEach((button) => { button.disabled = false; });
    };
    window.addEventListener('pageshow', reset);
    form.addEventListener('submit', (event) => {
      if (submitting) { event.preventDefault(); return; }
      submitting = true;
      form.setAttribute('aria-busy', 'true');
      form.querySelector('[data-import-progress]').hidden = false;
      form.querySelectorAll('button[type="submit"]').forEach((button) => { button.disabled = true; });
    });
  });
  const input = document.querySelector('[data-import-file]');
  if (input) {
    const zone = document.querySelector('[data-dropzone]');
    const selected = document.querySelector('[data-selected-file]');
    const error = document.querySelector('[data-file-error]');
    document.querySelector('.import-workspace').classList.add('import-js');
    const show = () => {
      const file = input.files[0];
      error.textContent = '';
      input.setCustomValidity('');
      selected.hidden = !file;
      if (!file) return;
      document.querySelector('[data-file-name]').textContent = file.name;
      document.querySelector('[data-file-size]').textContent = file.size < 1048576 ? `${(file.size / 1024).toFixed(1)} KB` : `${(file.size / 1048576).toFixed(1)} MB`;
      if (!/\.(csv|xlsx)$/i.test(file.name)) error.textContent = 'Choose a CSV or Excel (.xlsx) file.';
      else if (file.size > 5 * 1024 * 1024) error.textContent = 'Choose a file of 5 MB or less.';
      input.setCustomValidity(error.textContent);
    };
    input.addEventListener('change', show);
    document.querySelector('[data-remove-file]').addEventListener('click', () => { input.value = ''; show(); input.focus(); });
    ['dragenter', 'dragover'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add('is-dragging'); }));
    zone.addEventListener('dragleave', () => zone.classList.remove('is-dragging'));
    zone.addEventListener('drop', (event) => {
      event.preventDefault(); zone.classList.remove('is-dragging');
      if (event.dataTransfer.files.length !== 1) { error.textContent = 'Drop one spreadsheet at a time.'; return; }
      try { input.files = event.dataTransfer.files; input.dispatchEvent(new Event('change', {bubbles: true})); }
      catch (_) { error.textContent = 'Please use Browse Files to choose your spreadsheet.'; }
    });
    show();
  }
  const search = document.querySelector('[data-guide-search]');
  const category = document.querySelector('[data-guide-category]');
  if (search && category) {
    const filter = () => {
      let visible = 0;
      const text = search.value.trim().toLowerCase();
      document.querySelectorAll('[data-guide-row]').forEach((row) => {
        row.hidden = !(row.textContent.toLowerCase().includes(text) && (!category.value || row.dataset.category === category.value));
        if (!row.hidden) visible += 1;
      });
      document.querySelector('[data-guide-empty]').hidden = visible > 0;
    };
    search.addEventListener('input', filter);
    category.addEventListener('change', filter);
  }
})();
