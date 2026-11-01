# Audit arithmetic regression fixtures

`audit-numerics-v1.json` preserves twenty actual shortlist input vectors and the
exact fitted model from GitHub Actions run `41301561071`, artifact `13082241344`.
The model self-hash is `9e07aa28d768d4fedc6080566b44b605cc2488e374afe184d22ffe91dd634838`.
Its historical `expected_ci_score` fields record the old scorer's output; they
are not expectations for the new scorer.

The new `expected` hexadecimal feature, logit and score values were frozen using
Python's independent `_pydecimal` reference implementation, a fully explicit
80-digit context, scalar binary64 arithmetic, and standard Decimal-to-float
conversion. The one-time reference imported no ARIADNE production code. Tests
compare these static expectations to the C Decimal/vectorized production kernel
and its separate integer binary64 converter. Expected values are never generated
from the implementation under test. The fixture records the original input and
reference-script digests. The numerical contract specifies every operation needed
to reproduce the expectations independently.

The two `legacy-*-certificate.json` files were produced by unmodified public
commit `ccf37ca95623ace90aea722912baa4c587aa7fee` in a detached worktree. They use
`create_fixture_engine`'s hand-counted graph/model with its eight coefficients
replaced by integer zeros. This gives exactly 0.5 scores and zero logits even on
different historical libm implementations, allowing the compatibility test to
exercise old identities, interpretation, diagnostic fields, bounds, witnesses and
seals without pretending that arbitrary old certificates were portable.

These are synthetic compatibility examples, not biomedical benchmark results.
