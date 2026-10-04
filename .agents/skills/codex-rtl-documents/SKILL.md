---
name: codex-rtl-documents
description: >
  Enforces correct Hebrew and other right-to-left output across Codex chat,
  IDE panels, webviews, HTML, Word, Excel, PowerPoint, PDF, tables, diagrams,
  and generated images. Use whenever the requested or source content is RTL,
  when mixed Hebrew/LTR text must remain readable, or when the user reports
  reversed text, wrong alignment, mirrored columns, or broken RTL layout.
---

# Codex RTL Documents

Produce RTL output whose text direction, alignment, layout order, and mixed-language
content all agree. A right-aligned paragraph is not necessarily RTL; validate the
underlying direction and the rendered result.

## Operating workflow

1. Detect the output surface: chat, IDE/webview, HTML, office document, PDF, or image.
2. Apply the universal RTL rules below.
3. Apply the matching surface rules. For document formats, read
   [references/document-formats.md](references/document-formats.md).
4. Preserve LTR islands for code, paths, URLs, identifiers, numbers, and formulas.
5. Validate structure and rendering before delivery.

Do not ask whether RTL is required when the content or audience is clearly Hebrew.

## Universal RTL rules

- Set direction at the outermost supported page, section, or container level.
- Use logical start/end alignment and spacing instead of physical left/right values.
- Keep Hebrew paragraphs RTL from the first character; do not rely on visual alignment alone.
- Keep code, commands, URLs, paths, email addresses, versions, and API names LTR.
- Keep punctuation with its logical sentence and test mixed Hebrew, Latin, and numbers.
- Put the logical first table column first; use the renderer's RTL table feature instead
  of manually reversing every row.
- Never reverse Hebrew strings character by character.
- Never claim correctness from source inspection alone when a real renderer is available.

## Codex chat and Markdown

- Answer Hebrew users in Hebrew unless they request another language.
- Wrap every substantial Hebrew heading, paragraph, and list item with an actual U+2067
  RIGHT-TO-LEFT ISOLATE at the start and U+2069 POP DIRECTIONAL ISOLATE at the end.
- Do not print the codepoint names or visible placeholders in the final response.
- Do not wrap fenced code blocks or standalone LTR values in RTL isolates.
- Put paths, commands, URLs, versions, and identifiers in separate Markdown code spans or
  code blocks when practical.
- Do not use raw HTML such as `<div dir="rtl">` to control normal Codex chat direction;
  chat renderers may escape it.
- Prefer short Hebrew-only sentences where a mixed-language construction is unnecessary.

Example logical structure:

```text
[RTL isolate]כותרת בעברית[pop isolate]

[RTL isolate]פסקה בעברית שמפנה אל הקובץ הבא:[pop isolate]
`C:\work\report.docx`
```

## IDE panels and generated webviews

- Apply RTL to the document preview, chat panel, generated page, and editable Hebrew area.
- Do not alter code-editor direction or reverse source-code syntax.
- Mirror navigation and content flow only where the product's Hebrew locale requires it.
- Use logical CSS properties so one stylesheet remains correct in both directions.
- If the host IDE cannot be globally restyled, state that limitation and still make every
  generated artifact and supported panel RTL-correct.

## HTML and web applications

Set the document language and direction at the root:

```html
<html lang="he" dir="rtl">
```

Use logical CSS:

```css
.page {
  direction: rtl;
  text-align: start;
  padding-inline: 1rem;
  margin-inline: auto;
}

code,
pre,
.ltr {
  direction: ltr;
  text-align: start;
  unicode-bidi: isolate;
}
```

- Use `margin-inline-*`, `padding-inline-*`, `inset-inline-*`, and `border-inline-*`.
- Mark local LTR islands with `dir="ltr"`; do not switch the whole page to LTR.
- Check flex/grid order, icons, back/next controls, forms, validation messages, and tables.
- Test narrow and wide viewports with real Hebrew and mixed-direction content.

## Documents and office files

Read [references/document-formats.md](references/document-formats.md) before creating or
editing DOCX, XLSX, PPTX, PDF, tables, diagrams, or images containing Hebrew. Combine this
skill with the format-specific document skill used for file mechanics.

Non-negotiable principles:

- DOCX requires RTL at section, paragraph, run, and table levels.
- RTL table paragraphs use logical `START`, not absolute `RIGHT`.
- XLSX requires an RTL sheet view and reading order on Hebrew cells.
- PPTX requires RTL text plus an intentionally mirrored visual reading flow.
- PDF correctness is established in the source layout before export, then verified in the PDF.
- Hebrew diagrams and raster images use a real browser or shaping-aware renderer, never
  manual character reversal in PIL or matplotlib.

## Mixed-direction content

- Treat numbers, currency, dates, phone numbers, formulas, and Latin product names as local
  LTR runs inside the RTL sentence.
- Keep number-unit pairs visually stable, especially currency, percentages, and versions.
- Avoid starting a Hebrew paragraph with an unisolated LTR token.
- Inspect parentheses, slashes, colons, hyphens, and trailing punctuation after rendering.
- Use explicit isolation when automatic Unicode bidi behavior produces ambiguity.

## Validation ladder

Use the strongest checks available for the surface:

1. Structural: confirm direction, logical alignment, and table-order properties.
2. Content: confirm Hebrew is not manually reversed and LTR islands remain intact.
3. Rendered: open or convert with the real target renderer and inspect representative pages.
4. Responsive: for webviews, inspect desktop and mobile widths.
5. Regression: include at least one Hebrew-only, one LTR-only, and one mixed-direction case.

Do not use a preview known to mishandle RTL as the only validation signal.

## Pre-delivery checklist

- [ ] The outer page, section, sheet, slide, or container is RTL.
- [ ] Hebrew paragraphs use logical start alignment and RTL direction.
- [ ] Code, paths, URLs, identifiers, numbers, and formulas remain readable LTR islands.
- [ ] Tables have correct visual column order and correctly aligned cell paragraphs.
- [ ] Navigation, icons, spacing, and controls follow the intended RTL flow.
- [ ] Hebrew diagrams/images were rendered by a shaping-aware engine.
- [ ] A real rendered output was inspected where the format permits it.
- [ ] No Hebrew or mixed-direction text is clipped, overlapped, or reversed.
