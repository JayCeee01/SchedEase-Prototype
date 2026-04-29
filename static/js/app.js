(function () {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("schedease-theme");
  if (savedTheme) root.dataset.theme = savedTheme;

  const fieldTooltips = {
    "username": "Enter the username assigned to your account.",
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
    "run genetic algorithm": "Create a new schedule using the saved settings.",
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

  document.querySelectorAll(".nav-group").forEach((nav) => {
    const savedScroll = sessionStorage.getItem("schedease-sidebar-scroll");
    if (savedScroll) nav.scrollTop = Number(savedScroll);
    nav.addEventListener("scroll", () => {
      sessionStorage.setItem("schedease-sidebar-scroll", String(nav.scrollTop));
    });
    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        sessionStorage.setItem("schedease-sidebar-scroll", String(nav.scrollTop));
      });
    });
  });

  const currentPath = window.location.pathname;
  document.querySelectorAll(".nav-group a").forEach((link) => {
    link.dataset.tooltip = link.textContent.trim();
    link.setAttribute("title", link.textContent.trim());
    link.dataset.tooltipPlacement = "right";
    if (link.getAttribute("href") === currentPath) link.classList.add("is-active");
  });

  document.querySelectorAll(".toast-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".toast")?.remove());
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
    form.querySelectorAll("label").forEach((label) => {
      if (label.querySelector(".info-icon")) return;
      const text = label.textContent.trim().replace(":", "");
      const icon = document.createElement("span");
      icon.className = "info-icon";
      icon.textContent = "i";
      icon.dataset.tooltip = tooltipForLabel(label);
      label.appendChild(icon);
    });

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

  document.querySelectorAll("a.button, button").forEach((control) => {
    if (control.dataset.tooltip) return;
    const key = normalize(control.textContent);
    if (actionTooltips[key]) control.dataset.tooltip = actionTooltips[key];
  });

  bindTooltips();
})();
