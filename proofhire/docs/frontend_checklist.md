# Frontend manual checklist (Member 2)

Run at 360 px width (browser dev tools) and at desktop width, in light and dark theme.
Start the API (`uvicorn`) first. The app has no built-in example listings; every screen uses real API data.

## Setup
- [ ] `cp .env.example .env` and set `VITE_API_BASE_URL`
- [ ] `npm install` then `npm run dev`; `npm run build` completes with no errors

## Assessment flow (Section 1.6)
- [ ] Landing shows no example listing; "Assess a listing" opens /assess
- [ ] Paste the team's suspicious test listing (from demo_data/) and submit: gauge, High risk badge, evidence panel (Observed and Model-derived groups), checklist, summary
- [ ] Click a key-concern chip (E1): page scrolls to and highlights that evidence item
- [ ] Explanation badge reads "Auto-generated" (template) or "AI-written" (llm)
- [ ] Submit a more complete listing: lower risk; evidence shows decreasing-risk items
- [ ] An unknown /assessment/:id shows the error banner with Retry

## Resilience
- [ ] Offline (dev tools -> Offline): submit shows an error banner; Retry works after going back online
- [ ] Cold start: with the API stopped, the "Server is waking up" banner appears after about 3 s; Analyse is disabled; it enables when the API answers or after 12 attempts
- [ ] Every page shows a skeleton while loading, an error banner with Retry on failure, and an empty state when a list is empty
- [ ] 429 (more than 10 assessments per minute) shows the rate-limit message
- [ ] 422 field errors appear under the matching inputs

## Accounts and saving
- [ ] Register, sign out, sign in; `ph_token` set in localStorage; redirect returns to the page you came from
- [ ] /saved redirects to /login when signed out; works when signed in
- [ ] Saved: risk filter, pagination, delete with confirm
- [ ] Checklist toggle: optimistic update; stop the API and toggle to confirm the rollback and error message
- [ ] Anonymous assessment: `ph_owner_tokens` holds the token and the checklist PATCH sends `X-Owner-Token`

## Compare and report
- [ ] Compare two assessments by id through the API; the better side shows a "Better" label
- [ ] Report modal: type, 10-1000 character counter, Escape closes, focus stays inside, success toast
- [ ] Reporting the same listing twice shows "You already reported this."

## Dashboard and admin
- [ ] Dashboard: KPI cards, donut, trend lines, top-evidence bars, metrics, confusion matrix
- [ ] The "Metrics are from a synthetic benchmark." badge is visible
- [ ] Toggle "Include seeded demo data" changes the numbers; default shows real stored data only
- [ ] Any metric the API does not provide reads "Not available" (never a made-up number)
- [ ] /admin/reports: admin can approve or reject with a note; a non-admin sees "no access"

## Accessibility and layout
- [ ] No horizontal scroll at 360 px on every route
- [ ] Compare table stacks into cards below 640 px
- [ ] Risk is shown with an icon and text everywhere, never colour alone
- [ ] Keyboard only: skip link, visible focus ring, menu button, modal focus trap
- [ ] Footer disclaimer appears on every page: "ProofHire gives a risk estimate, not a verification of the employer."

## Motion and visual pass (11 Oct 2026)
Test once normally, then again with the OS setting "Reduce motion" turned on.
- [ ] Landing hero: the listing scan highlights each flagged phrase (with its E-number tag), findings list in, then the gauge counts up to 92%
- [ ] Landing: stats count up when scrolled into view; signal cards, timeline and FAQ reveal as you scroll; timeline line draws between steps
- [ ] FAQ: each item opens and closes with the keyboard (Enter/Space), chevron rotates
- [ ] Route changes fade and slide in, scroll resets to top, and focus moves to the page (no visible outline)
- [ ] Report: gauge arcs draw, marker sweeps to the score, number counts up; the screen-reader label still says the final score
- [ ] Report: sticky "jump to" bar highlights the section in view; clicking a link scrolls and moves focus to that section
- [ ] Evidence filter chips (All / Increases risk / Decreases risk) change the list; counts are correct; a key-concern chip (E1) clears the filter and scrolls to its item
- [ ] Dashboard: KPI numbers and metric values count up; charts animate in; with Reduce motion on, charts and numbers appear instantly
- [ ] Cards lift on hover, buttons press, checkbox pops, modal and toast animate in
- [ ] Navbar gains a shadow after scrolling; link underline slides in; footer shows the disclaimer on every page
- [ ] 360 px: no horizontal page scroll (the report "jump to" bar scrolls sideways inside itself, which is expected); hero stacks above the scan card
- [ ] Light and dark theme both readable; hero stays navy in both

## v1.1.1 hardening pass

Added: request cancellation (AbortController, stale responses ignored), session-expiry handling (401 on a sent token signs the user out with a notice on Login), assessment response normalisation, expandable "Why this counts" evidence with from-your-listing vs model-derived grouping, score context and boundary note, missing-details list, confirm dialogs for delete and moderation (shared focus trap), icon-plus-text status badges, form error summary with focus and links, click-to-reveal help tips, duplicate-submit guard, live-vs-demo data label on the Dashboard, 360 px chart label fixes, 44 px touch targets on coarse pointers, and `npm test` (node:test, no new dependencies).

Deliberately NOT done (conflict with earlier rules or the guidebook): removing v1.1 animations; a "verified" evidence category, confidence values or source fields (the API returns none); search in Saved/Admin; changing the spec-fixed storage keys or `/assessment/:id` URLs; ESLint/Prettier/Vitest/Testing Library; dashboard fields that need Part A/B data (sample size, evaluation date, methodology, recent assessments).

Verification: `npm test` runs 28 logic tests (validation, API client, normalisers, insights, report marking, score drivers, sorting, palette filtering). A syntax-only TypeScript parse and a relative-import check were run. `npm run build`, the dev server and browser/viewport checks were NOT run (npm registry unreachable here), so rendering, CSS and focus behaviour are unverified.

## v1.2 additions (manual checks)
- [ ] Report: marked phrases in "Listing with evidence marked"; click one -> jumps to its evidence card; "Show in listing" on a card jumps back
- [ ] Report: signals whose text is not in the description (for example the contact email) are listed under the marked listing
- [ ] Report: "What moved the estimate" shows two separate groups (severity for observed, weight for model)
- [ ] Report: scroll past the score -> slim mini score bar appears; scroll up -> it hides
- [ ] Report: Copy link shows a toast; Print or save as PDF gives a clean one-column page without nav or buttons
- [ ] Ctrl/Cmd+K and "/" open the command palette; arrows + Enter work; typing a number offers "Open assessment #N"; Esc closes
- [ ] "?" shows shortcuts; "g" then a/c/s/d/b/h navigates; none of them fire while typing in a field
- [ ] Toasts stack bottom-right (delete, report, moderation, copy link)
- [ ] Saved: risk chips show counts; sort changes order; table layout available from 720 px up; delete asks for confirmation
- [ ] Dashboard: 7/14/30-day range changes the trend chart and KPI sparklines
- [ ] Assess: "What to paste" guide visible; Landing hero panel highlight rotates and stops with reduced motion
