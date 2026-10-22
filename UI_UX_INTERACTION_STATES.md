# Interaction states - Task 1.4

## Scope and implementation

Extends the existing Task 1.2 palettes and Task 1.3 components. Previous uncommitted work was preserved. Changes are limited to shared CSS/JavaScript, isolated browser regression fixtures and documentation. No models, migrations, authentication policy, scheduling, publication, search scope or autosave behavior changed.

| Component/state | Convention and review result |
| --- | --- |
| Primary/secondary/destructive actions | Existing semantic hover/active/disabled foreground-background pairs retained. Disabled hover no longer adds a lift or shadow. Existing loading indicators and request handling retained. |
| Navigation/sidebar | Existing hover/selected styles preserved. Sidebar keyboard outline uses the light sidebar foreground token so the Light Mode focus token cannot disappear against the navy sidebar. |
| Forms/dropdowns/checkboxes | Existing native required validation and textual server errors retained. `aria-invalid` fields receive a stronger border as well as the existing error color. Checkboxes use the primary accent. Native select behavior unchanged. |
| Help | Existing and generated information icons become native `type=button` controls. Generated labels identify the field. Focus, hover and activation display the original help text; Escape/blur dismiss. `aria-describedby` connects the shared tooltip while visible, preserving other description IDs. Native buttons supply Enter/Space activation without custom key emulation. |
| Local sorting | Only `th[data-sort]` gains a native button, labelled by column. The existing comparator and row filtering are unchanged. `aria-sort` and a visible arrow describe current direction; prior column state clears. Server-side sort links are untouched. |
| Tabs/pagination/row and modal actions | Existing native button/link behavior retained. Shared focus outlines apply; explicit tab focus uses `--focus`. Existing tab arrow-key/roving-focus implementation remains unchanged. Unavailable pagination placeholders remain non-actions. |
| Disabled links | `aria-disabled=true` links have activation cancelled in capture phase. Native disabled buttons remain disabled; visual styling alone does not grant or enforce permissions. |
| Login dialog | Opening remembers the trigger and focuses username. Tab/Shift+Tab wrap among visible enabled controls, including help buttons. Escape/close restore the trigger (or a login trigger for initial open). Delayed initial focus checks that the dialog remains open. Explicit closure prevents the existing auto-open timer from reopening it. Authentication submission is untouched. |
| Feedback/loading | Existing textual success/warning/error/info messages and generation live status remain. Import retains its busy state, duplicate-submit prevention and reset behavior; no artificial progress was introduced. |
| Motion | Reduced-motion preference removes repeated animation and effectively removes transitions; status text remains visible when spinners stop. No extra animation introduced. |

The new generic focus selector also covers existing focusable controls and native summary disclosures. Decorative non-interactive elements are not added to the tab order. Native focus is replaced only where a visible outline is supplied.

## Browser regression harness

Run in PowerShell from the repository root:

```powershell
.\.venv\Scripts\python.exe tests/browser/run_interactions.py
# Optional fixture screenshots in the repository root:
.\.venv\Scripts\python.exe tests/browser/run_interactions.py --screenshots
```

Uses installed Windows Chrome or Edge, a fresh disposable profile and a synthetic local HTML fixture loading the actual application CSS and JavaScript. No dependencies, server, login account or real database required. Missing browser is reported as unavailable, not as a pass. The runner checks rendered result output and measured viewport widths.

Chrome **155.0.8059.85**: **22 checks passed in each of four configurations** (Light/Dark at measured 1360px/500px CSS width). Tests cover native help/sort control structure, focus-triggered help, accessible description, click activation, Escape dismissal, sort ordering/state, disabled-link cancellation, login initial focus, forward/backward focus wrapping excluding disabled controls, focus restoration, early-close timing and stored theme read/write. DOM focus and dispatched key events are used; these do not establish a complete physical-keyboard or assistive-technology walkthrough.

Initial 390px request was clamped by this Chrome build to 500px. Final runs assert actual 1360px/500px widths. True 390px mobile testing remains outstanding. Screenshots of the final fixture in all four configurations were inspected; temporary screenshots can be reproduced with the command above. This is fixture visual evidence, not a screenshot review of authenticated application pages.

The sandbox initially blocked creation of Chrome's disposable profile; the isolated browser runs succeeded outside it. No personal browser profile was used.

## Separate theme verification

- **Light Mode:** 22 browser assertions at each width passed. Screenshot review found readable primary/destructive/disabled controls, warning text and a visible help focus outline. Existing palette tests cover text/background and relevant control boundaries. Navy sidebar uses its own light focus foreground.
- **Dark Mode:** same 22 assertions at each width passed. Screenshot review found readable teal primary, pale destructive and muted disabled controls, warning text and visible help focus. Existing intentionally selected dark palette retained.
- No new hardcoded colors; semantic palette values and theme storage key unchanged. Full visual inspection of hover/active states across all application modules, screen-reader output and mobile behavior remain manual verification items.

## Django and static checks

- Full suite: **554 passed in 313.319 seconds**, zero failures, errors, skips or expected failures (baseline preserved).
- `python manage.py check`: no issues.
- `python manage.py makemigrations --check --dry-run`: no changes.
- `git diff --check`: pass, repeated at completion.
- Browser tests are additional to the Django suite and do not inflate its test count.

## Outstanding manual checklist

Repeat separately in Light and Dark Mode at desktop, true 390px and enlarged text:

1. Tab through navigation, sidebar disclosures, pagination, row actions, native selects, checkboxes and meeting tabs. Check visible focus and no clipping; verify existing tab arrow keys.
2. Use physical Enter/Space on help and local sort buttons; verify screen-reader labels, descriptions and sorting announcements. Test hover/touch, Escape dismissal and long tooltip edge placement.
3. Open login from each trigger and from validation-error/automatic opening. Tab and Shift+Tab through enabled controls, use Escape and close, confirm restored focus. Check password visibility control and normal authentication with an authorized test account.
4. Check disabled controls and real loading/error recovery during generation/import using disposable inputs. Confirm no accidental activation, duplicate requests or lost warnings.
5. Check required/invalid fields and non-color error text, all status messages and reduced-motion behavior on actual pages. Toggle/reload both themes.

Broader modal background isolation/screen-reader navigation, comprehensive tooltip hover persistence and cross-browser/mobile accessibility acceptance remain Task 6.1/Phase 6 review items. No claim of full WCAG conformance. Task 2.1 must wait for explicit approval.

## Status

Task 1.4 complete. Phase 1 implementation complete; progress 4/24. All Phase 2 and later tasks remain Not Started. Manual accessibility limitations above remain outstanding. No commits or deployment.
