# WatchUp WP-3.4 Brand Asset Design QA

## Evidence

- Source visual truth: `C:\Users\Master_PC\.codex\codex-remote-attachments\01a10392-6dd8-7561-9e5b-bb581bc4335e\1459FDC7-045B-46D8-86B8-C13C1A750BF5\1-Photo-1.jpg` and `2-Photo-2.jpg`.
- Implementation: `http://127.0.0.1:4173/#home`.
- Browser-rendered implementation: captured in the Codex in-app browser during this QA run in mobile and desktop states; the browser surface does not persist a local screenshot path.
- Viewports: 390 × 844 and 1440 × 900 CSS pixels, device scale factor 1.
- Source pixels: hero 784 × 1168; owner icon 1280 × 1280. Assets are rendered with responsive `object-fit: cover` and explicit focal positions.
- State: synthetic single-child POC, Hebrew RTL, no live data.

## Full-view comparison

The supplied child illustration is now the dominant top-of-app visual. The supplied green eye icon replaces the previous generated logo in the sidebar, mobile header, favicon and Apple touch icon. The surrounding interface retains WatchUp's existing alert-first structure.

## Focused-region comparison

- Mobile Hero: the child's full head, face, phone and seated pose remain visible; the green source icon anchors the lower crop.
- Desktop Hero: the image and product copy share a fixed 320px band, keeping the dashboard summary visible above the fold.
- Brand icon: the exact supplied owner asset is used at every app-logo and favicon reference.

## Required fidelity surfaces

- Typography: existing Hebrew hierarchy remains readable over the dark-green Hero with no unwanted wrapping.
- Spacing and layout: no horizontal overflow at either viewport; the Hero preserves rounded corners and consistent dashboard rhythm.
- Colors and tokens: the Hero uses dark greens sampled from the supplied identity while preserving white-text contrast.
- Image quality: both supplied images are used directly, without regenerated approximations, stretching or placeholder artwork.
- Copy: the existing synthetic-data and read-only disclosures remain visible and accurate.

## Interaction and accessibility checks

- Navigation and existing dashboard interactions remain functional.
- The Hero image has descriptive Hebrew alternative text; decorative logo instances remain appropriately empty or branded.
- Browser console errors: 0.
- Horizontal overflow: none at 375px and 1425px client widths.

## Comparison history

1. P1: the first mobile crop removed the top of the child's head. Fixed by moving the focal position to 13% and increasing the image region to 270px. Post-fix evidence shows the complete head and seated pose.
2. P1: the first desktop layout inherited the portrait image's height and produced a 677px Hero with low-contrast copy. Fixed with a 320px Hero, fixed image height and a dark-green background.
3. P2: the corrected desktop height still clipped the child's hair. Fixed by moving the desktop focal position to 12%. Post-fix evidence shows the complete head and balanced composition.

## Follow-up polish

- P3: revisit the final Hero crop after the wider dashboard redesign is selected from Pinterest references.

final result: passed
# WP-3.5 Design QA — 05.10.2026

- Verified Hebrew document language and RTL direction.
- Verified dashboard, alerts, groups/contacts, event detail and monitoring settings with synthetic data only.
- Verified mobile at 390×844 and desktop at 1440×1000.
- Verified no horizontal overflow at either breakpoint.
- Verified groups/contacts tab switching and event-detail navigation.
- Verified keyboard focus treatment, semantic headings, labels and status announcements.
- Raised all visible buttons and navigation items to a minimum 44px touch target.
- Browser console: no warnings or errors during the tested flow.
- Automated tests: web 7/7; API 29/29.
- No deployment, VPS mutation, real phone pairing or production data was used.
