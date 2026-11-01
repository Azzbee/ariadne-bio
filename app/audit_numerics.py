"""A specified finite arithmetic kernel for reproducible audit certificates.

Transcendentals use a fixed Decimal context, followed by integer nearest-even
rounding to binary64. Basic feature arithmetic uses separate IEEE-754 binary64
ufunc operations. There is no platform libm, BLAS reduction, or fused operation
in this kernel. The historical scorer remains in binding_audit for old seals.
"""

from __future__ import annotations

from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN
from functools import lru_cache
import struct

import numpy as np

SCORER = "decimal80-binary64-v1"
LEGACY_SCORER = "float64-fixed-order-v1"
SUPPORTED_SCORERS = (SCORER, LEGACY_SCORER)
DECIMAL_PRECISION = 80
TRANSFORM_CACHE_SIZE = 131072
_CONTEXT = Context(
    prec=DECIMAL_PRECISION,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[DivisionByZero, InvalidOperation, Overflow],
)
_ONE = Decimal(1)


def _round_quotient(numerator, denominator):
    quotient, remainder = divmod(numerator, denominator)
    doubled = 2 * remainder
    return quotient + (doubled > denominator or (doubled == denominator and quotient % 2 == 1))


def decimal_to_binary64(value):
    """Round a finite Decimal to IEEE binary64 by exact integer arithmetic.

    This explicitly specifies ties, subnormals and overflow instead of relying
    on the host's Decimal-to-float or C-library string conversion implementation.
    Signed zeros are preserved here; certificate transport normalizes zeros.
    """
    if not value.is_finite():
        raise ValueError("Audit Decimal conversion requires a finite value")
    sign = int(value.is_signed()) << 63
    magnitude = value.copy_abs()
    if not magnitude or magnitude.adjusted() < -325:
        bits = sign
    elif magnitude.adjusted() > 309:
        bits = sign | (2047 << 52)
    else:
        numerator, denominator = magnitude.as_integer_ratio()
        exponent = numerator.bit_length() - denominator.bit_length()
        if (exponent >= 0 and numerator < denominator << exponent) or (
            exponent < 0 and numerator << -exponent < denominator
        ):
            exponent -= 1
        if exponent < -1022:
            # Subnormals and a possible carry into the smallest normal value.
            bits = sign | _round_quotient(numerator << 1074, denominator)
        else:
            shift = 52 - exponent
            significand = _round_quotient(numerator << max(shift, 0), denominator << max(-shift, 0))
            if significand == 1 << 53:
                significand >>= 1
                exponent += 1
            bits = sign | (
                (2047 << 52)
                if exponent > 1023
                else ((exponent + 1023) << 52) | (significand - (1 << 52))
            )
    return struct.unpack(">d", bits.to_bytes(8, byteorder="big"))[0]


@lru_cache(maxsize=TRANSFORM_CACHE_SIZE)
def _log1p(value):
    context = _CONTEXT.copy()
    argument = context.add(_ONE, Decimal.from_float(float(value)))
    return decimal_to_binary64(context.ln(argument))


@lru_cache(maxsize=16384)
def _sqrt(value):
    context = _CONTEXT.copy()
    return decimal_to_binary64(context.sqrt(Decimal.from_float(float(value))))


@lru_cache(maxsize=TRANSFORM_CACHE_SIZE)
def _sigmoid(value):
    # Beyond these exact branch points the correctly rounded binary64 logistic
    # value is respectively 1 or 0. The bounds also avoid Decimal exponent limits.
    if value >= 800:
        return 1.0
    if value <= -800:
        return 0.0
    context = _CONTEXT.copy()
    term = context.exp(Decimal.from_float(-abs(float(value))))
    denominator = context.add(_ONE, term)
    return decimal_to_binary64(context.divide(_ONE if value >= 0 else term, denominator))


def _mapped(values, transform):
    """Evaluate only distinct arguments; bounded caches contain scalar results."""
    values = np.asarray(values, dtype=np.float64)
    distinct, inverse = np.unique(values, return_inverse=True)
    transformed = np.asarray([transform(float(value)) for value in distinct], dtype=np.float64)
    return transformed[inverse].reshape(values.shape)


def _check_binary64():
    """Reject unsupported formats, non-nearest rounding and flushed subnormals."""
    if np.finfo(np.float64).nmant != 52 or np.finfo(np.float64).nexp != 11:
        raise RuntimeError("Audit scoring requires IEEE-754 binary64")
    halfway = np.float64(float.fromhex("0x1p-53"))
    even = np.float64(1.0)
    odd = np.float64(float.fromhex("0x1.0000000000001p+0"))
    normal = np.float64(float.fromhex("0x1p-1022"))
    tiny = np.float64(float.fromhex("0x1p-1074"))
    observed = (
        np.add(even, halfway),
        np.add(odd, halfway),
        np.add(-even, -halfway),
        np.multiply(normal, np.float64(0.5)),
        np.add(tiny, np.float64(0.0)),
    )
    expected_bits = (
        0x3FF0000000000000,
        0x3FF0000000000002,
        0xBFF0000000000000,
        0x0008000000000000,
        0x0000000000000001,
    )
    # A DAZ runtime can also compare an expected subnormal as zero. Inspect
    # integer representations so the guard cannot inherit that false equality.
    if tuple(int(np.asarray(value, dtype=np.float64).view(np.uint64)) for value in observed) != (
        expected_bits
    ):
        raise RuntimeError("Audit scoring requires nearest-even arithmetic and gradual underflow")


def canonical_scores(counts, compound_degree, disease_degree, model):
    """Score rows by the fully specified decimal80-binary64-v1 operation order.

    Decimal inputs are exact conversions of binary64 arguments. Decimal context
    operations round at 80 significant digits, then each transform rounds once
    to binary64. This defines a finite scorer, not an assertion that the entire
    mathematical real-number expression is correctly rounded in one step.
    """
    _check_binary64()
    values = np.asarray(counts, dtype=np.float64)
    compound_degree, disease_degree = np.broadcast_arrays(
        np.asarray(compound_degree, dtype=np.float64),
        np.asarray(disease_degree, dtype=np.float64),
    )
    if values.shape[-1:] != (3,) or any(
        not np.isfinite(array).all() or np.any(array < 0)
        for array in (values, compound_degree, disease_degree)
    ):
        raise ValueError("Audit counts and degrees must be finite and nonnegative")
    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        try:
            product = np.multiply(compound_degree, disease_degree)
            divisor = _mapped(np.maximum(product, np.float64(1)), _sqrt)
            terms = [_mapped(values[..., index], _log1p) for index in range(3)]
            terms.extend(
                _mapped(np.divide(values[..., index], divisor), _log1p) for index in range(3)
            )
            terms.extend((_mapped(compound_degree, _log1p), _mapped(disease_degree, _log1p)))
            logits = np.full(values.shape[:-1], model["intercept"], dtype=np.float64)
            for index, term in enumerate(terms):
                centered = np.subtract(term, model["mean"][index])
                standardized = np.divide(centered, model["scale"][index])
                contribution = np.multiply(model["coefficients"][index], standardized)
                logits = np.add(logits, contribution)
        except FloatingPointError as error:
            raise ValueError("Nonfinite intermediate in audit scorer") from error
    if not np.isfinite(logits).all():
        raise ValueError("Nonfinite logit in audit scorer")
    return _mapped(logits, _sigmoid), logits
