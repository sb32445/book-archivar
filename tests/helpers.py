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


def make_pdf(path: Path, pages: list[list[str]], outline: list[tuple[str, int]] | None = None,
             title: str | None = None) -> Path:
    """Write a small text PDF by hand (no PDF library needed): one list of
    lines per page, optional bookmarks as (title, page index)."""
    objects: list[bytes] = []

    def add(body: str) -> int:
        objects.append(body.encode("latin-1"))
        return len(objects)

    catalog = add("")  # placeholders, filled below
    pages_obj = add("")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    for lines in pages:
        text = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
            f"({l.replace('(', '[').replace(')', ']')}) Tj T*" for l in lines
        ) + " ET"
        content = add(f"<< /Length {len(text)} >>\nstream\n{text}\nendstream")
        page_ids.append(add(
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"
        ))
    outlines_id = None
    if outline:
        outlines_id = add("")
        item_ids = [add("") for _ in outline]
        for i, (name, page) in enumerate(outline):
            parts = [f"/Title ({name})", f"/Parent {outlines_id} 0 R",
                     f"/Dest [{page_ids[page]} 0 R /Fit]"]
            if i > 0:
                parts.append(f"/Prev {item_ids[i - 1]} 0 R")
            if i < len(outline) - 1:
                parts.append(f"/Next {item_ids[i + 1]} 0 R")
            objects[item_ids[i] - 1] = f"<< {' '.join(parts)} >>".encode("latin-1")
        objects[outlines_id - 1] = (
            f"<< /Type /Outlines /First {item_ids[0]} 0 R /Last {item_ids[-1]} 0 R "
            f"/Count {len(outline)} >>"
        ).encode("latin-1")
    objects[pages_obj - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] /Count {len(page_ids)} >>"
    ).encode("latin-1")
    root = f"<< /Type /Catalog /Pages {pages_obj} 0 R" + (
        f" /Outlines {outlines_id} 0 R" if outlines_id else "") + " >>"
    objects[catalog - 1] = root.encode("latin-1")
    info = None
    if title:
        info = add(f"<< /Title ({title}) /Author (Pat Author) >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R"
    if info:
        trailer += f" /Info {info} 0 R"
    out += (trailer + f" >>\nstartxref\n{xref}\n%%EOF\n").encode()
    Path(path).write_bytes(bytes(out))
    return Path(path)
