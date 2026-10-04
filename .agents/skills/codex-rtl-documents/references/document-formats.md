# RTL Document Format Reference

Read only the sections relevant to the requested output format.

## DOCX

Apply all four levels:

| Level | Required setting |
|---|---|
| Section | Enable bidirectional page/section behavior where the library supports it. |
| Paragraph | `bidirectional: true` and `alignment: AlignmentType.START`. |
| Run | `rightToLeft: true` for Hebrew text runs. |
| Table | `visuallyRightToLeft: true`. |

Recommended helpers with the `docx` npm library:

```js
function rtlRun(text, options = {}) {
  return new TextRun({ text, rightToLeft: true, font: "Arial", ...options });
}

function rtlParagraph(children, options = {}) {
  return new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.START,
    children: Array.isArray(children) ? children : [children],
    ...options,
  });
}
```

Critical Word behavior:

- Inside a table with `visuallyRightToLeft: true`, absolute `RIGHT` alignment can render on
  the physical left in Microsoft Word because the table mirrors it.
- Use logical `START` for RTL paragraphs inside and outside tables.
- Define columns in logical reading order and let `visuallyRightToLeft` mirror them.
- Keep bullet and cell indentation consistent; stray indentation can look like alignment failure.
- Center only intentionally centered titles or labels.

Validate DOCX by inspecting OOXML and rendering with Word or LibreOffice. Confirm `w:bidi`,
`w:rtl`, `w:jc w:val="start"`, and `w:bidiVisual` where applicable.

## XLSX

- Set `ws.sheet_view.rightToLeft = True`.
- Use `Alignment(horizontal="right", readingOrder=2)` for Hebrew cells.
- Keep numeric cells numeric; do not convert values to reversed text.
- Place identifier/number columns first in logical order when they should appear rightmost.
- Check formulas, filters, merged cells, frozen panes, chart labels, and print layout.
- Open the workbook in Excel for final validation; XML validity alone is insufficient.

## PPTX

- Set RTL/bidirectional paragraph properties on every Hebrew text box and table cell.
- Right-align body text with logical RTL behavior; center only deliberate display text.
- Arrange title, body, images, arrows, and navigation in a right-to-left visual flow.
- Keep numbers, URLs, and English product names as LTR runs.
- Check overflow because Hebrew shaping can change line length.
- Render every slide to images or PDF and inspect text, tables, diagrams, and transitions.

## PDF

- Build RTL correctly in the source document or HTML before PDF export.
- Prefer a browser engine for HTML-to-PDF because it supports Unicode bidi and Hebrew shaping.
- Embed a Hebrew-capable font and verify selectable text order when accessibility matters.
- Check page direction, paragraphs, lists, tables, headers, footers, page numbers, and links.
- Render PDF pages to images for visual inspection and separately test text extraction order.

## Diagrams and raster images

- Render Hebrew labels through HTML/CSS in Chromium or another shaping-aware engine.
- Do not reverse strings manually or draw Hebrew directly with a renderer lacking bidi shaping.
- Keep diagram titles as real surrounding document headings when alignment with document margins matters.
- Preserve LTR islands inside labels with `dir="ltr"` or `unicode-bidi: isolate`.
- Inspect the final pixels for clipping, overlap, punctuation placement, and arrow direction.

Minimal browser-rendering pattern:

```html
<div class="diagram" dir="rtl" lang="he">
  <div class="node">שלב ראשון</div>
  <div class="node">גרסה <span dir="ltr">v2.4</span></div>
</div>
```

## Tables across formats

- Treat column order and text direction as separate concerns.
- Put the first logical column first in data structures; enable the format's RTL table mode.
- Use logical start alignment for Hebrew cells and suitable numeric alignment for numeric cells.
- Check header order, merged cells, wrapping, row height, and long unbroken LTR values.
- Validate in the real target application because preview engines frequently disagree on RTL tables.
