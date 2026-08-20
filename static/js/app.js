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
  appTooltip.setAttribute("role", "tooltip");
  document.body.appendChild(appTooltip);

  function placeTooltip(target) {
    const text = target.dataset.tooltip;
    if (!text) return;
    appTooltip.textContent = text;
    appTooltip.classList.add("is-visible");

    const targetRect = target.getBoundingClientRect();
    const tooltipRect = appTooltip.getBoundingClientRect();
    const gap = 10;
    const margin = 8;
    let placement = target.dataset.tooltipPlacement || "top";

    if (target.closest(".nav-group") && document.body.classList.contains("sidebar-collapsed")) {
      placement = "right";
    } else if (targetRect.top < tooltipRect.height + gap + margin) {
      placement = "bottom";
    }

    let top;
    let left;
    if (placement === "right") {
      top = targetRect.top + targetRect.height / 2 - tooltipRect.height / 2;
      left = targetRect.right + gap;
    } else if (placement === "bottom") {
      top = targetRect.bottom + gap;
      left = targetRect.left + targetRect.width / 2 - tooltipRect.width / 2;
    } else {
      top = targetRect.top - tooltipRect.height - gap;
      left = targetRect.left + targetRect.width / 2 - tooltipRect.width / 2;
    }

    top = Math.max(margin, Math.min(top, window.innerHeight - tooltipRect.height - margin));
    left = Math.max(margin, Math.min(left, window.innerWidth - tooltipRect.width - margin));
    appTooltip.style.top = `${top}px`;
    appTooltip.style.left = `${left}px`;
  }

  function hideTooltip() {
    appTooltip.classList.remove("is-visible");
  }

  window.addEventListener("scroll", hideTooltip, true);
  window.addEventListener("resize", hideTooltip);

  function bindTooltips(scope = document) {
    scope.querySelectorAll("[data-tooltip]").forEach((target) => {
      if (target.dataset.tooltipBound === "true") return;
      target.dataset.tooltipBound = "true";
      target.addEventListener("mouseenter", () => placeTooltip(target));
      target.addEventListener("focus", () => placeTooltip(target));
      target.addEventListener("mouseleave", hideTooltip);
      target.addEventListener("blur", hideTooltip);
      target.addEventListener("click", hideTooltip);
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

  document.querySelectorAll("[data-sidebar-toggle]").forEach((button) => {
    button.dataset.tooltip = "Open the navigation menu.";
    button.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
  });

  if (sessionStorage.getItem("schedease-sidebar-collapsed") === "true") {
    document.documentElement.classList.add("sidebar-collapsed");
    document.body.classList.add("sidebar-collapsed");
  }
  document.querySelectorAll("[data-sidebar-collapse]").forEach((button) => {
    button.dataset.tooltip = "Open or close the sidebar menu.";
    button.addEventListener("click", () => {
      document.body.classList.toggle("sidebar-collapsed");
      document.documentElement.classList.toggle("sidebar-collapsed", document.body.classList.contains("sidebar-collapsed"));
      sessionStorage.setItem("schedease-sidebar-collapsed", document.body.classList.contains("sidebar-collapsed"));
    });
  });

  const currentPath = window.location.pathname;
  const navLinks = Array.from(document.querySelectorAll(".nav-group a"));
  let bestMatch = null;
  navLinks.forEach((link) => {
    link.dataset.tooltip = link.textContent.trim();
    link.setAttribute("title", link.textContent.trim());
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
    const saved = sessionStorage.getItem(key);
    if (hasActiveItem) group.open = true;
    else if (saved !== null) group.open = saved === "true";
    group.addEventListener("toggle", () => sessionStorage.setItem(key, String(group.open)));
  });

  document.querySelectorAll(".nav-group").forEach((nav) => {
    const scrollKey = "schedease-sidebar-scroll";
    const saveScroll = () => sessionStorage.setItem(scrollKey, String(nav.scrollTop));
    const restoreScroll = () => {
      const savedScroll = sessionStorage.getItem(scrollKey);
      if (savedScroll === null) return;
      const target = Number(savedScroll);
      if (Number.isFinite(target)) nav.scrollTop = target;
    };

    // Expanded groups affect the scrollable height, so restore only after their
    // saved state has been applied and the browser has completed layout.
    restoreScroll();
    window.requestAnimationFrame(() => {
      restoreScroll();
      window.requestAnimationFrame(restoreScroll);
    });

    nav.addEventListener("scroll", saveScroll, { passive: true });
    nav.querySelectorAll("a").forEach((link) => link.addEventListener("pointerdown", saveScroll));
    window.addEventListener("pagehide", saveScroll);
  });

  document.querySelectorAll(".toast-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".toast")?.remove());
  });

  const loginModal = document.querySelector("[data-login-modal]");
  function openLoginModal() {
    if (!loginModal) return;
    loginModal.classList.add("is-open");
    loginModal.classList.add("is-auto-opening");
    loginModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    window.setTimeout(() => loginModal.classList.remove("is-auto-opening"), 320);
    window.setTimeout(() => loginModal.querySelector("input[name='username']")?.focus(), 80);
  }

  function closeLoginModal() {
    if (!loginModal) return;
    loginModal.classList.remove("is-open");
    loginModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
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
    document.body.classList.add("modal-open");
  }
  if (loginModal?.dataset.loginAutoOpen === "true") {
    let autoModalClosed = false;
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
    if (event.key === "Escape") closeLoginModal();
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
    input.closest(".topbar-search")?.setAttribute("data-tooltip", "Search the tables currently shown on this page.");
    input.addEventListener("input", () => filterTables(input.value, document));
  });

  document.querySelectorAll("th[data-sort]").forEach((header) => {
    header.dataset.tooltip = "Click to sort this column.";
    header.addEventListener("click", () => {
      const table = header.closest("table");
      const tbody = table.querySelector("tbody");
      const index = Array.from(header.parentNode.children).indexOf(header);
      const direction = header.dataset.direction === "asc" ? "desc" : "asc";
      header.dataset.direction = direction;
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
      const panel = document.querySelector('[data-schedule-view-panel="table"]');
      if (!panel) return;
      filterTables(input.value, panel);
      panel.querySelectorAll(".schedule-section-group").forEach((group) => {
        const rows = Array.from(group.querySelectorAll("tbody tr"));
        group.hidden = rows.length > 0 && rows.every((row) => row.hidden);
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

  document.querySelectorAll("a.button, button").forEach((control) => {
    if (control.dataset.tooltip) return;
    const key = normalize(control.textContent);
    if (actionTooltips[key]) control.dataset.tooltip = actionTooltips[key];
  });

  bindTooltips();
})();
