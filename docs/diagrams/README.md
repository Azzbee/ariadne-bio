# Portable architecture figures

The README and architecture reference embed ordinary, self-contained SVGs.
They work without a Mermaid renderer, JavaScript, remote images or web fonts.
The shared labels, properties and service ports describe the implementation;
the diagrams do not add treatment edges to the predictive evidence graph.

The editable source is [render.py](render.py), a Python standard-library
generator with explicit labels and layout. From the repository root:

```bash
python docs/diagrams/render.py
```

The outputs are [graph-schema.svg](graph-schema.svg) and
[architecture.svg](architecture.svg). Both carry descriptive SVG titles and
alternative descriptions. Their full property definitions, counts and runtime
contracts are in the [architecture reference](../architecture.md).

For a local PNG preview, if Inkscape is installed:

```bash
inkscape docs/diagrams/graph-schema.svg --export-type=png --export-filename=/tmp/ariadne-schema.png
inkscape docs/diagrams/architecture.svg --export-type=png --export-filename=/tmp/ariadne-architecture.png
```
