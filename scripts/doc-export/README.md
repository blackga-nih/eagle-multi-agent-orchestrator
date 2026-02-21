# Doc Export

Converts chat conversations to PDF or Word documents with NCI branding.

## Usage

```js
import { exportToPdf } from './pdf-export';    // requires: jspdf
import { exportToDocx } from './docx-export';  // requires: docx
import { translateDocx } from './docx';        // requires: jszip, fast-xml-parser

const messages = [{ role: 'user', content: 'Hello' }, { role: 'assistant', content: '**Hi!**' }];
const pdfBlob = await exportToPdf(messages, { title: 'Session Export' });
const docxBlob = await exportToDocx(messages, { title: 'Session Export' });
```

Both functions accept markdown in message content (headings, bold, italic, code blocks, lists) and produce branded documents with NCI headers, footers, and page numbers. Tests are in `test/`.
