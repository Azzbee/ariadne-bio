# Observed source licenses and commercial-use review

## Reproduce the inventory

```bash
make data
make audit-licenses
```

The command writes [license-inventory.json](../reports/v1.2.0/license-inventory.json)
from the exact prepared graph bytes. It includes node, evidence-edge and separate
treatment-label counts, original license text, missing metadata, source/record
co-occurrences, limited record examples and the graph/archive SHA-256 identities.
It does not change data, query a service or assign a new license.

The report's `legal_clearance.status` is always `not_assessed` and
`commercial_permission` is null. A successful command means that metadata was
counted, not that any use was authorized. Unknown text stays unknown, conflicting
declarations remain visible, and an absent license is never interpreted as an
open license.

## Inventory of the pinned prepared graph

These are observed declaration counts, not findings about legal applicability:

| Preserved license text | Nodes | Evidence edges | Separate treatment labels |
| --- | ---: | ---: | ---: |
| CC0 1.0 | 21,165 | 8,154 | 755 |
| CC BY 3.0 | 431 | 12,652 | 0 |
| CC BY 4.0 | 1,308 | 68,899 | 0 |
| CC BY-NC 4.0 | 1,552 | 8,780 | 0 |
| CC BY-SA 3.0 | 0 | 1,711 | 0 |
| ODbL 1.0 | 0 | 5,940 | 0 |
| Missing license metadata | 0 | 149,594 | 0 |
| **Records** | **24,456** | **255,730** | **755** |

Every compound node carries DrugBank source metadata and `CC BY-NC 4.0` in this
input. The machine-readable report enumerates all other observed source names.
Some consolidated edges mention several sources. Such an edge is counted once
in the graph totals and once per source in the co-occurrence inventory; these
source counts must not be added to estimate unique edges. An edge's consolidated
license text is not assigned as the license of every named publisher.

## What the text markers mean

The report recognizes only a small explicit mapping of the exact observed
license labels. `noncommercial_text`, `share_alike_text`, `attribution_text` and
`database_license_text` are review markers. They are not an automated decision
about which database rights, exceptions, contractual permissions or derivative
work obligations apply to a specific deployment.

Primary references for a human review include:

- [Hetionet's license statement](https://github.com/hetio/hetionet#license), which
  distinguishes its original CC0 content from constituent source terms, and its
  [source license table](https://github.com/dhimmel/integrate/blob/master/licenses/README.md).
- [CC BY-NC 4.0 legal code](https://creativecommons.org/licenses/by-nc/4.0/legalcode),
  for records carrying the noncommercial label.
- [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) and
  [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), for the corresponding
  share-alike/database declarations.
- The original record and the source owner's current contract or permission,
  where supplied metadata is missing, inconsistent or insufficient for the use.

ARIADNE's [MIT license](../LICENSE) covers its original code and documentation.
It does not relicense constituent biomedical data, private customer records,
third-party content or published paper text. Training a model or exporting a
snapshot does not cause this inventory to declare the derived artifact cleared.

## Consequence for a commercial pilot

This research dataset is **not presented as commercially cleared**. Before a
commercial pilot, inventory the actual inputs, obtain a use-specific review by
the relevant rights holders or authorized reviewer, and secure permission or use
an appropriately licensed replacement. A private customer deployment still
requires rights to process its inputs. Preserve attribution and provenance as
required by the actual terms.

The [pilot protocol](commercial_pilot.md) separates permission, scientific utility
and willingness to pay. None of those can be inferred from a green software test
or from the presence of a familiar license name.
