"""Regenerate the portable README figures using only Python's standard library.

Run from any directory: python docs/diagrams/render.py
Coordinates and labels below are the editable source; no diagram service,
browser script, web font, image asset, or Graphviz installation is required.
"""

from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
INK = "#153f39"
MUTED = "#506862"
PAPER = "#faf9f5"
LINE = "#bdcec5"
AMBER = "#986417"


class Figure:
    """Small, explicit SVG layout builder for these two technical figures."""

    def __init__(self, height, title, description):
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" '
            f'viewBox="0 0 1000 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            f'<desc id="desc">{escape(description)}</desc>',
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{MUTED}"/></marker></defs>',
            f'<rect width="1000" height="{height}" rx="16" fill="{PAPER}"/>',
            '<g font-family="DejaVu Sans, Arial, sans-serif">',
        ]

    def text(self, x, y, value, size=16, weight=400, color=INK, anchor="start"):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color}" text-anchor="{anchor}">{escape(value)}</text>'
        )

    def box(self, x, y, width, height, title, lines=(), tint="#ffffff", dashed=False):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" '
            f'fill="{tint}" stroke="{AMBER if dashed else LINE}" stroke-width="1.5"'
            + (' stroke-dasharray="7 5"' if dashed else "")
            + "/>"
        )
        self.text(x + 20, y + 34, title, 20, 650)
        for index, line in enumerate(lines):
            self.text(x + 20, y + 62 + index * 23, line, 15, color=MUTED)

    def path(self, value, arrow=True):
        self.parts.append(
            f'<path d="{value}" fill="none" stroke="{MUTED}" stroke-width="2"'
            + (' marker-end="url(#arrow)"' if arrow else "")
            + "/>"
        )

    def label(self, x, y, value, width=150):
        self.parts.append(
            f'<rect x="{x - width / 2}" y="{y - 17}" width="{width}" height="23" '
            f'rx="4" fill="{PAPER}"/>'
        )
        self.text(x, y, value, 15, 600, anchor="middle")

    def save(self, filename):
        (HERE / filename).write_text(
            "\n".join(self.parts + ["</g></svg>"]) + "\n", encoding="utf-8"
        )


def graph_schema():
    """Show the implemented labels, relation endpoints and separated targets."""
    figure = Figure(
        880,
        "ARIADNE biological evidence schema",
        "Compound binds Gene; Disease associates with Gene; Genes interact and "
        "participate in Pathway. Gene A and Gene B are roles of the same label. "
        "All biological nodes share Entity identity. Treatment labels are separate "
        "from the graph used for predictive features.",
    )
    figure.text(36, 45, "THE BIOLOGICAL EVIDENCE GRAPH", 14, 700, MUTED)
    figure.text(36, 82, "Four entity types. Four evidence families.", 28, 650)
    figure.text(
        36, 111, "24,456 biological entities · 255,730 evidence records · Hetionet v1.0", 16
    )
    figure.box(
        60, 150, 310, 112, "Compound : Entity", ["Compound::DrugBank identifier", "1,552 compounds"]
    )
    figure.box(630, 150, 310, 112, "Disease : Entity", ["Disease::DOID identifier", "137 diseases"])
    figure.box(
        60,
        345,
        310,
        112,
        "Gene A : Entity",
        ["Gene::Entrez identifier", "20,945 genes across both roles"],
    )
    figure.box(
        630,
        345,
        310,
        112,
        "Gene B : Entity",
        ["Gene::Entrez identifier", "Same Gene label as role A"],
    )
    figure.box(
        345, 545, 310, 112, "Pathway : Entity", ["Pathway::source identifier", "1,822 pathways"]
    )
    figure.path("M 215 262 L 215 345")
    figure.label(215, 301, "BINDS · 11,571", 164)
    figure.path("M 785 262 L 785 345")
    figure.label(785, 301, "ASSOCIATES · 12,623", 207)
    figure.path("M 370 401 L 630 401", arrow=False)
    figure.label(500, 388, "INTERACTS · 147,164", 206)
    figure.text(500, 429, "symmetric traversal", 14, color=MUTED, anchor="middle")
    figure.path("M 215 457 L 215 515 Q 215 540 240 560 L 345 601")
    figure.path("M 785 457 L 785 515 Q 785 540 760 560 L 655 601")
    figure.label(215, 502, "PARTICIPATES", 152)
    figure.label(785, 502, "PARTICIPATES", 152)
    figure.text(500, 524, "84,372 PARTICIPATES records in total", 15, color=MUTED, anchor="middle")
    figure.box(
        36,
        690,
        564,
        146,
        "Identity and retained provenance",
        [
            "Nodes: id, identifier, name; available url and original data",
            "Relations: id, type, direction, sources, license, data",
            "Namespace-qualified IDs; original metadata is preserved.",
        ],
    )
    figure.box(
        624,
        690,
        340,
        146,
        "755 treatment label pairs",
        [
            "TREATS / PALLIATES held separately",
            "Train / validation / test and lookup",
            "Excluded from predictive graph paths",
        ],
        tint="#fff8e9",
        dashed=True,
    )
    figure.text(
        36,
        862,
        "Gene A/B are path roles. INTERACTS records retain original direction; traversal is symmetric.",
        14,
        color=MUTED,
    )
    figure.save("graph-schema.svg")


