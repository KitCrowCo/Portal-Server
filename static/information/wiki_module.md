# Wiki Module

A markdown-based knowledge base with a built-in file manager, wiki-style linking, and per-page access control. Every page is a plain text file on disk under `data/_common/` — nothing is locked into a database, so your content is portable and readable even without the server running.

## Opening the Wiki

Click the Wiki card on your dashboard, or open it from the module launcher. It occupies its own tab with three panels:

- **Left** — the file tree. Click a file to open it in the main area; click a folder to expand it.
- **Center** — the current page, in Edit, Preview, or Split view.
- **Right** — contextual info (file size, word count, tags) plus quick references for Markdown and Graphviz syntax.

## Creating Pages

Click the `+` button above the file tree. You can create:
- **A file** — type a name. If you don't include a file extension, `.md` is assumed and the extension is hidden everywhere the page is displayed (tabs, tree, links) — `home` and `home.md` are the same page, and it's always shown as just `home`. If you *do* include an extension (`notes.txt`, `diagram.svg`), it's created and treated exactly as written.
- **A folder** — organize pages into a hierarchy just like a filesystem, because it is one.
- **An upload** — single files, multiple files, or an entire folder (via your browser's folder-upload picker).

## Editing

The editor has three view modes, switchable from the toolbar:
- **Edit** — a plain text editor with **live inline formatting**: typing `**bold**` shows it bold while keeping the asterisks visible, headers render larger, links get colored — all without altering your actual source text. This is meant to make raw markdown source pleasant to write in, not to hide the syntax from you.
- **Preview** — the fully rendered page, exactly as it will display to readers, with all markdown syntax converted to formatted output.
- **Split** — both side by side. This is the default for new documents.

Editor toolbar icons (hover for a tooltip; tap the `?` icon for a full legend):
- Save now, zoom in/out, toggle word wrap, toggle font (monospace/prose), toggle a visible border around the page, search within the document, document info (word/line count), a quick-insert bar for common markdown snippets, download the raw source, and print.

Autosave fires automatically a couple of seconds after you stop typing. `Ctrl+S` forces an immediate save.

## Wiki Links

`[[page]]` links to another page by name — no extension needed if it's a `.md` page (`[[home]]` finds `home.md`). If you're linking to something that isn't markdown (`[[notes.txt]]`, `[[data.csv]]`), include the extension explicitly — the link resolves to exactly what you typed, it does not silently add `.md` on top of an extension you already gave it.

- `[[page|Display Text]]` — link to `page` but show custom link text.
- `![[image.png]]` — embed an image, video, or PDF inline by extension. Falls back to a download-style link icon for anything else.
- Relative links: `[[./sibling]]` and `[[../parent-folder/page]]` resolve relative to the current page's folder, not the wiki root.

Links to pages that don't exist yet show up in orange — click one to be taken there and start writing (the page won't be auto-created for you; navigating to a non-existent page and writing something is what creates it).

## Markdown Reference

Beyond standard Markdown (headers, bold/italic, lists, tables, code blocks, blockquotes, images, links), this wiki supports a few extensions:

| Syntax | Effect |
|---|---|
| `~~strike~~` | ~~strikethrough~~ |
| `==highlight==` | highlighted text |
| `^super^` / `~sub~` | superscript / subscript |
| `# H1` through `###### H6` | headers, auto-underlined |
| `> quote` | blockquote |
| `- [ ] task` / `- [x] done` | checkbox task list |
| `[^note]` ... `[^note]: text` | footnotes, collected at the bottom of the page |
| \`code\` / \`\`\`fenced\`\`\` | inline and block code, never interpreted as markdown |
| `:::details Title` ... `:::` | a collapsible section; can be nested |
| ` ```dot ... ``` ` | a Graphviz DOT diagram, rendered as an inline SVG |
| `Term\n: Definition` | definition list |
| `\*` `\_` `` \` `` etc. | escape a character so it displays literally |

### Tab Sets

Turn a section into a tabbed interface:
```
### Section Title {.tabset}
#### Tab One
Content for tab one.
#### Tab Two
Content for tab two.
{end.tabset}
```
A tabset ends at an explicit `{end.tabset}` marker, or automatically at the next header of the same level or shallower (in the example above, the next `###` or higher), or at the end of the document — whichever comes first. `{end.tabset}` is only needed if you want the tabset to end *before* the next same-level header would naturally close it.

### Layout Blocks

For laying out content side-by-side rather than in the normal top-to-bottom flow:
- `((row))` ... `(())` — lays its contents out horizontally, wrapping to a new line if there isn't room.
- `((col))` ... `(())` — lays its contents out vertically as a stack.
- `((grid: 3))` ... `(())` — a strict N-column grid (replace `3` with however many columns you want).

These can be nested freely — a `((row))` containing two `((col))` blocks makes two vertical stacks side by side, for example. Every opening block needs exactly one matching `(())` to close it; as long as the count matches, nesting resolves correctly regardless of how deep it goes.

## Access Control

Two layers, from broad to specific:

1. **Global roles** (Wiki Settings, gear icon) — "Edit Access" and "View Access," each a comma-separated list of roles (`admin`, `moderator`, `user`, `guest`). Leave View Access empty to allow any logged-in user to view; Edit Access defaults to `admin` only.
2. **Per-page rules** (Settings → Per-Page Access Rules) — narrow access further for a specific path or a tag you've applied to a page (right-click a page in the tree → set tags). Whitelist mode means *only* the listed users/roles can access; blacklist mode means the listed ones are denied and everyone else can. A page with no matching rule falls back to the global roles only.

The special tag `public` marks a page as reachable through the **public wiki** (see below) with no login required.

## Public Wiki

If enabled, a subset of pages are reachable without logging in at `/public/wiki/{page}`, themed with the server's admin-configured default theme (not any individual user's personal theme). Only pages explicitly tagged `public` are reachable this way:

- A `[[wiki link]]` on a public page to another page only becomes a working link if that target is *also* tagged public — otherwise it renders as struck-through, non-clickable text, so a public page can never accidentally leak the existence or content of a private one.
- Direct URL guesses to a non-public page return a plain 404, same as if the page didn't exist.
- The public wiki view has no editor, no file tree, and no access to anything outside the whitelist — it's read-only rendering of exactly the pages you've chosen to expose.

This is useful for things like a public project page, a shared recipe, or documentation you want to link to from outside the server, without exposing your entire wiki.

## File Types Beyond Markdown

The wiki can display (not necessarily edit) several other file types directly in the tab: images, PDFs (inline viewer), and SVGs. Anything else falls back to a plain-text view through the same editor, syntax-highlighted where recognized (Python, JSON, YAML, etc. get a `\`\`\`` code fence treatment automatically when opened).

## Settings Reference (gear icon)

| Setting | Effect |
|---|---|
| Wiki Title | Display name shown in the wiki's own left panel header |
| Edit Access (roles) | Who can create/edit/delete pages |
| View Access (roles) | Who can view the wiki at all (empty = any logged-in user) |
| File visibility | Show only markdown pages in the tree, or all file types |
| Wiki-link navigation | Clicking a link replaces the current tab's content, or opens a new tab each time |
| Paragraph breaks | Whether every line break becomes its own paragraph, or only blank lines do (standard Markdown behavior) |
