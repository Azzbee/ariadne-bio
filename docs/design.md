# Interface and brand design

## The visitor's first question

ARIADNE's opening screen introduces the purpose of the instrument: follow a
biomedical hypothesis back to its evidence, then ask how much that hypothesis
depends on records that could change. It gives a new visitor a concrete example
before presenting the full research controls.

The visual progression is deliberate: a large editorial introduction, a
conceptual evidence map, three steps through an investigation, a recorded
source-withdrawal example, and an explanation of replayable proof. Each section
offers a working route into the workbench, methods or source repository.
There are no invented customer logos, testimonials or clinical success claims.
The [desktop capture](screenshots/landing-v1.4.jpg) records the actual rendered
Overview, including the mark, typography and labeled conceptual illustration.

## The mark and visual language

The open **threaded A** replaces the previous boxed monogram. Its continuous
line and terminal node connect the product name to the act of following a path
through evidence. The same thread appears in the hero illustration. The mark
is a small repository-native SVG used in the header and favicon; it needs no
raster image service or rendering dependency.

Warm ivory provides the reading surface, deep forest gives the scientific
instrument its structure, and pale lime highlights the thread and active
connections. A warm peach tone distinguishes a failed ranking scenario. Labels,
rank values and explicit verdict text carry the meaning as well as color.

| Element | Implementation |
| --- | --- |
| Reading surface | Ivory `#f5f4ec` |
| Main ink and dark panels | Forest tones, including `#193a30` and `#16372c` |
| Thread and active accents | Pale lime `#d9e99a` |
| Interface typography | Manrope with system sans-serif fallbacks |
| Editorial display typography | Instrument Serif, regular and italic, with serif fallbacks |
| Hero artwork | Inline SVG; a conceptual map, not a representation of the measured Hetionet graph |

The graph illustration is visibly identified as conceptual. Its motion does not
pretend to display a live model calculation, and the landing page does not
describe the recorded example as a new experiment.

## Local typefaces and licensing

The three Latin WOFF2 files total **67,692 bytes**. They are served from the
application itself, so rendering the page does not request fonts from a third
party. `font-display: swap` keeps text visible while fonts load; system fallback
fonts cover characters outside the bundled subset.

The original font projects are [Manrope](https://github.com/googlefonts/manrope)
and [Instrument Serif](https://github.com/Instrument/instrument-serif). Both
unmodified SIL Open Font License files, the downloaded font filenames, and their
exact Google Fonts source URLs are retained in the
[font asset directory](https://github.com/Azzbee/ariadne-bio/tree/main/frontend/assets/fonts).
The release packager includes that directory recursively.

## Interaction and accessibility

The Overview is semantic HTML that remains meaningful without JavaScript.
Case exploration, audit computation and the workbench's interactive controls
require JavaScript; the static introduction does not claim otherwise. Internal
links have real destinations, and existing disease, compound and audit links
still open their intended investigation directly.

Navigation uses history state and handles back/forward movement. The workbench
loads its research data only when the visitor enters an investigation, benchmark
or method view; the opening page does not fetch the API or recorded case dataset.
This separation keeps a visual introduction from depending on a multi-megabyte
research payload or a running backend.

The animated map has a visible pause control. The landing animation honors
`prefers-reduced-motion` and pauses when the document is hidden. Native buttons,
links, disclosure elements and accessible labels keep the page usable with a
keyboard. Live scenario text exposes the selected state, and the recorded
example never relies on the motion itself to explain the result.

The example switches between the original evidence, the worst rank under any
two individual binding-record withdrawals, and one named source-group
withdrawal. It identifies its frozen v1.3 certificate and post-benchmark
selection. The differing perturbation units and clinical limits remain visible.
Changing a display step retrieves a recorded value; it does not run the solver
in the browser.

## Workbench continuity

The existing candidate list, evidence graph, source trail, family controls,
agent, binding audit and provenance audit remain available. The joint-audit
panel adds a four-cell frontier for one group and one surviving record, with
selectable attaining witnesses and the exact certificate export.

Live mode calls the API and its verifier. Recorded mode retrieves certificates
that were verified during snapshot export and labels that execution boundary.
An unavailable scope is shown as unavailable; the client does not fabricate a
result or silently widen its guarantee. Snapshot identity checks bind cases
and certificates to the manifest and fitted model.

## Implementation and verification

The frontend remains ordinary HTML, CSS and browser ES modules. It has no npm
runtime dependencies, framework build step, analytics service or external font
dependency. The landing and joint-audit code are separate modules with pure
model helpers for state and certificate checks.

`node --test frontend/tests/*.test.js` exercises routing, recorded-example
identity, unsupported and malformed audit states, payload integrity, stale
asynchronous responses and the existing workbench behavior. `npm --prefix frontend run check`
checks the JavaScript modules' syntax. Browser QA is a separate release activity:
inspect the actual composition, keyboard flow, example transitions, workbench
entry, narrow layouts and certificate exports. A configured test or CSS rule
alone is not evidence that a browser check passed; retain actual release
screenshots and verification records with the tested source revision.
