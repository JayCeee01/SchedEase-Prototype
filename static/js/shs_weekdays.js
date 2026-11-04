// SHS admin date selection only. Server-side policy remains authoritative.
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('id_meeting_date');
  if (!input || input.disabled || input.readOnly) return;
  const warning = document.createElement('p');
  warning.className = 'help';
  warning.id = 'shs-weekday-warning';
  warning.setAttribute('role', 'status');
  input.insertAdjacentElement('afterend', warning);
  input.setAttribute('aria-describedby', [input.getAttribute('aria-describedby'), warning.id].filter(Boolean).join(' '));
  const validate = () => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(input.value);
    if (!match) return;
    const day = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])).getDay();
    if (day === 0 || day === 6) {
      input.value = '';
      warning.textContent = 'Choose a Monday-Friday date. Weekend SHS dates are not allowed.';
    } else {
      warning.textContent = '';
    }
  };
  input.addEventListener('change', validate);
  // Django admin's calendar assigns value programmatically, then focuses input.
  input.addEventListener('focus', validate);
});
