from pathlib import Path

from ebooklib import epub


def make_epub(path: Path, *, title="Test Book", author="Doe, Jane", single_file=False,
              with_toc=True) -> Path:
    """Build a small EPUB: either two chapter files, or one file with anchors."""
    book = epub.EpubBook()
    book.set_identifier(f"id-{path.stem}")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    if single_file:
        doc = epub.EpubHtml(title="All", file_name="all.xhtml", lang="en")
        doc.content = (
            "<h1 id='c1'>First</h1><p>Alpha <em>text</em> with ümlauts.</p>"
            "<h1 id='c2'>Second</h1><p>Beta text.</p>"
        )
        docs = [doc]
        toc = [epub.Link("all.xhtml#c1", "First", "c1"), epub.Link("all.xhtml#c2", "Second", "c2")]
    else:
        docs, toc = [], []
        for n, name in enumerate(["One", "Two"], 1):
            doc = epub.EpubHtml(title=name, file_name=f"ch{n}.xhtml", lang="en")
            doc.content = f"<h1>{name}</h1><p>Body of chapter {name}.</p><ul><li>item</li></ul>"
            docs.append(doc)
            toc.append(epub.Link(f"ch{n}.xhtml", name, f"ch{n}"))

    for doc in docs:
        book.add_item(doc)
    book.toc = toc if with_toc else []
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *docs]
    epub.write_epub(str(path), book)
    return path
