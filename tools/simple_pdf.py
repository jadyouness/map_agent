import sys
from pathlib import Path


PAGE_WIDTH = 612  # 8.5in * 72
PAGE_HEIGHT = 792  # 11in * 72
MARGIN = 72
FONT_SIZE = 12
LEADING = 14  # line height
MAX_LINES = int((PAGE_HEIGHT - 2 * MARGIN) // LEADING) - 1
MAX_COLS = 90  # rough wrap; Helvetica width not measured precisely


def escape_text(s: str) -> str:
    return s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')


def wrap_text(text: str, max_cols: int) -> list[str]:
    lines = []
    for para in text.splitlines():
        if not para.strip():
            lines.append("")
            continue
        current = []
        col = 0
        for word in para.split():
            wlen = len(word)
            if col == 0:
                current.append(word)
                col = wlen
            elif col + 1 + wlen <= max_cols:
                current.append(word)
                col += 1 + wlen
            else:
                lines.append(" ".join(current))
                current = [word]
                col = wlen
        if current:
            lines.append(" ".join(current))
    return lines


def paginate(lines: list[str]) -> list[list[str]]:
    pages = []
    page = []
    for line in lines:
        if len(page) >= MAX_LINES:
            pages.append(page)
            page = []
        page.append(line)
    if page:
        pages.append(page)
    return pages


def build_pdf_objects(pages: list[list[str]], title: str | None = None) -> bytes:
    objects = []

    # Font object (Helvetica)
    font_obj_index = len(objects) + 1
    objects.append(
        f"{font_obj_index} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode()
    )

    # Content streams (one per page)
    content_obj_indices = []
    for page_lines in pages:
        y_start = PAGE_HEIGHT - MARGIN - FONT_SIZE
        content = [
            b"BT\n",
            f"/F{font_obj_index} {FONT_SIZE} Tf\n".encode(),
            f"1 0 0 1 {MARGIN} {int(y_start)} Tm\n".encode(),
            f"{LEADING} TL\n".encode(),
        ]
        if title:
            t = escape_text(title)
            content.append(f"({t}) Tj\n".encode())
            content.append(b"T*\nT*\n")  # blank line after title
        for line in page_lines:
            t = escape_text(line)
            content.append(f"({t}) Tj\n".encode())
            content.append(b"T*\n")
        content.append(b"ET\n")
        stream = b"".join(content)
        stream_obj_index = len(objects) + 1
        content_obj_indices.append(stream_obj_index)
        objects.append(
            (
                f"{stream_obj_index} 0 obj\n".encode()
                + f"<< /Length {len(stream)} >>\nstream\n".encode()
                + stream
                + b"endstream\nendobj\n"
            )
        )

    # Page objects
    page_obj_indices = []
    for content_idx in content_obj_indices:
        page_obj_index = len(objects) + 1
        page_obj_indices.append(page_obj_index)
        objects.append(
            (
                f"{page_obj_index} 0 obj\n".encode()
                + (
                    f"<< /Type /Page /Parent {{PAGES}} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                    f"/Contents {content_idx} 0 R /Resources << /Font << /F{font_obj_index} {font_obj_index} 0 R >> >> >>\n"
                ).encode()
                + b"endobj\n"
            )
        )

    # Pages tree
    pages_obj_index = len(objects) + 1
    kids = " ".join(f"{idx} 0 R" for idx in page_obj_indices)
    objects.append(
        (
            f"{pages_obj_index} 0 obj\n".encode()
            + f"<< /Type /Pages /Count {len(page_obj_indices)} /Kids [ {kids} ] >>\n".encode()
            + b"endobj\n"
        )
    )

    # Fix parent references in page objects now that pages id is known
    fixed_objects = []
    for obj in objects:
        fixed_objects.append(obj.replace(b"{PAGES}", str(pages_obj_index).encode()))
    objects = fixed_objects

    # Catalog
    catalog_obj_index = len(objects) + 1
    objects.append(
        f"{catalog_obj_index} 0 obj\n<< /Type /Catalog /Pages {pages_obj_index} 0 R >>\nendobj\n".encode()
    )

    # Assemble file with xref
    result = bytearray()
    result.extend(b"%PDF-1.4\n")
    offsets = [0]  # object 0 is the free object
    for obj in objects:
        offsets.append(len(result))
        result.extend(obj)
    xref_start = len(result)
    result.extend(f"xref\n0 {len(objects)+1}\n".encode())
    # object 0 (free)
    result.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        result.extend(f"{off:010d} 00000 n \n".encode())
    # trailer
    result.extend(
        (
            f"trailer\n<< /Size {len(objects)+1} /Root {catalog_obj_index} 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
        ).encode()
    )
    return bytes(result)


def md_to_text(md: str) -> str:
    # Minimal transform: drop leading '#' and trim
    lines = []
    for line in md.splitlines():
        l = line.strip()
        if l.startswith('#'):
            l = l.lstrip('#').strip()
        # Convert markdown bullets to simple dashes
        if l.startswith('- '):
            l = '* ' + l[2:]
        lines.append(l)
    return "\n".join(lines).strip()


def generate_pdf_from_md(md_path: Path, out_pdf: Path, title: str | None = None) -> None:
    text = md_to_text(md_path.read_text(encoding='utf-8'))
    lines = wrap_text(text, MAX_COLS)
    pages = paginate(lines)
    if not pages:
        pages = [["(empty)"]]
    pdf_bytes = build_pdf_objects(pages, title=title)
    out_pdf.write_bytes(pdf_bytes)


def main():
    if len(sys.argv) < 3:
        print("Usage: python tools/simple_pdf.py <input_md> <output_pdf> [title]", file=sys.stderr)
        sys.exit(2)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    title = sys.argv[3] if len(sys.argv) > 3 else None
    out.parent.mkdir(parents=True, exist_ok=True)
    generate_pdf_from_md(inp, out, title)
    print(f"Wrote: {out}")


if __name__ == '__main__':
    main()