def architecture():
    """Show current runtime services and the bounded data/model pipeline."""
    figure = Figure(
        1070,
        "ARIADNE service architecture and data flow",
        "The browser uses Nginx on port 8080 and FastAPI on 8000. FastAPI "
        "orchestrates read-only graph tools, fixed-model ranking and three audit "
        "engines. Neo4j with GDS uses Bolt 7687 and Browser 7474. An optional "
        "Ollama service on internal port 11434 or configured provider supplies "
        "validated plans, never scores. Checksummed Hetionet data is prepared "
        "with treatment labels separate, imported idempotently and fitted using "
        "a recorded split. Graph and saved model are fixed during challenges.",
    )
    figure.text(36, 45, "SERVICES + DATA FLOW", 14, 700, MUTED)
    figure.text(36, 82, "A traceable path from question to evidence.", 28, 650)
    figure.box(335, 116, 330, 86, "Research interface", ["Browser · evidence, rankings, audits"])
    figure.box(335, 254, 330, 86, "Nginx · :8080", ["Static frontend + reverse proxy"])
    figure.path("M 500 202 L 500 254")
    figure.label(500, 234, "HTTP", 66)
    figure.box(
        215,
        404,
        570,
        112,
        "FastAPI · :8000",
        [
            "LangGraph · validated plans · typed, read-only tools",
            "Exact graph features · fixed-model ranking · three auditors",
        ],
        tint="#eef5f0",
    )
    figure.path("M 500 340 L 500 404")
    figure.label(500, 378, "/api · /docs · /redoc", 199)
    figure.box(
        36,
        609,
        430,
        112,
        "Neo4j + Graph Data Science",
        [
            "Bolt :7687 · Neo4j Browser :7474",
            "Typed evidence · indexes · graph algorithms",
        ],
    )
    figure.box(
        534,
        609,
        430,
        112,
        "Optional LLM provider",
        [
            "Ollama :11434 (internal) or configured URL",
            "Typed planning only; no ranking or labels",
        ],
    )
    figure.path("M 350 516 L 350 558 Q 350 570 338 570 L 263 570 Q 251 570 251 582 L 251 609")
    figure.path("M 650 516 L 650 558 Q 650 570 662 570 L 737 570 Q 749 570 749 582 L 749 609")
    figure.label(251, 552, "Read-only queries", 177)
    figure.label(749, 552, "Plan request", 152)
    figure.box(
        36,
        817,
        260,
        112,
        "Pinned Hetionet JSON",
        [
            "Source archive SHA-256",
            "Downloaded bytes verified",
        ],
    )
    figure.box(
        366,
        817,
        268,
        112,
        "Prepare + evaluate",
        [
            "Graph and separate label table",
            "Recorded split → fit / evaluate",
        ],
    )
    figure.box(
        704,
        817,
        260,
        112,
        "Graph + saved model",
        [
            "Source / model identities",
            "Fixed during challenges",
        ],
    )
    figure.path("M 296 872 L 366 872")
    figure.path("M 634 872 L 704 872")
    figure.path("M 416 817 L 416 721")
    figure.label(416, 794, "Idempotent graph import", 243)
    figure.path("M 964 872 L 981 872 L 981 460 L 785 460")
    figure.label(880, 438, "Load fixed artifacts", 194)
    figure.text(
        36,
        973,
        "Labels supervise fitting and evaluation; TREATS / PALLIATES never enter predictive evidence paths.",
        15,
        color=MUTED,
    )
    figure.text(
        36,
        1003,
        "Binding, provenance and joint auditors return replayable certificates bound to the graph and model.",
        15,
        color=MUTED,
    )
    figure.text(
        36,
        1033,
        "Published ports bind to 127.0.0.1. Core-only startup uses deterministic planning by default.",
        15,
        color=MUTED,
    )
    figure.save("architecture.svg")


if __name__ == "__main__":
    graph_schema()
    architecture()
