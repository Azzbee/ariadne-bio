# Reproducible finite arithmetic for audit certificates

The default scorer is **`decimal80-binary64-v1`**. Both the individual binding
audit and the correlated provenance audit use it. Its guarantees concern the
finite function below, with the exact frozen graph and model. They do not claim
that an entire real-number expression is rounded correctly in one final step.
The explorer's original `GraphEngine` feature transforms, fitted model and
ranking implementation remain unchanged.

## Why a new identity was necessary

An actual GitHub Actions certificate from run `41301561071` failed strict replay
on the development machine despite matching graph, model and scorer identities.
For rheumatoid arthritis / Ketoprofen, the historical scorer returned
`0.8227232069370202` in CI and `0.8227232069370205` locally. Its inputs were counts
`[3, 14, 1260]`, compound degree 13, disease degree 267, and model self-hash
`9e07aa28d768d4fedc6080566b44b605cc2488e374afe184d22ffe91dd634838`.

Diagnostic child processes isolated the discrepancy to NumPy's dispatched
`log1p`: changing AVX-512 dispatch changed the historical output on the same
machine. The scenario-table digest consequently differed, even though the
observed ranks and protection plans did not. NumPy documents both
[runtime CPU dispatch](https://numpy.org/doc/2.3/reference/simd/build-options.html#runtime-dispatch)
and the APIs for inspecting selected kernels. Replacing vector operations with
the platform's scalar `math` functions would not by itself establish a portable
contract: Python describes those functions as mostly wrappers around the
[platform C math library](https://docs.python.org/3/library/math.html).

The repair changes the named scoring function, preserves strict verification,
and freezes independent regression expectations. It does not set a deployment
environment variable to hide the difference, round certificate outputs for
comparison, or accept a numerical tolerance.

## Representations and rounding

The supported native arithmetic format is IEEE-754 binary64, round to nearest,
ties to even, with gradual underflow. The scorer checks the format, representative
even and odd halfway additions, negative rounding and subnormal preservation on
every call. Sentinel results are compared through their integer bit patterns,
so a runtime that also treats denormal comparison operands as zero cannot hide
a flushed result. A nonconforming runtime is rejected. These checks are guards against
unsupported environments, not an exhaustive hardware conformance proof.

Every Decimal operation uses an explicitly constructed context:

| Setting | Value |
|---|---|
| Precision | 80 significant decimal digits |
| Rounding | `ROUND_HALF_EVEN` |
| Minimum / maximum exponent | −999999 / 999999 |
| Clamp | 0 |
| Capitals | 1, irrelevant to numerical values |
| Initial flags | Empty |
| Traps | Division by zero, invalid operation, overflow |

Conversion **from** binary64 to Decimal is exact (`Decimal.from_float`). The
context is copied for each uncached scalar transform. Neither the caller's
current Decimal context nor mutable flags from another transform are used.
The Decimal `ln` and `exp` operations have documented correctly rounded
`ROUND_HALF_EVEN` results; `sqrt` is rounded to the context precision. See the
[Python Decimal specification](https://docs.python.org/3/library/decimal.html).

Conversion **to** binary64 is specified by integer arithmetic, rather than by
the host C library or Decimal-to-float conversion. For the nonnegative exact
rational `n/d` represented by a finite Decimal:

1. Determine its binary exponent using integer bit lengths and exact comparison.
2. For a normal value, round the scaled significand to 53 bits. For a subnormal
   value, round `n × 2^1074 / d` to an integer.
3. Round an integer quotient up when twice its remainder exceeds the denominator;
   on equality, round up only when the quotient is odd.
4. Handle a carry into the next exponent or from subnormal to normal, and normal
   overflow into infinity. Pack the resulting sign, exponent and significand
   bits as binary64. The scorer itself rejects nonfinite intermediates.

The converter preserves signed zero. Scoring treats zero counts identically,
and the certificate's existing JSON-number transport convention normalizes
negative zero and integral floats. It never rounds a nonintegral finite value.

## Exact operation order

Let `RN64` be the specified binary64 rounding and `D80` the Decimal context above.
All counts, degrees and saved model parameters enter the scorer as binary64.
The graph's supported inputs are exact nonnegative integer counts and degrees.
The implementation rejects nonfinite or negative inputs and nonfinite logits.

For each compound–disease row:

1. Multiply compound degree `d` and disease degree `a` in binary64; take the
   maximum of that result and binary64 one.
2. Convert this result exactly to Decimal, compute `D80.sqrt`, then apply `RN64`.
   This is the normalization divisor `v`.
3. Define `L(x) = RN64(D80.ln(D80.add(1, Decimal.from_float(x))))`.
4. Form features in the saved order:
   `L(p0), L(p1), L(p2), L(RN64(p0/v)), L(RN64(p1/v)), L(RN64(p2/v)), L(d), L(a)`.
5. Start the logit with the saved binary64 intercept. For each feature in order,
   perform four separate operations: subtract its saved mean, divide by its
   saved scale, multiply by its coefficient, and add the contribution to the
   current logit. Each operation rounds to binary64. No BLAS dot product, fused
   multiply-add or reduction over features is used.
6. Convert the resulting finite logit `z` to a score using the following defined
   Decimal sigmoid, and round its final result with `RN64`:
   - If `z ≥ 800`, the score is exactly binary64 one.
   - If `z ≤ −800`, the score is exactly binary64 zero.
   - Otherwise compute `t = D80.exp(Decimal.from_float(−abs(z)))`, then
     `u = D80.add(1, t)`. For nonnegative `z`, use `D80.divide(1, u)`; for negative
     `z`, use `D80.divide(t, u)`.

The ±800 branches are part of the finite contract. At these magnitudes the
mathematical sigmoid already rounds to the stated binary64 endpoint; the
branches also avoid unnecessary Decimal exponent-range failures for huge finite
logits. Decimal rounding occurs at each explicitly listed Decimal operation.
This precision is not an assertion of correctly rounded binary64 `log1p` or
sigmoid for every possible real argument.

Scores descend, with namespace-qualified compound ID ascending for exact score
ties. Sigmoid saturation ties are therefore resolved by ID, even when the logits
differ. A row whose three path counts sum to zero is unsupported and has no rank,
regardless of its finite diagnostic score.

## Caches, shapes and concurrency

Distinct binary64 transform arguments are evaluated once per cache entry.
The `log1p` and sigmoid caches each retain at most 131,072 scalar results; the
square-root cache retains at most 16,384. They contain no model parameters,
graph data, or stochastic state. Their values are pure functions of the named
contract and argument; eviction, concurrency, array shape and cache warmth cannot
change a result. The standard-library LRU cache is thread-safe; simultaneous
misses may duplicate work but cannot alter a value.

Basic NumPy multiply/divide/add/subtract operations remain vectorized. The
supported rounding format, explicit intermediate arrays and separate calls
prevent an implementation from silently choosing a fused arithmetic expression.
The Decimal transcendental results do not depend on NumPy SIMD dispatch.

## Certificate compatibility

Methods remain `binding-envelope-v1` and `provenance-group-exhaustive-v1`, with
schema version `1.0`. **`identity.scorer` distinguishes the numerical function.**
Changing that string and recomputing a content hash cannot make a certificate
valid: verification reconstructs every field using the declared scorer.

New certificates omit `legacy_score`, `legacy_rank`, `score_difference` and
`rank_agrees_with_legacy`. Those explorer diagnostics were computed through the
unchanged platform-dependent legacy engine and cannot be sealed into a portable
certificate. The original explorer remains available separately. The new scorer
does not edit or refit its model.

The historical `float64-fixed-order-v1` implementation is preserved verbatim,
including its interpretation and legacy comparison fields. A verifier accepts a
historical certificate only if its original strict calculations reproduce on the
current runtime. It never relabels it or silently upgrades its numerical values.
Historical certificates are not retroactively portable. All non-scorer input
identities must match the owning immutable auditor before compatibility dispatch;
a later mutation of the engine cannot switch to another graph or model. Saved
model self-hashes are rechecked before constructing either auditor.

Entity identity/name/type metadata, disease positions, baseline path counts and
all scientific matrices are copied at construction. Historical scorer instances
also copy the legacy score matrix once; new scorer instances never evaluate it.
Changing an engine cache or display name afterward cannot change sealed names,
lookup rows, diagnostics, bounds or replay. Constructors check loaded entity and
edge identities against the same raw graph bytes whose digest is bound.

Unknown scorer identities fail closed. Bounds are recomputed in a separate
cache, and attaining witnesses are independently replayed through edited sparse
matrices. Hash equality is an integrity check, not a replacement for those
computations.

## Regression evidence and its limits

`tests/fixtures/audit-numerics-v1.json` contains twenty actual CI input rows,
their exact model, and static expected feature, logit and score hexadecimal
values. The expected values were generated with Python's independent `_pydecimal`
reference implementation and scalar binary64 operations, importing no ARIADNE
production code. Tests compare the production C Decimal/vector kernel against
those frozen values. The original troublesome Ketoprofen row is included.

Other tests cover exact midpoint conversion, subnormal and overflow boundaries,
signed zero, saturation, altered ambient and default Decimal contexts, concurrent
cache access, complete certificate equality between native and disabled-AVX-512
child processes, old certificate dispatch, and rejection of relabeled, unknown or
mutated-identity certificates. Literal-path enumeration independently checks
complete tiny-graph rank bounds, support loss, witnesses and protection optima.

These tests establish the stated implementation checks on the exercised
runtimes. A complete CI-artifact replay uses the **same retained model and graph**
in another runtime; a fresh fit is a different model and is not a portability
test. Successful same-runtime replay, a theorem, or matching a few scores alone
does not establish that independent artifact result.
