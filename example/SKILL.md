---
name: book-archivar
description: "Read and search the user's own book library through the book-archivar MCP server: find passages, list chapters, quote exact text."
version: 1.0.0
---

<!--
Template skill for agents that support SKILL.md-style instructions (Claude Code,
Hermes, ...). Copy it into your agent's skills folder and adapt the wording.
MCP clients often prefix tool names with the server name (for example
`mcp__books__search_books`); the tool names below are the bare ones.
-->

# book-archivar: the user's book library

You have read-only access to the user's own book library through the `book-archivar` MCP server. When a conversation touches one of the archived books, use the tools instead of relying on what you remember: they return the exact original text.

## Tools

| Tool | Use it to |
|---|---|
| `list_books` | see which books are archived (slug, title, author, language) |
| `get_book_info` | get author, language, number of chapters and size of one book |
| `search_books` | find passages. Optional `book_slug` limits it to one book. `mode`: `hybrid` (default, meaning plus exact words), `semantic` (meaning only), `keyword` (exact words only, best for names and verbatim quotes) |
| `list_chapters` | get a book's chapters as `{index, title}` |
| `get_chapter` | read a chapter by title or by 0-based index. Long chapters come in windows of 30,000 characters |

## Workflow

1. **A question about content or themes** -> `search_books` (hybrid), limited with `book_slug` if the book is known.
2. **A verbatim quote or a proper name** -> `search_books` with `mode="keyword"` and the exact phrase.
3. **Reading a chapter** -> every search hit carries `chapter_index` and `chapter_title`; pass one of them to `get_chapter`. If the text ends with `[... N more characters. Call again with offset=X to continue.]`, call `get_chapter` again with that `offset` until you have everything. Never continue a chapter from memory.
4. **"What do I have?"** -> `list_books`.

## Quoting

Weave quotes into your answer and name book and chapter. Do not paste raw tool output. Never invent a quote you could look up.

## When the user says a sentence is in the book

Do not wave it away: look it up. A search hit is a pointer, not a verdict. Read the returned chunk (and, if needed, the chapter) before claiming that a passage does not exist, and do not judge by the distance score alone. If the user names a quote and the tools give no clear "not found", assume the sentence is in the book and find it.

## Known limits

- Books whose files have no headings get chapters named "Section N"; work with `chapter_index` there.
- Chapter titles can repeat in some books; prefer the index from `list_chapters` when a title is ambiguous.
- The archive is read-only: you cannot add, change or delete books.
