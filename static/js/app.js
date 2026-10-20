(function () {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("schedease-theme");
  if (savedTheme) root.dataset.theme = savedTheme;

  const fieldTooltips = {
    "email or username": "Enter the email address or username for your account.",
    "username": "Enter your account username used for logging in.",
    "password": "Enter your password to sign in securely.",
    "code": "Use a short unique code people can recognize, such as BSIT or IT101.",
    "name": "Enter the display name people will see in lists and schedules.",
    "description": "Add a short note that explains what this item is for.",
    "department": "Choose the department that owns this record.",
    "program": "Choose the program this section or student belongs to.",
    "year level": "Select the student's current year level.",
    "level": "Enter the year level number, such as 1 for first year.",
    "label": "Enter a friendly name, such as First Year.",
    "size": "Enter how many students are in this section.",
    "adviser": "Choose the faculty adviser for this section, if there is one.",
    "title": "Enter the full subject name shown to users.",
    "units": "Enter the credit units for this subject.",
    "lecture hours": "Enter how many classroom hours this subject needs each week.",
    "lab hours": "Enter how many lab hours this subject needs each week.",
    "required room type": "Choose the kind of room this subject needs, such as lecture room or computer lab.",
    "user": "Link this record to a login account when the person needs access.",
    "employee id": "Enter the faculty member's official employee number.",
    "full name": "Enter the person's complete name.",
    "max weekly hours": "Set the most teaching hours this faculty member should receive per week.",
    "student number": "Enter the student's official school ID number.",
    "room type": "Choose what this room is best used for, such as lecture, lab, or gym.",
    "capacity": "Make sure the room can fit all students in the class.",
    "is active": "Turn this on when the room or term is available for scheduling.",
    "school year": "Enter the school year, such as 2026-2027.",
    "starts on": "Choose the first day of the term.",
    "ends on": "Choose the last day of the term.",
    "term": "Choose the academic term this record belongs to.",
    "subject": "Choose the subject for this class assignment.",
    "faculty": "Choose the faculty member assigned to teach this class.",
    "section": "Choose the section that will take this class.",
    "room": "Choose the room where the class will meet.",
    "day": "Choose the class day, such as Monday.",
    "start time": "Choose when the class begins, e.g., Monday 8:00 AM.",
    "end time": "Choose when the class ends, e.g., Monday 10:00 AM.",
    "kind": "Choose whether this time is available, preferred, or unavailable.",
    "settings": "Choose the schedule generation setup you want to use.",
    "population size": "Controls how many schedule options are compared at a time.",
    "generations": "Controls how many rounds are used to improve the schedule.",
    "mutation rate": "Controls how often small changes are made when generating schedules.",
    "crossover rate": "Controls how often strong parts of schedules are combined.",
    "elitism": "Keeps the best schedule options from being lost while new ones are made.",
    "status": "Choose whether the schedule is a draft, approved, or published.",
    "credential": "Choose the qualification this faculty member has.",
    "required credential": "Choose the qualification needed to teach this subject.",
    "acceptable equivalents": "Choose other credentials that are also allowed for this subject.",
    "issued by": "Enter who granted this credential, if known.",
    "issued on": "Choose when this credential was issued.",
    "expires on": "Choose when this credential expires, if it has an end date.",
    "notes": "Add any helpful details for administrators.",
    "assignment": "Choose the teaching assignment connected to this override.",
    "admin user": "Shows which admin approved this override.",
    "reason": "Explain why this exception is being allowed.",
    "missing credentials": "Shows which required credentials were missing.",
    "override reason": "Briefly explain why this exception should be allowed."
  };

  const contextualTooltips = {
    "login|email or username": "Enter the email address or username for your account.",
    "login|password": "Enter your password to sign in securely.",
    "login|remember me": "Keeps you signed in on this device after logging in.",

    "departments|code": "Enter the short department code, such as CCS or CBA.",
    "departments|name": "Enter the full department name shown across the system.",

    "programs|department": "Choose the department that offers this program.",
    "programs|code": "Enter the short program code, such as BSIT or BSCS.",
    "programs|name": "Enter the full program name students and staff will see.",

    "year-levels|level": "Enter the year number, such as 1 for first year.",
    "year-levels|label": "Enter the friendly year level name, such as First Year.",

    "sections|program": "Select the academic program this section belongs to.",
    "sections|year level": "Select the students' current year level.",
    "sections|section code": "Enter the section identifier, such as 201 or 202.",
    "sections|size": "Enter the number of students in this section.",
    "sections|adviser": "Choose the faculty adviser for this section, if assigned.",

    "subjects|code": "Enter the subject code shown in schedules, such as IT101.",
    "subjects|title": "Enter the full subject title students and faculty will see.",
    "subjects|department": "Choose the department that owns this subject.",
    "subjects|units": "Enter the credit units for this subject.",
    "subjects|lecture hours": "Enter how many classroom hours this subject needs each week.",
    "subjects|lab hours": "Enter how many lab hours this subject needs each week.",
    "subjects|required room type": "Choose the kind of room this subject needs.",

    "credentials|name": "Enter the exact credential name used to qualify faculty.",
    "credentials|description": "Add a short note describing when this credential applies.",

    "faculty-credentials|faculty": "Choose the faculty member who has this credential.",
    "faculty-credentials|credential": "Choose the credential this faculty member has earned.",
    "faculty-credentials|issued by": "Enter the school or organization that granted it, if known.",
    "faculty-credentials|issued on": "Choose the date this credential was issued, if known.",
    "faculty-credentials|expires on": "Choose the expiration date, if this credential expires.",
    "faculty-credentials|notes": "Add helpful details about this faculty credential.",

    "subject-credential-requirements|subject": "Choose the subject that needs a teaching credential.",
    "subject-credential-requirements|required credential": "Choose the credential required to teach this subject.",
    "subject-credential-requirements|acceptable equivalents": "Choose other credentials that are allowed for this subject.",
    "subject-credential-requirements|notes": "Add helpful details about this subject requirement.",

    "faculty|user": "Link this faculty record to a login account, if they need access.",
    "faculty|department": "Choose the department this faculty member belongs to.",
    "faculty|employee id": "Enter the faculty member's official employee number.",
    "faculty|full name": "Enter the faculty member's complete name.",
    "faculty|max weekly hours": "Set the most teaching hours this faculty member should have each week.",

    "students|user": "Link this student record to a login account, if needed.",
    "students|section": "Choose the section this student belongs to.",
    "students|student number": "Enter the student's official school ID number.",
    "students|full name": "Enter the student's complete name.",

    "rooms|name": "Enter the room name or number shown in schedules.",
    "rooms|room type": "Choose what this room is best used for, such as lecture or lab.",
    "rooms|capacity": "Make sure the room can fit all students in the class.",
    "rooms|is active": "Turn this on when the room is available for scheduling.",

    "terms|name": "Enter the term name, such as First Semester.",
    "terms|school year": "Enter the school year, such as 2026-2027.",
    "terms|starts on": "Choose the first day of this academic term.",
    "terms|ends on": "Choose the last day of this academic term.",
    "terms|is active": "Turn this on when this term is ready to use.",

    "assignments|term": "Choose the term for this teaching assignment.",
    "assignments|subject": "Choose the subject that will be taught.",
    "assignments|faculty": "Choose the faculty member assigned to teach it.",
    "assignments|section": "Choose the section that will take this subject.",

    "availability|faculty": "Choose the faculty member for this time slot.",
    "availability|room": "Choose the room for this time slot, when setting room availability.",
    "availability|day": "Choose the day for this availability time.",
    "availability|start time": "Choose when this time slot begins, e.g., 8:00 AM.",
    "availability|end time": "Choose when this time slot ends, e.g., 10:00 AM.",
    "availability|kind": "Choose whether this time is available, preferred, or unavailable.",

    "ga-settings|name": "Enter a clear name for this schedule setup.",
    "ga-settings|population size": "Controls how many schedule options are compared at a time.",
    "ga-settings|generations": "Controls how many rounds are used to improve the schedule.",
    "ga-settings|mutation rate": "Controls how often small changes are made when generating schedules.",
    "ga-settings|crossover rate": "Controls how often strong parts of schedules are combined.",
    "ga-settings|elitism": "Keeps the best schedule options from being lost while new ones are made.",

    "schedules|term": "Choose the academic term this schedule belongs to.",
    "schedules|name": "Enter the schedule name shown to admins and users.",
    "schedules|status": "Choose whether this schedule is a draft, approved, or published.",

    "credential-overrides|assignment": "Choose the teaching assignment approved for this exception.",
    "credential-overrides|subject": "Shows the subject involved in this exception.",
    "credential-overrides|faculty": "Shows the faculty member approved for this exception.",
    "credential-overrides|admin user": "Shows the admin who approved this exception.",
    "credential-overrides|reason": "Explain why this exception was approved.",
    "credential-overrides|missing credentials": "Lists the required credentials that were missing.",

    "generate-schedule|term": "Choose the term you want to create a schedule for.",
    "generate-schedule|settings": "Choose the saved setup to use for schedule generation.",
    "generate-schedule|name": "Enter a name for the generated schedule draft.",

    "schedule-entry|assignment": "Choose the class assignment for this schedule entry.",
    "schedule-entry|room": "Choose where this class meeting will be held.",
    "schedule-entry|day": "Choose the day this class meeting happens.",
    "schedule-entry|start time": "Choose when this class meeting starts.",
    "schedule-entry|end time": "Choose when this class meeting ends.",

    "schedule-filters|term": "Show schedules from one academic term.",
    "schedule-filters|department": "Show classes from one department.",
    "schedule-filters|program": "Show classes from one program.",
    "schedule-filters|year level": "Show classes for one year level.",
    "schedule-filters|section": "Show classes for one section.",
    "schedule-filters|subject": "Show classes for one subject.",

    "room-utilization-filters|search rooms": "Find rooms by name.",
    "room-utilization-filters|room type": "Show only rooms of the selected type.",
    "room-utilization-filters|utilization range": "Show rooms by how much they are currently used."
  };

  const actionTooltips = {
    "sign out": "Sign out of your account.",
    "save": "Save your changes.",
    "cancel": "Go back without saving changes.",
    "new": "Create a new record.",
    "edit": "Update this record.",
    "delete": "Remove this record after confirmation.",
    "open": "View the full schedule details.",
    "publish": "Make this schedule visible to users.",
    "csv": "Download this schedule as a spreadsheet file.",
    "pdf": "Download this schedule as a PDF file.",
    "apply filters": "Show only the records that match your selections.",
    "add slot": "Add a day and time for your availability.",
    "add entry": "Add a class meeting to this schedule.",
    "run genetic algorithm": "Create a new schedule draft using the saved setup.",
    "view published schedules": "Open schedules that are already visible to users.",
    "search published schedules": "Find published schedules by section, subject, or term.",
    "update availability": "Change the days and times you can teach.",
    "confirm override": "Allow this exception and save the reason.",
    "delete record": "Permanently remove this record after confirmation."
  };

  function normalize(text) {
    return text.toLowerCase().replace(/:/g, "").replace(/\s+/g, " ").trim();
  }

  function tooltipForLabel(label) {
    const text = normalize(label.textContent);
    const context = label.closest("form")?.dataset.tooltipContext || "";
    if (contextualTooltips[`${context}|${text}`]) return contextualTooltips[`${context}|${text}`];
    return fieldTooltips[text] || `${label.textContent.trim().replace(":", "")} helps keep schedules clear and accurate.`;
  }

  const appTooltip = document.createElement("div");
  appTooltip.className = "app-tooltip";
  appTooltip.id = "schedease-tooltip";
  let tooltipTarget = null;
  appTooltip.setAttribute("role", "tooltip");
  document.body.appendChild(appTooltip);

  function placeTooltip(target) {
    const text = target.dataset.tooltip;
    if (!text) return;
    hideTooltip();
    tooltipTarget = target;
    const descriptions = new Set((target.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
    descriptions.add(appTooltip.id);
    target.setAttribute("aria-describedby", [...descriptions].join(" "));
    appTooltip.textContent = text;
    appTooltip.classList.add("is-visible");

    const targetRect = target.getBoundingClientRect();
    const tooltipRect = appTooltip.getBoundingClientRect();
    const gap = 10;
    const margin = 8;
    const preferred = target.closest(".nav-group") && document.body.classList.contains("sidebar-collapsed")
      ? "right" : target.dataset.tooltipPlacement || "top";
    const positions = {
      top: [targetRect.top - tooltipRect.height - gap, targetRect.left + (targetRect.width - tooltipRect.width) / 2],
      bottom: [targetRect.bottom + gap, targetRect.left + (targetRect.width - tooltipRect.width) / 2],
      right: [targetRect.top + (targetRect.height - tooltipRect.height) / 2, targetRect.right + gap],
      left: [targetRect.top + (targetRect.height - tooltipRect.height) / 2, targetRect.left - tooltipRect.width - gap],
    };
    const opposite = {top: "bottom", bottom: "top", right: "left", left: "right"};
    const order = [...new Set([preferred, opposite[preferred], "bottom", "top", "right", "left"])].filter(key => positions[key]);
    // Keep the chosen side clear of its trigger; clamp only the cross axis.
    const fits = key => {
      const [y, x] = positions[key];
      return key === "top" || key === "bottom"
        ? y >= margin && y + tooltipRect.height <= innerHeight - margin
        : x >= margin && x + tooltipRect.width <= innerWidth - margin;
    };
    const placement = order.find(fits) || order[0];
    let [top, left] = positions[placement];
    top = Math.max(margin, Math.min(top, innerHeight - tooltipRect.height - margin));
    left = Math.max(margin, Math.min(left, innerWidth - tooltipRect.width - margin));
    appTooltip.style.top = `${top}px`;
    appTooltip.style.left = `${left}px`;
  }

  function hideTooltip() {
    if (tooltipTarget) {
      const descriptions = (tooltipTarget.getAttribute("aria-describedby") || "").split(/\s+/).filter(id => id && id !== appTooltip.id);
      if (descriptions.length) tooltipTarget.setAttribute("aria-describedby", descriptions.join(" "));
      else tooltipTarget.removeAttribute("aria-describedby");
      tooltipTarget = null;
    }
    appTooltip.classList.remove("is-visible");
  }

  window.addEventListener("scroll", () => {
    const focusedNavigation = tooltipTarget === document.activeElement && tooltipTarget?.closest('.nav-group') ? tooltipTarget : null;
    hideTooltip();
    if (focusedNavigation) requestAnimationFrame(() => {
      if (document.activeElement === focusedNavigation) placeTooltip(focusedNavigation);
    });
  }, true);
  window.addEventListener("resize", hideTooltip);

  function bindTooltips(scope = document) {
    scope.querySelectorAll(".info-icon[data-tooltip]").forEach((icon) => {
      if (icon.tagName === "BUTTON") return;
      const button = document.createElement("button");
      for (const attribute of icon.attributes) button.setAttribute(attribute.name, attribute.value);
      button.type = "button";
      button.textContent = icon.textContent;
      button.setAttribute("aria-label", icon.getAttribute("aria-label") || "More information");
      icon.replaceWith(button);
    });
    scope.querySelectorAll("[data-tooltip]").forEach((target) => {
      if (target.dataset.tooltipBound === "true") return;
      target.dataset.tooltipBound = "true";
      target.addEventListener("mouseenter", () => placeTooltip(target));
      target.addEventListener("focus", () => placeTooltip(target));
      target.addEventListener("mouseleave", hideTooltip);
      target.addEventListener("blur", hideTooltip);
      target.addEventListener("click", (event) => {
        if (target.classList.contains("info-icon")) {
          event.preventDefault();
          placeTooltip(target);
        } else hideTooltip();
      });
    });
  }

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.dataset.tooltip = "Switch between light and dark mode.";
    button.addEventListener("click", () => {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      localStorage.setItem("schedease-theme", next);
    });
  });

  const sidebar = document.querySelector('.sidebar');
  const workspace = document.querySelector('.workspace');
  const mobileNavigation = window.matchMedia('(max-width: 900px)');
  let navigationTrigger = null;
  function syncNavigation() {
    const open = document.body.classList.contains('sidebar-open');
    const collapsed = document.body.classList.contains('sidebar-collapsed');
    if (sidebar) sidebar.inert = mobileNavigation.matches && !open;
    if (workspace) workspace.inert = mobileNavigation.matches && open;
    document.querySelectorAll('button[data-sidebar-toggle], [data-sidebar-collapse]').forEach(button => {
      const expanded = mobileNavigation.matches ? open : !collapsed;
      button.setAttribute('aria-controls', 'sidebar');
      button.setAttribute('aria-expanded', String(expanded));
      const label = mobileNavigation.matches ? (open ? 'Close navigation' : 'Open navigation') : (collapsed ? 'Expand navigation' : 'Collapse navigation');
      button.setAttribute('aria-label', label);
      button.dataset.tooltip = label;
    });
  }
  function closeNavigation() {
    if (!document.body.classList.contains('sidebar-open')) return;
    document.body.classList.remove('sidebar-open');
    syncNavigation();
    hideTooltip();
    navigationTrigger?.focus({preventScroll: true});
  }
  document.querySelectorAll('[data-sidebar-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      if (document.body.classList.contains('sidebar-open')) closeNavigation();
      else {
        navigationTrigger = button;
        document.body.classList.add('sidebar-open');
        syncNavigation();
        sidebar?.querySelector('[data-sidebar-collapse]')?.focus({preventScroll: true});
      }
    });
  });
  if (sessionStorage.getItem('schedease-sidebar-collapsed') === 'true') {
    document.documentElement.classList.add('sidebar-collapsed');
    document.body.classList.add('sidebar-collapsed');
  }
  document.querySelectorAll('[data-sidebar-collapse]').forEach(button => {
    button.addEventListener('click', () => {
      if (mobileNavigation.matches) { closeNavigation(); return; }
      document.body.classList.toggle('sidebar-collapsed');
      document.documentElement.classList.toggle('sidebar-collapsed', document.body.classList.contains('sidebar-collapsed'));
      sessionStorage.setItem('schedease-sidebar-collapsed', document.body.classList.contains('sidebar-collapsed'));
      syncNavigation();
    });
  });
  mobileNavigation.addEventListener('change', () => {
    const focusedInside = sidebar?.contains(document.activeElement);
    document.body.classList.remove('sidebar-open');
    syncNavigation();
    if (mobileNavigation.matches && focusedInside) document.querySelector('button[data-sidebar-toggle]')?.focus({preventScroll: true});
  });
  document.addEventListener('keydown', event => {
    if (!mobileNavigation.matches || !document.body.classList.contains('sidebar-open')) return;
    if (event.key === 'Escape') { event.preventDefault(); closeNavigation(); }
    if (event.key === 'Tab') {
      const controls = [...sidebar.querySelectorAll('a[href], button, summary')].filter(control => !control.disabled && control.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  });
  syncNavigation();

  const currentPath = window.location.pathname;
  const navLinks = Array.from(document.querySelectorAll(".nav-group a"));
  let bestMatch = null;
  navLinks.forEach((link) => {
    link.dataset.tooltip = link.textContent.trim();
    link.setAttribute("aria-label", link.textContent.trim());
    link.dataset.tooltipPlacement = "right";
    const href = link.getAttribute("href");
    if (href === currentPath || (href && href !== "/" && currentPath.startsWith(href))) {
      if (!bestMatch || href.length > bestMatch.getAttribute("href").length) bestMatch = link;
    }
  });
  if (bestMatch) {
    bestMatch.classList.add("is-active");
    bestMatch.setAttribute("aria-current", "page");
  }

  document.querySelectorAll("[data-nav-group]").forEach((group) => {
    const key = `schedease-nav-group-${group.dataset.navGroup}`;
    const hasActiveItem = Boolean(group.querySelector("a.is-active"));
    const summary = group.querySelector("summary");
    summary?.setAttribute("aria-label", summary.textContent.trim());
    summary?.setAttribute("data-tooltip-placement", "right");
    const saved = sessionStorage.getItem(key);
    if (hasActiveItem) group.open = true;
    else if (saved !== null) group.open = saved === "true";
    group.addEventListener("toggle", () => sessionStorage.setItem(key, String(group.open)));
  });

  document.querySelectorAll(".nav-group").forEach((nav) => {
    const scrollKey = "schedease-sidebar-scroll";
    const initialScroll = sessionStorage.getItem(scrollKey);
    let restoring = true;
    const saveScroll = () => { if (!restoring) sessionStorage.setItem(scrollKey, String(nav.scrollTop)); };
    const restoreScroll = () => {
      const savedScroll = initialScroll;
      if (savedScroll === null) return;
      const target = Number(savedScroll);
      if (Number.isFinite(target)) nav.scrollTop = target;
    };

    // Expanded groups affect the scrollable height, so restore only after their
    // saved state has been applied and the browser has completed layout.
    restoreScroll();
    window.requestAnimationFrame(() => {
      restoreScroll();
      window.requestAnimationFrame(() => { restoreScroll(); restoring = false; });
    });

    nav.addEventListener("scroll", saveScroll, { passive: true });
    nav.querySelectorAll("a").forEach((link) => link.addEventListener("pointerdown", saveScroll));
    window.addEventListener("pagehide", saveScroll);
  });

  document.querySelectorAll(".toast-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".toast")?.remove());
  });

  const loginModal = document.querySelector("[data-login-modal]");
  let loginReturnFocus = null;
  let autoModalClosed = false;
  function loginFocusables() {
    return [...loginModal.querySelectorAll("a[href], button, input, select, textarea, [tabindex]")]
      .filter(control => !control.disabled && control.tabIndex >= 0 && control.getClientRects().length);
  }
  function openLoginModal() {
    if (!loginModal) return;
    if (!loginModal.classList.contains("is-open")) loginReturnFocus = document.activeElement;
    loginModal.classList.add("is-open");
    loginModal.classList.add("is-auto-opening");
    loginModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    window.setTimeout(() => loginModal.classList.remove("is-auto-opening"), 320);
    window.setTimeout(() => {
      if (loginModal.classList.contains("is-open")) (loginModal.querySelector("input[name='username']") || loginFocusables()[0])?.focus();
    }, 80);
  }

  function closeLoginModal() {
    if (!loginModal?.classList.contains("is-open")) return;
    autoModalClosed = true;
    hideTooltip();
    loginModal.classList.remove("is-open");
    loginModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    const target = loginReturnFocus?.isConnected && loginReturnFocus !== document.body ? loginReturnFocus : document.querySelector("[data-login-open]");
    target?.focus();
  }

  document.querySelectorAll("[data-login-open]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      openLoginModal();
    });
  });
  document.querySelectorAll("[data-login-close]").forEach((button) => {
    button.addEventListener("click", closeLoginModal);
  });
  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.closest(".password-field")?.querySelector("input");
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
  if (loginModal?.classList.contains("is-open")) {
    openLoginModal();
  }
  if (loginModal?.dataset.loginAutoOpen === "true") {
    loginModal.querySelectorAll("[data-login-close]").forEach((button) => {
      button.addEventListener("click", () => {
        autoModalClosed = true;
      });
    });
    window.setTimeout(() => {
      if (!autoModalClosed && !loginModal.classList.contains("is-open")) {
        openLoginModal();
      }
    }, 420);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { hideTooltip(); closeLoginModal(); }
    if (event.key === "Tab" && loginModal?.classList.contains("is-open")) {
      const controls = loginFocusables();
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !loginModal.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !loginModal.contains(document.activeElement))) {
        event.preventDefault(); first?.focus();
      }
    }
  });

  function filterTables(value, scope) {
    const query = value.trim().toLowerCase();
    scope.querySelectorAll("table tbody tr").forEach((row) => {
      row.hidden = query.length > 0 && !row.textContent.toLowerCase().includes(query);
    });
  }

  document.querySelectorAll("[data-table-filter]").forEach((input) => {
    const panel = input.closest(".panel") || document;
    input.closest("label")?.setAttribute("data-tooltip", "Search the records in this table.");
    input.addEventListener("input", () => filterTables(input.value, panel));
  });

  document.querySelectorAll("[data-global-filter]").forEach((input) => {
    input.dataset.tooltip = "Filter rows loaded on this page only. Other pages and records are not searched. On pages without tables, this has no effect.";
    input.addEventListener("input", () => filterTables(input.value, document));
  });

  document.querySelectorAll("th[data-sort]").forEach((header) => {
    const sortButton = document.createElement("button");
    sortButton.type = "button";
    sortButton.className = "sort-control";
    sortButton.dataset.tooltip = "Sort this column.";
    sortButton.setAttribute("aria-label", `Sort by ${header.textContent.trim()}`);
    while (header.firstChild) sortButton.appendChild(header.firstChild);
    header.appendChild(sortButton);
    header.addEventListener("click", () => {
      const table = header.closest("table");
      const tbody = table.querySelector("tbody");
      const index = Array.from(header.parentNode.children).indexOf(header);
      const direction = header.dataset.direction === "asc" ? "desc" : "asc";
      header.dataset.direction = direction;
      table.querySelectorAll("th[aria-sort]").forEach(other => other.removeAttribute("aria-sort"));
      header.setAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");
      const rows = Array.from(tbody.querySelectorAll("tr")).filter((row) => row.children.length > 1);
      rows.sort((a, b) => {
        const left = a.children[index]?.textContent.trim().toLowerCase() || "";
        const right = b.children[index]?.textContent.trim().toLowerCase() || "";
        return direction === "asc" ? left.localeCompare(right) : right.localeCompare(left);
      });
      rows.forEach((row) => tbody.appendChild(row));
    });
  });

  document.querySelectorAll("form").forEach((form) => {
    if (form.dataset.autoTooltips !== "false") {
      form.querySelectorAll("label").forEach((label) => {
        if (label.querySelector(".info-icon")) return;
        const text = label.textContent.trim().replace(":", "");
        const icon = document.createElement("span");
        icon.className = "info-icon";
        icon.setAttribute("aria-label", `More information about ${text}`);
        icon.textContent = "i";
        icon.dataset.tooltip = tooltipForLabel(label);
        label.appendChild(icon);
      });
    }

    form.querySelectorAll("button, .button").forEach((control) => {
      if (control.dataset.tooltip) return;
      const key = normalize(control.textContent);
      if (actionTooltips[key]) control.dataset.tooltip = actionTooltips[key];
    });

    form.addEventListener("submit", () => {
      const submitter = form.querySelector("button[type='submit'], button:not([type]), .primary");
      if (submitter && submitter.dataset.loadingText !== "false") submitter.classList.add("loading");
    });
  });

  document.querySelectorAll("[data-schedule-live-filter]").forEach((input) => {
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      const tablePanel = document.querySelector('[data-schedule-view-panel="table"]');
      const timetablePanel = document.querySelector('[data-schedule-view-panel="timetable"]');
      if (tablePanel) filterTables(input.value, tablePanel);
      tablePanel?.querySelectorAll(".schedule-section-group").forEach((group) => {
        const rows = Array.from(group.querySelectorAll("tbody tr"));
        group.hidden = rows.length > 0 && rows.every((row) => row.hidden);
      });
      timetablePanel?.querySelectorAll(".schedule-block").forEach((block) => {
        block.hidden = query.length > 0 && !block.textContent.toLowerCase().includes(query);
      });
      timetablePanel?.querySelectorAll(".day-column").forEach((column) => {
        const blocks = Array.from(column.querySelectorAll(".schedule-block"));
        column.classList.toggle("has-no-matches", query.length > 0 && blocks.length > 0 && blocks.every((block) => block.hidden));
      });
    });
  });

  document.querySelectorAll("[data-schedule-view-button]").forEach((button) => {
    button.addEventListener("click", () => {
      const selected = button.dataset.scheduleViewButton;
      document.querySelectorAll("[data-schedule-view-button]").forEach((item) => {
        const active = item.dataset.scheduleViewButton === selected;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll("[data-schedule-view-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.scheduleViewPanel !== selected;
      });
    });
  });

  document.querySelectorAll("[data-planning-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const selected = button.dataset.planningTab;
      document.querySelectorAll("[data-planning-tab]").forEach((item) => item.classList.toggle("is-active", item === button));
      document.querySelectorAll("[data-planning-row]").forEach((row) => {
        row.hidden = selected !== "all" && row.dataset.planningRow !== selected;
      });
    });
  });

  document.querySelectorAll("[data-schedule-generation]").forEach((form) => {
    const indicator = form.querySelector("[data-generation-loading]");
    const submitter = form.querySelector(".generation-submit");
    let submitting = false;

    const resetGenerationState = () => {
      submitting = false;
      form.removeAttribute("aria-busy");
      if (indicator) indicator.hidden = true;
      if (submitter) {
        submitter.disabled = false;
        submitter.removeAttribute("aria-disabled");
        submitter.classList.remove("loading");
      }
    };

    form.addEventListener("submit", (event) => {
      if (submitting) {
        event.preventDefault();
        return;
      }
      submitting = true;
      form.setAttribute("aria-busy", "true");
      if (indicator) indicator.hidden = false;
      if (submitter) {
        submitter.disabled = true;
        submitter.setAttribute("aria-disabled", "true");
        submitter.classList.add("loading");
      }
    });

    window.addEventListener("pageshow", resetGenerationState);
  });

  document.querySelectorAll("[data-form-draft]").forEach((form) => {
    const status = form.querySelector("[data-draft-status]");
    const csrf = form.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
    let savedState;
    let dirty = false;
    let finalSubmitting = false;
    let timer;

    const payload = () => {
      const values = {};
      Array.from(form.elements).forEach((field) => {
        if (!field.name || field.disabled || ["csrfmiddlewaretoken", "draft_conflict_confirm"].includes(field.name)) return;
        if (["submit", "button", "file"].includes(field.type)) return;
        if ((field.type === "checkbox" || field.type === "radio") && !field.checked) {
          if (!(field.name in values)) values[field.name] = "";
          return;
        }
        if (field.multiple) {
          values[field.name] = Array.from(field.selectedOptions).map((option) => option.value);
        } else if (field.name in values) {
          values[field.name] = [].concat(values[field.name], field.value);
        } else {
          values[field.name] = field.value;
        }
      });
      return values;
    };

    const setStatus = (text, state = "") => {
      if (!status) return;
      status.textContent = text;
      status.dataset.state = state;
    };

    const saveDraft = async (keepalive = false) => {
      if (!dirty || finalSubmitting) return true;
      const currentPayload = payload();
      setStatus("Saving draft...", "saving");
      try {
        const response = await fetch(form.dataset.draftSaveUrl, {
          method: "POST",
          credentials: "same-origin",
          keepalive,
          headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
          body: JSON.stringify({
            resource: form.dataset.draftResource,
            object_pk: form.dataset.draftObjectPk,
            payload: currentPayload,
            changed: true,
          }),
        });
        if (!response.ok) throw new Error("Draft request failed");
        savedState = JSON.stringify(currentPayload);
        dirty = false;
        setStatus("Draft saved", "saved");
        return true;
      } catch (error) {
        setStatus("Draft could not be saved. Check your connection and try again.", "error");
        return false;
      }
    };

    const noteChange = () => {
      dirty = JSON.stringify(payload()) !== savedState;
      window.clearTimeout(timer);
      if (dirty) {
        setStatus("Unsaved draft changes", "pending");
        timer = window.setTimeout(() => saveDraft(), 900);
      }
    };

    savedState = JSON.stringify(payload());
    form.addEventListener("input", noteChange);
    form.addEventListener("change", noteChange);
    form.addEventListener("focusout", () => {
      if (dirty) {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => saveDraft(), 250);
      }
    });
    form.addEventListener("submit", () => {
      finalSubmitting = true;
      window.clearTimeout(timer);
    });

    document.addEventListener("click", async (event) => {
      const link = event.target.closest("a[href]");
      if (!link || !dirty || finalSubmitting || link.target === "_blank") return;
      const destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      event.preventDefault();
      window.clearTimeout(timer);
      if (await saveDraft()) window.location.assign(destination.href);
    }, true);

    window.addEventListener("pagehide", () => {
      if (dirty && !finalSubmitting) saveDraft(true);
    });
  });

  document.querySelectorAll("[data-section-preview]").forEach((preview) => {
    const form = preview.closest("form");
    const program = form?.querySelector("[data-section-program]");
    const year = form?.querySelector("[data-section-year]");
    const code = form?.querySelector("[data-section-code]");
    const output = preview.querySelector("strong");
    const update = () => {
      const programCode = program?.selectedOptions[0]?.textContent.trim().toUpperCase() || "";
      const yearLevel = year?.selectedOptions[0]?.textContent.trim().match(/^\d+/)?.[0] || "";
      let sectionCode = code?.value.trim().toUpperCase() || "";
      const complete = sectionCode.match(/^\S+\s+\d+-([A-Z0-9][A-Z0-9_-]*)$/);
      if (complete) sectionCode = complete[1];
      output.textContent = programCode && yearLevel && sectionCode
        ? `${programCode} ${yearLevel}-${sectionCode}`
        : "Choose a program, year level, and section code";
    };
    [program, year, code].forEach((field) => {
      field?.addEventListener("input", update);
      field?.addEventListener("change", update);
    });
    update();
  });

  document.querySelectorAll("[data-assignment-editor]").forEach((form) => {
    const list = form.querySelector("[data-meeting-list]");
    const template = form.querySelector("[data-empty-meeting]");
    const total = form.querySelector("[name='meetings-TOTAL_FORMS']");
    const tabs = form.querySelector("[data-meeting-tabs]");
    const add = form.querySelector("[data-add-meeting]");
    const status = form.querySelector("[data-meeting-status]");
    const max = Number(form.querySelector("[name='meetings-MAX_NUM_FORMS']").value) || 1000;
    let selected;
    const panels = () => Array.from(list.querySelectorAll("[data-meeting-form]"));
    const field = (panel, name) => panel.querySelector(`[name$="-${name}"]`);
    const active = () => panels().filter((panel) => !field(panel, "DELETE").checked);
    const changed = () => form.dispatchEvent(new Event("change", {bubbles: true}));
    const summary = (panel) => {
      const type = field(panel, "component").selectedOptions[0]?.textContent || "Choose class type";
      const minutes = Number(field(panel, "duration_minutes").value);
      const duration = minutes > 0 ? (minutes % 60 === 0 ? `${minutes / 60} ${minutes === 60 ? "hour" : "hours"}` : `${minutes} minutes`) : "Course default duration";
      return `${type} \u00b7 ${duration}`;
    };
    const select = (panel, focus = false) => {
      selected = panel;
      panels().forEach((item) => { item.hidden = item !== panel; });
      Array.from(tabs.children).forEach((tab) => {
        const on = tab.getAttribute("aria-controls") === panel.id;
        tab.setAttribute("aria-selected", String(on));
        tab.tabIndex = on ? 0 : -1;
        if (on && focus) { tab.focus(); tab.scrollIntoView({block: "nearest", inline: "nearest"}); }
      });
    };
    const render = (target = selected, focus = false) => {
      const visible = active();
      tabs.replaceChildren();
      panels().forEach((panel) => {
        if (field(panel, "DELETE").checked) {
          panel.hidden = true;
          panel.querySelectorAll("[required]").forEach((input) => { input.required = false; });
        }
      });
      visible.forEach((panel, index) => {
        const prefix = field(panel, "meeting_index").name.replace(/-meeting_index$/, "");
        panel.id = `${prefix}-panel`;
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", `${prefix}-tab`);
        panel.querySelector("[data-meeting-number]").textContent = String(index + 1);
        const remove = panel.querySelector("[data-remove-meeting]");
        remove.hidden = false;
        remove.disabled = visible.length === 1;
        const tab = document.createElement("button");
        tab.type = "button";
        tab.className = "meeting-tab";
        tab.id = `${prefix}-tab`;
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-controls", panel.id);
        const title = document.createElement("strong");
        title.textContent = `Meeting ${index + 1}`;
        const detail = document.createElement("small");
        detail.textContent = summary(panel);
        tab.append(title, detail);
        if (panel.querySelector(".errorlist") || panel.dataset.invalid === "true") {
          const error = document.createElement("span");
          error.className = "meeting-tab-error";
          error.textContent = "Needs attention";
          tab.append(error);
        }
        tab.addEventListener("click", () => select(panel, true));
        tabs.append(tab);
      });
      add.disabled = Number(total.value) >= max;
      if (visible.length) select(visible.includes(target) ? target : visible[0], focus);
    };
    tabs.addEventListener("keydown", (event) => {
      const items = Array.from(tabs.children);
      const index = items.indexOf(document.activeElement);
      if (index < 0) return;
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % items.length;
      if (event.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = items.length - 1;
      if (next !== undefined) { event.preventDefault(); select(active()[next], true); }
    });
    add.addEventListener("click", () => {
      const index = Number(total.value);
      if (index >= max) return;
      const nextNumber = Math.max(0, ...panels().map((panel) => Number(field(panel, "meeting_index").value) || 0)) + 1;
      list.insertAdjacentHTML("beforeend", template.innerHTML.replaceAll("__prefix__", String(index)).replaceAll("__number__", String(index + 1)));
      total.value = String(index + 1);
      const panel = panels().at(-1);
      field(panel, "meeting_index").value = String(nextNumber);
      render(panel, true);
      status.textContent = `Meeting ${active().length} added.`;
      changed();
    });
    list.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove-meeting]");
      if (!remove || active().length <= 1) return;
      const panel = remove.closest("[data-meeting-form]");
      const hasInformation = field(panel, "id").value || Array.from(panel.querySelectorAll("input:not([type=hidden]), select, textarea")).some((input) => !input.name.endsWith("-DELETE") && !input.name.endsWith("-meeting_index") && input.value && input.value !== "0");
      if (hasInformation && !window.confirm("Remove this meeting? Its information will be removed when you save the assignment.")) return;
      const visible = active();
      const index = visible.indexOf(panel);
      field(panel, "DELETE").checked = true;
      render(visible[index + 1] || visible[index - 1], true);
      status.textContent = "Meeting removed. Save the assignment to apply this change.";
      changed();
    });
    list.addEventListener("input", (event) => {
      const panel = event.target.closest("[data-meeting-form]");
      if (!panel) return;
      const tab = document.getElementById(panel.getAttribute("aria-labelledby"));
      if (tab) tab.querySelector("small").textContent = summary(panel);
      if (panel.dataset.invalid === "true" && !panel.querySelector(":invalid")) {
        delete panel.dataset.invalid;
        if (!panel.querySelector(".errorlist")) tab?.querySelector(".meeting-tab-error")?.remove();
      }
    });
    let firstInvalid = null;
    form.addEventListener("invalid", (event) => {
      const panel = event.target.closest("[data-meeting-form]");
      if (panel && !field(panel, "DELETE").checked) {
        event.preventDefault();
        panel.dataset.invalid = "true";
        if (!firstInvalid) {
          firstInvalid = event.target;
          queueMicrotask(() => {
            const input = firstInvalid;
            firstInvalid = null;
            render(input.closest("[data-meeting-form]"));
            input.focus();
            status.textContent = input.validationMessage;
          });
        }
      }
    }, true);
    form.classList.add("meeting-tabs-ready");
    form.querySelector("[data-meeting-toolbar]").hidden = false;
    render(active().find((panel) => panel.querySelector(".errorlist")) || active()[0]);
  });

  document.querySelectorAll("a.button, button").forEach((control) => {
    if (control.dataset.tooltip) return;
    const key = normalize(control.textContent);
    if (actionTooltips[key]) control.dataset.tooltip = actionTooltips[key];
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest("a[aria-disabled='true']")) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  bindTooltips();
})();
