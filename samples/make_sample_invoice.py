"""Generates sample-invoice.pdf - a test invoice with deliberate mistakes.

Planted problems:
  - "Website hosting": 12 x 25.00 should be 300.00, but shows 325.00
  - "Logo design" appears twice (duplicate)
  - Line items add to 1,925.00 but subtotal says 1,875.00
  - Total doesn't equal subtotal + tax
  - Due date is before the invoice date
  - "Misc. service fee" is vague

Run:  python samples/make_sample_invoice.py
Uses only the Python standard library (writes a minimal PDF by hand).
"""

from pathlib import Path

LINES = [
    ("BrightPixel Studio", 20, 18, True),
    ("221 Market Street, Austin, TX 78701  |  billing@brightpixel.example", 9, 18, False),
    ("INVOICE", 16, 30, True),
    ("Invoice #: BP-2026-0417", 10, 16, False),
    ("Invoice date: 2026-11-10", 10, 14, False),
    ("Due date: 2026-11-01", 10, 14, False),
    ("Bill to: Greenleaf Bakery, 9 Oak Avenue, Austin, TX 78704", 10, 14, False),
    ("Description                         Qty    Unit price      Amount", 10, 30, True),
    ("Logo design                           1        800.00      800.00", 10, 16, False),
    ("Website hosting (monthly)            12         25.00      325.00", 10, 14, False),
    ("Logo design                           1        800.00      800.00", 10, 14, False),
    ("Misc. service fee                     1          0.00        0.00", 10, 14, False),
    ("Subtotal:                                                 1,875.00", 10, 28, True),
    ("Sales tax (8.25%):                                          154.69", 10, 14, False),
    ("TOTAL DUE (USD):                                          2,100.00", 11, 16, True),
    ("Payment terms: Net 15. Thank you for your business!", 9, 30, False),
]


def build_pdf() -> bytes:
    y = 760
    ops = []
    for text, size, gap, bold in LINES:
        y -= gap
        font = "F2" if bold else "F1"
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"BT /{font} {size} Tf 50 {y} Td ({safe}) Tj ET")
    stream = "\n".join(ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


if __name__ == "__main__":
    target = Path(__file__).parent / "sample-invoice.pdf"
    target.write_bytes(build_pdf())
    print(f"Wrote {target}")
