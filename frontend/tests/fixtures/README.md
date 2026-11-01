# Joint audit presentation fixture

`mixed-marimastat.json` is an actual certificate from `MixedAuditor`, generated
from the prepared reference graph and fitted model for Marimastat / rheumatoid
arthritis, with top-k 10 and group/record budgets 1+1. The engine's independent
edited-matrix verification returned `valid: true` during fixture generation.
Its embedded identities bind the complete graph/model/scorer and source-group map.

The certificate SHA-256 is
`dd704f9f3ab9a17766e66fb2ed05dcd3897c52e63bf05bb0a60e37f78348a9c8`.
Worst supported ranks across (0,0), (0,1), (1,0), (1,1) are 1, 1, 1,096, 1,096;
the joint cell also has a separate support-loss witness. The presentation tests
keep that distinction intact and intentionally alter copies to test rejection.

Mock verification responses inside unit tests test transport and asynchronous
state handling. They are explicitly unit fixtures and are not publication
evidence. Actual exported snapshots and release verification carry independently
executed records.
