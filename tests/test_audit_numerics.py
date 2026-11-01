"""Frozen, independent and cross-dispatch regression tests for audit numerics."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Context, Decimal, ROUND_DOWN, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from app import audit_numerics
from app.audit_numerics import SCORER, LEGACY_SCORER, canonical_scores, decimal_to_binary64
from app.binding_audit import BindingAuditor, certificate_digest
from app.provenance_audit import ProvenanceAuditor
from tests.test_graph_engine import create_fixture_engine

FIXTURES = Path(__file__).with_name("fixtures")


def _golden():
    return json.loads((FIXTURES / "audit-numerics-v1.json").read_text())


def _score_rows(fixture):
    rows = fixture["rows"]
    return canonical_scores(
        [row["counts"] for row in rows],
        [row["compound_degree"] for row in rows],
        [row["disease_degree"] for row in rows],
        fixture["model"],
    )


def _assert_golden(fixture):
    scores, logits = _score_rows(fixture)
    assert [float(value).hex() for value in scores] == [
        row["expected"]["score_hex"] for row in fixture["rows"]
    ]
    assert [float(value).hex() for value in logits] == [
        row["expected"]["logit_hex"] for row in fixture["rows"]
    ]


def test_actual_ci_inputs_match_frozen_independent_feature_logit_and_score_bits():
    fixture = _golden()
    unsigned = {key: value for key, value in fixture["model"].items() if key != "model_sha256"}
    assert hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest() == (
        "9e07aa28d768d4fedc6080566b44b605cc2488e374afe184d22ffe91dd634838"
    )
    assert fixture["scorer"] == SCORER
    _assert_golden(fixture)
    for row in fixture["rows"]:
        divisor = audit_numerics._sqrt(
            float(max(row["compound_degree"] * row["disease_degree"], 1))
        )
        assert divisor.hex() == row["expected"]["divisor_hex"]
        arguments = [*row["counts"], *(count / divisor for count in row["counts"])]
        arguments.extend((row["compound_degree"], row["disease_degree"]))
        assert [audit_numerics._log1p(value).hex() for value in arguments] == (
            row["expected"]["features_hex"]
        )


def test_ambient_decimal_context_cannot_change_the_certificate_scorer():
    fixture = _golden()
    with localcontext(Context(prec=3, rounding=ROUND_DOWN, Emin=-3, Emax=3)):
        for transform in (audit_numerics._log1p, audit_numerics._sqrt, audit_numerics._sigmoid):
            transform.cache_clear()
        _assert_golden(fixture)
    _assert_golden(fixture)


def test_concurrent_transform_cache_hits_and_misses_preserve_every_bit():
    fixture = _golden()
    for transform in (audit_numerics._log1p, audit_numerics._sqrt, audit_numerics._sigmoid):
        transform.cache_clear()
        assert transform.cache_parameters()["maxsize"] > 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_assert_golden, [fixture] * 12))


def test_binary64_converter_rounds_exact_halfway_normal_subnormal_and_overflow_cases():
    with localcontext(Context(prec=1200)):
        half_ulp = Decimal(2) ** -53
        assert decimal_to_binary64(Decimal(1) + half_ulp).hex() == "0x1.0000000000000p+0"
        assert decimal_to_binary64(Decimal(1) + 3 * half_ulp).hex() == "0x1.0000000000002p+0"
        assert decimal_to_binary64(-Decimal(1) - half_ulp).hex() == "-0x1.0000000000000p+0"
        assert decimal_to_binary64(-Decimal(1) - 3 * half_ulp).hex() == "-0x1.0000000000002p+0"
        half_subnormal = Decimal(2) ** -1075
        assert decimal_to_binary64(half_subnormal).hex() == "0x0.0p+0"
        assert decimal_to_binary64(3 * half_subnormal).hex() == "0x0.0000000000002p-1022"
        assert decimal_to_binary64(-half_subnormal).hex() == "-0x0.0p+0"
        boundary = Decimal.from_float(sys.float_info.max) + Decimal(2) ** 970
        assert math.isinf(decimal_to_binary64(boundary))
        assert decimal_to_binary64(boundary - 1) == sys.float_info.max
        assert decimal_to_binary64(Decimal(2) ** -1022) == sys.float_info.min
        assert decimal_to_binary64(Decimal(2) ** -1022 - half_subnormal) == sys.float_info.min
    assert decimal_to_binary64(Decimal("1e10000")) == math.inf
    assert decimal_to_binary64(Decimal("1e-10000")) == 0.0
    assert decimal_to_binary64(Decimal("-0")).hex() == "-0x0.0p+0"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_binary64_converter_rejects_nonfinite_values(value):
    with pytest.raises(ValueError, match="finite"):
        decimal_to_binary64(Decimal(value))


@pytest.mark.parametrize(
    "intercept, expected",
    [(1000, 1.0), (-1000, 0.0), (-0.0, 0.5), (-745, float.fromhex("0x1p-1074")), (-746, 0.0)],
)
def test_sigmoid_saturation_and_signed_zero_have_explicit_semantics(intercept, expected):
    model = {"mean": [0] * 8, "scale": [1] * 8, "coefficients": [0] * 8, "intercept": intercept}
    scores, _ = canonical_scores([[0, 0, 0], [1, 2, 3]], [0, 2], 1, model)
    np.testing.assert_array_equal(scores, [expected, expected])


@pytest.mark.parametrize("counts", [[1, -1, 0], [0, math.nan, 0], [0, math.inf, 0], [1, 2]])
def test_nonfinite_negative_or_wrong_shaped_counts_fail_closed(counts):
    with pytest.raises(ValueError, match="counts"):
        canonical_scores(counts, 1, 1, _golden()["model"])


def test_nonfinite_arithmetic_is_rejected_instead_of_sealed():
    model = deepcopy(_golden()["model"])
    model["scale"][0] = 0.0
    with pytest.raises(ValueError, match="Nonfinite"):
        canonical_scores([1, 0, 0], 1, 1, model)
    model["scale"][0] = 1.0
    model["coefficients"][0] = sys.float_info.max
    with pytest.raises(ValueError, match="Nonfinite"):
        canonical_scores([100000, 0, 0], 1, 1, model)
    with pytest.raises(ValueError, match="Nonfinite"):
        canonical_scores([1, 0, 0], sys.float_info.max, sys.float_info.max, model)


@pytest.mark.parametrize(
    "name, auditor_type", [("binding", BindingAuditor), ("provenance", ProvenanceAuditor)]
)
def test_frozen_historical_certificate_selects_its_original_scorer(tmp_path, name, auditor_type):
    engine = create_fixture_engine(tmp_path)
    engine.model["coefficients"] = [0] * 8
    historical = json.loads((FIXTURES / f"legacy-{name}-certificate.json").read_text())
    current = auditor_type(engine)
    assert historical["identity"]["scorer"] == LEGACY_SCORER
    assert current.verify(historical)["valid"]
    assert (
        auditor_type(engine, scorer=LEGACY_SCORER).audit(
            "Disease::D1", "Compound::C2", top_k=1, budget=2
        )
        == historical
    )
    portable = current.audit("Disease::D1", "Compound::C2", top_k=1, budget=2)
    assert portable["identity"]["scorer"] == SCORER
    assert current.verify(portable)["valid"]
    for key in ("legacy_score", "legacy_rank", "score_difference", "rank_agrees_with_legacy"):
        assert key not in portable["baseline"]
    # A valid checksum never authorizes relabeling a numerical contract.
    historical["identity"]["scorer"] = SCORER
    historical["certificate_sha256"] = certificate_digest(historical)
    assert not current.verify(historical)["valid"]
    portable["identity"]["scorer"] = LEGACY_SCORER
    portable["certificate_sha256"] = certificate_digest(portable)
    assert not current.verify(portable)["valid"]


@pytest.mark.parametrize("auditor_type", [BindingAuditor, ProvenanceAuditor])
def test_unknown_scorer_identity_is_rejected_by_constructor_and_verifier(tmp_path, auditor_type):
    engine = create_fixture_engine(tmp_path)
    with pytest.raises(ValueError, match="scorer"):
        auditor_type(engine, scorer="unknown-v99")
    current = auditor_type(engine)
    certificate = current.audit("Disease::D1", "Compound::C2")
    certificate["identity"]["scorer"] = "unknown-v99"
    certificate["certificate_sha256"] = certificate_digest(certificate)
    result = current.verify(certificate)
    assert not result["valid"]
    assert "Unsupported audit scorer identity" in result["errors"]


@pytest.mark.parametrize("auditor_type", [BindingAuditor, ProvenanceAuditor])
def test_alternate_scorer_cannot_switch_the_owning_auditors_frozen_model(tmp_path, auditor_type):
    engine = create_fixture_engine(tmp_path)
    original = auditor_type(engine)
    engine.model["coefficients"][0] += 1
    different = auditor_type(engine, scorer=LEGACY_SCORER).audit("Disease::D1", "Compound::C2")
    verification = original.verify(different)
    assert not verification["valid"]
    assert "identity does not match" in verification["errors"][0]


@pytest.mark.parametrize("auditor_type", [BindingAuditor, ProvenanceAuditor])
def test_stale_model_self_hash_cannot_enter_an_alternate_verifier(tmp_path, auditor_type):
    engine = create_fixture_engine(tmp_path)
    engine.model["model_sha256"] = hashlib.sha256(
        json.dumps(engine.model, sort_keys=True).encode()
    ).hexdigest()
    original = auditor_type(engine)
    historical = auditor_type(engine, scorer=LEGACY_SCORER).audit("Disease::D1", "Compound::C2")
    engine.model["coefficients"][0] += 1
    with pytest.raises(ValueError, match="Model checksum"):
        auditor_type(engine)
    verification = original.verify(historical)
    assert not verification["valid"]
    assert "Model checksum" in verification["errors"][0]


@pytest.mark.parametrize("auditor_type", [BindingAuditor, ProvenanceAuditor])
@pytest.mark.parametrize("scorer", [SCORER, LEGACY_SCORER])
def test_sealed_metadata_positions_counts_and_old_scores_are_frozen(tmp_path, auditor_type, scorer):
    engine = create_fixture_engine(tmp_path)
    auditor = auditor_type(engine, scorer=scorer)
    original = auditor.audit("Disease::D1", "Compound::C2", top_k=1)
    for node in engine.nodes.values():
        node["name"] = "Changed after audit construction"
        node["label"] = "Changed type"
    engine.positions["Disease"] = {"Disease::D1": 1, "Disease::D2": 0}
    engine.path_counts[:] = 0
    engine.score_matrix()[:] = 0
    engine.matrices["BINDS"].data[:] = 0
    assert auditor.audit("Disease::D1", "Compound::C2", top_k=1) == original
    assert auditor.verify(original)["valid"]


@pytest.mark.parametrize("auditor_type", [BindingAuditor, ProvenanceAuditor])
def test_new_auditor_does_not_evaluate_platform_dependent_legacy_scores(
    tmp_path, monkeypatch, auditor_type
):
    engine = create_fixture_engine(tmp_path)

    def forbidden_legacy_call(*_args, **_kwargs):
        raise AssertionError("New certificates must not evaluate legacy scores")

    monkeypatch.setattr(engine, "score_matrix", forbidden_legacy_call)
    auditor = auditor_type(engine)
    certificate = auditor.audit("Disease::D1", "Compound::C2")
    assert auditor.verify(certificate)["valid"]


@pytest.mark.parametrize("auditor_type", [BindingAuditor, ProvenanceAuditor])
def test_changed_entity_metadata_before_construction_cannot_keep_original_graph_identity(
    tmp_path, auditor_type
):
    engine = create_fixture_engine(tmp_path)
    engine.nodes["Compound::C2"]["name"] = "Different from raw graph"
    with pytest.raises(ValueError, match="node identities"):
        auditor_type(engine)


def test_real_ci_vectors_and_complete_certificates_are_identical_across_cpu_dispatch(tmp_path):
    program = """
import decimal
import json
import os
if os.environ.get('ARIADNE_TEST_ALTER_DECIMAL_DEFAULT'):
    decimal.DefaultContext.prec = 3
    decimal.DefaultContext.rounding = decimal.ROUND_DOWN
    decimal.DefaultContext.traps[decimal.Inexact] = True
    decimal.DefaultContext.Emax = 3
    decimal.DefaultContext.Emin = -3
from pathlib import Path
from tempfile import TemporaryDirectory
from app.audit_numerics import canonical_scores
from app.binding_audit import BindingAuditor
from app.provenance_audit import ProvenanceAuditor
from tests.test_graph_engine import create_fixture_engine
fixture = json.loads(Path('tests/fixtures/audit-numerics-v1.json').read_text())
rows = fixture['rows']
scores, logits = canonical_scores([row['counts'] for row in rows],
    [row['compound_degree'] for row in rows], [row['disease_degree'] for row in rows], fixture['model'])
with TemporaryDirectory() as directory:
    engine = create_fixture_engine(Path(directory))
    result = {'scores_hex': [float(x).hex() for x in scores],
              'logits_hex': [float(x).hex() for x in logits],
              'binding': BindingAuditor(engine).audit('Disease::D1', 'Compound::C2'),
              'provenance': ProvenanceAuditor(engine).audit('Disease::D1', 'Compound::C2')}
print(json.dumps(result, sort_keys=True, separators=(',', ':')))
"""
    outputs = []
    for disabled, alter_decimal_default in (
        (None, False),
        ("AVX512F,AVX512_SKX", False),
        (None, True),
    ):
        environment = dict(os.environ)
        environment.pop("NPY_DISABLE_CPU_FEATURES", None)
        if disabled is not None:
            environment["NPY_DISABLE_CPU_FEATURES"] = disabled
        if alter_decimal_default:
            environment["ARIADNE_TEST_ALTER_DECIMAL_DEFAULT"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        )
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1] == outputs[2]
    observed = json.loads(outputs[0])
    fixture = _golden()
    assert observed["scores_hex"] == [row["expected"]["score_hex"] for row in fixture["rows"]]
    assert observed["logits_hex"] == [row["expected"]["logit_hex"] for row in fixture["rows"]]
    # Preserve this test's staged output in pytest's own temporary directory.
    (tmp_path / "cross-dispatch.json").write_text(outputs[0])
