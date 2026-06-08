"""Comprehensive test suite for signalweave/checks/expressions.py.

Tests cover:
- Arithmetic and precedence
- Comparisons, membership, between
- Boolean and/or/not and missing propagation
- Presence predicates
- Functions: count, length/len, sum, min, max, avg
- Projections (list[].field)
- Quantifiers: all/any/none (including empty list and element-missing semantics)
- Ternary if/then/else (including vacuous pass, missing antecedent)
- Parse errors → ExpressionError
"""

from __future__ import annotations

import pytest

from signalweave.checks.expressions import (
    ExpressionError,
    collect_expression_fields,
    evaluate_expression,
    parse_expression,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _eval(text: str, data: dict) -> "ConditionResult":  # type: ignore[name-defined]
    return evaluate_expression(text, data)


def passed(text: str, data: dict) -> bool:
    r = _eval(text, data)
    return r.passed and not r.missing


def failed(text: str, data: dict) -> bool:
    r = _eval(text, data)
    return not r.passed and not r.missing


def missing(text: str, data: dict) -> bool:
    r = _eval(text, data)
    return bool(r.missing)


# ---------------------------------------------------------------------------
# 1. Arithmetic and precedence
# ---------------------------------------------------------------------------

class TestArithmetic:
    def test_addition(self):
        assert passed("data.a + data.b == 10", {"data": {"a": 3, "b": 7}})

    def test_subtraction(self):
        assert passed("data.a - data.b == 1", {"data": {"a": 4, "b": 3}})

    def test_multiplication(self):
        assert passed("data.a * data.b == 12", {"data": {"a": 3, "b": 4}})

    def test_division(self):
        assert passed("data.a / data.b == 2", {"data": {"a": 10, "b": 5}})

    def test_precedence_mul_before_add(self):
        # 2 + 3 * 4 = 2 + 12 = 14
        assert passed("data.x + data.y * data.z == 14",
                      {"data": {"x": 2, "y": 3, "z": 4}})

    def test_parentheses(self):
        # (2 + 3) * 4 = 20
        assert passed("(data.x + data.y) * data.z == 20",
                      {"data": {"x": 2, "y": 3, "z": 4}})

    def test_unary_minus(self):
        assert passed("-data.x == -5", {"data": {"x": 5}})

    def test_division_by_zero_reports_missing(self):
        assert missing("data.a / data.b == 1", {"data": {"a": 10, "b": 0}})

    def test_three_term_sum(self):
        assert passed("data.a + data.b + data.c == 6",
                      {"data": {"a": 1, "b": 2, "c": 3}})

    def test_arithmetic_fail(self):
        assert failed("data.a + data.b == 99", {"data": {"a": 1, "b": 2}})


# ---------------------------------------------------------------------------
# 2. Comparisons, membership, between
# ---------------------------------------------------------------------------

class TestComparisons:
    def test_eq(self):
        assert passed("data.x == 42", {"data": {"x": 42}})

    def test_ne(self):
        assert passed("data.x != 0", {"data": {"x": 1}})

    def test_gt(self):
        assert passed("data.x > 0", {"data": {"x": 1}})

    def test_gte(self):
        assert passed("data.x >= 5", {"data": {"x": 5}})

    def test_lt(self):
        assert passed("data.x < 10", {"data": {"x": 9}})

    def test_lte(self):
        assert passed("data.x <= 100", {"data": {"x": 100}})

    def test_string_eq(self):
        assert passed("data.status == 'Active'", {"data": {"status": "Active"}})

    def test_string_ne(self):
        assert passed("data.status != 'Inactive'", {"data": {"status": "Active"}})

    def test_in_list_literal(self):
        assert passed("data.cat in [A, B, C]", {"data": {"cat": "B"}})

    def test_not_in_list_literal(self):
        assert passed("data.cat not in [X, Y]", {"data": {"cat": "A"}})

    def test_in_fail(self):
        assert failed("data.cat in [X, Y]", {"data": {"cat": "A"}})

    def test_between_inclusive_low(self):
        assert passed("data.x between 1 and 10", {"data": {"x": 1}})

    def test_between_inclusive_high(self):
        assert passed("data.x between 1 and 10", {"data": {"x": 10}})

    def test_between_middle(self):
        assert passed("data.x between 1 and 10", {"data": {"x": 5}})

    def test_between_out_of_range(self):
        assert failed("data.x between 1 and 10", {"data": {"x": 11}})

    def test_comparison_missing_field(self):
        assert missing("data.x > 0", {"data": {}})

    def test_numeric_float(self):
        assert passed("data.amount == 99.5", {"data": {"amount": 99.5}})


# ---------------------------------------------------------------------------
# 3. Boolean and/or/not + missing propagation
# ---------------------------------------------------------------------------

class TestBoolean:
    def test_and_both_true(self):
        assert passed("data.a == 1 and data.b == 2",
                      {"data": {"a": 1, "b": 2}})

    def test_and_first_false(self):
        assert failed("data.a == 99 and data.b == 2",
                      {"data": {"a": 1, "b": 2}})

    def test_and_second_false(self):
        assert failed("data.a == 1 and data.b == 99",
                      {"data": {"a": 1, "b": 2}})

    def test_or_first_true(self):
        assert passed("data.a == 1 or data.b == 99",
                      {"data": {"a": 1, "b": 2}})

    def test_or_second_true(self):
        assert passed("data.a == 99 or data.b == 2",
                      {"data": {"a": 1, "b": 2}})

    def test_or_both_false(self):
        assert failed("data.a == 0 or data.b == 0",
                      {"data": {"a": 1, "b": 2}})

    def test_not_true(self):
        assert passed("not data.a == 99", {"data": {"a": 1}})

    def test_not_false(self):
        assert failed("not data.a == 1", {"data": {"a": 1}})

    def test_and_missing_propagates(self):
        # data.b is missing; the and should propagate missing
        assert missing("data.a == 1 and data.b == 2",
                       {"data": {"a": 1}})

    def test_or_short_circuit_avoids_missing(self):
        # data.a is True, so 'or' short-circuits before checking data.b
        assert passed("data.a == 1 or data.b == 2",
                      {"data": {"a": 1}})

    def test_and_short_circuit_avoids_missing(self):
        # data.a is False, 'and' short-circuits → clean FALSE, not missing
        assert failed("data.a == 99 and data.b == 2",
                      {"data": {"a": 1}})

    def test_not_missing_propagates(self):
        assert missing("not data.x == 1", {"data": {}})

    def test_boolean_precedence_not_before_and(self):
        # not (data.a==1) and data.b==2
        # not False → True; True and True → True
        assert passed("not data.a == 99 and data.b == 2",
                      {"data": {"a": 1, "b": 2}})


# ---------------------------------------------------------------------------
# 4. Presence predicates
# ---------------------------------------------------------------------------

class TestPresence:
    def test_is_present_true(self):
        assert passed("data.x is present", {"data": {"x": 0}})

    def test_is_present_false(self):
        assert failed("data.x is present", {"data": {}})

    def test_is_not_present_true(self):
        assert passed("data.x is not present", {"data": {}})

    def test_is_not_present_false(self):
        assert failed("data.x is not present", {"data": {"x": 1}})

    def test_is_present_never_missing(self):
        # Presence check should return passed=False (not missing) when absent
        r = _eval("data.x is present", {"data": {}})
        assert not r.passed
        assert not r.missing

    def test_is_empty_null(self):
        assert passed("data.x is empty", {"data": {"x": None}})

    def test_is_empty_empty_string(self):
        assert passed("data.x is empty", {"data": {"x": ""}})

    def test_is_empty_non_empty(self):
        assert failed("data.x is empty", {"data": {"x": "hello"}})

    def test_is_not_empty(self):
        assert passed("data.x is not empty", {"data": {"x": "hello"}})

    def test_is_present_dotted_path(self):
        assert passed("data.nested.field is present",
                      {"data": {"nested": {"field": 42}}})


# ---------------------------------------------------------------------------
# 5. Functions: count / length / len
# ---------------------------------------------------------------------------

class TestCountLength:
    def test_count_list(self):
        assert passed("count(data.items) == 3",
                      {"data": {"items": [1, 2, 3]}})

    def test_count_empty(self):
        assert passed("count(data.items) == 0", {"data": {"items": []}})

    def test_count_missing(self):
        assert missing("count(data.items) == 0", {"data": {}})

    def test_length_string(self):
        assert passed("length(data.s) == 5", {"data": {"s": "hello"}})

    def test_len_alias(self):
        assert passed("len(data.s) == 5", {"data": {"s": "hello"}})

    def test_length_list(self):
        assert passed("length(data.items) == 2",
                      {"data": {"items": ["a", "b"]}})

    def test_length_missing(self):
        assert missing("length(data.s) == 5", {"data": {}})


# ---------------------------------------------------------------------------
# 6. Aggregate functions: sum / min / max / avg  (require projection)
# ---------------------------------------------------------------------------

class TestAggregates:
    _DATA = {"data": {"items": [
        {"v": 10}, {"v": 20}, {"v": 30},
    ]}}

    def test_sum(self):
        assert passed("sum(data.items[].v) == 60", self._DATA)

    def test_sum_zero(self):
        assert passed("sum(data.items[].v) == 0",
                      {"data": {"items": []}})

    def test_min(self):
        assert passed("min(data.items[].v) == 10", self._DATA)

    def test_max(self):
        assert passed("max(data.items[].v) == 30", self._DATA)

    def test_avg(self):
        assert passed("avg(data.items[].v) == 20.0", self._DATA)

    def test_sum_missing_array(self):
        assert missing("sum(data.items[].v) == 0", {"data": {}})

    def test_sum_shares_100(self):
        data = {"data": {"beneficiaries": [
            {"share_percentage": 60},
            {"share_percentage": 40},
        ]}}
        assert passed("sum(data.beneficiaries[].share_percentage) == 100", data)

    def test_sum_shares_not_100(self):
        data = {"data": {"beneficiaries": [
            {"share_percentage": 50},
            {"share_percentage": 30},
        ]}}
        assert failed("sum(data.beneficiaries[].share_percentage) == 100", data)

    def test_min_empty_list_missing(self):
        assert missing("min(data.items[].v) > 0", {"data": {"items": []}})


# ---------------------------------------------------------------------------
# 7. Quantifiers: all / any / none  (+  count with where)
# ---------------------------------------------------------------------------

class TestQuantifiers:
    _DATA_2 = {"data": {"nums": [
        {"v": 5},
        {"v": 10},
        {"v": -1},
    ]}}

    def test_all_true(self):
        data = {"data": {"nums": [{"v": 1}, {"v": 2}]}}
        assert passed("all(data.nums where v > 0)", data)

    def test_all_false(self):
        assert failed("all(data.nums where v > 0)", self._DATA_2)

    def test_all_empty_vacuous(self):
        assert passed("all(data.nums where v > 0)", {"data": {"nums": []}})

    def test_any_true(self):
        assert passed("any(data.nums where v > 0)", self._DATA_2)

    def test_any_false(self):
        data = {"data": {"nums": [{"v": -1}, {"v": -2}]}}
        assert failed("any(data.nums where v > 0)", data)

    def test_any_empty_false(self):
        assert failed("any(data.nums where v > 0)", {"data": {"nums": []}})

    def test_none_true(self):
        data = {"data": {"nums": [{"v": -1}, {"v": -2}]}}
        assert passed("none(data.nums where v > 0)", data)

    def test_none_false(self):
        assert failed("none(data.nums where v > 0)", self._DATA_2)

    def test_none_empty_vacuous(self):
        assert passed("none(data.nums where v > 0)", {"data": {"nums": []}})

    def test_count_with_where(self):
        assert passed("count(data.nums where v > 0) == 2", self._DATA_2)

    def test_quantifier_missing_array(self):
        assert missing("all(data.missing where v > 0)", {"data": {}})

    def test_quantifier_not_a_list(self):
        assert missing("all(data.x where v > 0)", {"data": {"x": "not a list"}})

    def test_element_missing_field_propagates_for_all(self):
        # Some elements are missing 'v'; all() should mark missing
        data = {"data": {"nums": [{"v": 1}, {"other": 2}]}}
        assert missing("all(data.nums where v > 0)", data)

    def test_any_with_missing_elements_no_match(self):
        # No element matches (due to missing field) and some have missing data
        data = {"data": {"nums": [{"other": 1}]}}
        assert missing("any(data.nums where v > 0)", data)

    def test_quantifier_string_eq_predicate(self):
        data = {"data": {"items": [
            {"status": "ok"}, {"status": "fail"}
        ]}}
        assert passed("any(data.items where status == 'fail')", data)

    def test_none_with_is_minor(self):
        data = {"data": {"beneficiaries": [
            {"is_minor": False},
            {"is_minor": False},
        ]}}
        assert passed("none(data.beneficiaries where is_minor == true)", data)

    def test_any_with_is_minor(self):
        data = {"data": {"beneficiaries": [
            {"is_minor": False},
            {"is_minor": True},
        ]}}
        assert passed("any(data.beneficiaries where is_minor == true)", data)


# ---------------------------------------------------------------------------
# 8. Ternary: if / then / else
# ---------------------------------------------------------------------------

class TestTernary:
    def test_condition_true_then_true(self):
        assert passed(
            "if data.type == 'X' then data.x_code is present",
            {"data": {"type": "X", "x_code": "123"}}
        )

    def test_condition_true_then_false(self):
        assert failed(
            "if data.type == 'X' then data.x_code is present",
            {"data": {"type": "X"}}
        )

    def test_condition_false_no_else_vacuous_pass(self):
        r = _eval(
            "if data.type == 'X' then data.x_code is present",
            {"data": {"type": "Y"}}
        )
        assert r.passed
        assert not r.missing
        assert "precondition not met" in r.reason

    def test_condition_false_with_else(self):
        assert passed(
            "if data.type == 'X' then data.x_code is present "
            "else data.y_code is present",
            {"data": {"type": "Y", "y_code": "456"}}
        )

    def test_condition_false_else_fails(self):
        assert failed(
            "if data.type == 'X' then data.x_code is present "
            "else data.y_code is present",
            {"data": {"type": "Y"}}
        )

    def test_missing_antecedent_propagates(self):
        assert missing(
            "if data.missing_field == 1 then data.x is present",
            {"data": {}}
        )

    def test_ternary_with_quantifier_antecedent(self):
        # If any beneficiary is a minor → guardian_id must be present
        data_esc = {"data": {
            "beneficiaries": [{"is_minor": True}],
        }}
        assert missing(  # guardian_id absent → missing triggers on_missing policy
            "if any(data.beneficiaries where is_minor == true) "
            "then data.guardian_id is present",
            data_esc
        ) or failed(
            "if any(data.beneficiaries where is_minor == true) "
            "then data.guardian_id is present",
            data_esc
        )

    def test_ternary_antecedent_false_no_minor(self):
        data_pass = {"data": {
            "beneficiaries": [{"is_minor": False}],
        }}
        r = _eval(
            "if any(data.beneficiaries where is_minor == true) "
            "then data.guardian_id is present",
            data_pass
        )
        assert r.passed


# ---------------------------------------------------------------------------
# 9. parse_expression raises ExpressionError on bad input
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_unterminated_string(self):
        with pytest.raises(ExpressionError):
            parse_expression("data.x == 'hello")

    def test_unexpected_end(self):
        with pytest.raises(ExpressionError):
            parse_expression("data.x ==")

    def test_unclosed_paren(self):
        with pytest.raises(ExpressionError):
            parse_expression("(data.x + data.y")

    def test_unknown_char(self):
        with pytest.raises(ExpressionError):
            parse_expression("data.x @ 1")

    def test_between_missing_and(self):
        with pytest.raises(ExpressionError):
            parse_expression("data.x between 1 2")

    def test_if_without_then(self):
        with pytest.raises(ExpressionError):
            parse_expression("if data.x == 1 data.y is present")

    def test_extra_tokens(self):
        with pytest.raises(ExpressionError):
            parse_expression("data.x == 1 data.y")


# ---------------------------------------------------------------------------
# 10. collect_expression_fields
# ---------------------------------------------------------------------------

class TestCollectFields:
    def test_simple_field_ref(self):
        fields = collect_expression_fields("data.amount <= 1000")
        paths = [p for p, _ in fields]
        assert "data.amount" in paths

    def test_projection(self):
        fields = collect_expression_fields("sum(data.items[].value) == 100")
        paths = [p for p, _ in fields]
        assert any("items" in p and "value" in p for p in paths)

    def test_quantifier_predicate_fields_prefixed(self):
        fields = collect_expression_fields(
            "all(data.beneficiaries where share_percentage > 0)"
        )
        paths = [p for p, _ in fields]
        # array path itself
        assert "data.beneficiaries" in paths
        # predicate field prefixed with array path and []
        assert any("beneficiaries" in p and "share_percentage" in p for p in paths)

    def test_invalid_expression_returns_empty(self):
        # Invalid expression → empty list, no exception
        fields = collect_expression_fields("data.x ==")
        assert fields == []

    def test_presence_op(self):
        fields = collect_expression_fields("data.policy_number is present")
        ops = [op for _, op in fields]
        assert "present" in ops


# ---------------------------------------------------------------------------
# 11. End-to-end: annuity-beneficiary-designation rules
# ---------------------------------------------------------------------------

class TestBeneficiaryRules:
    """Smoke-test the exact expression strings from the new skill's rules.yaml."""

    _PASS_DATA = {
        "policy_number": "ANN-001",
        "beneficiaries": [
            {"name": "Alice", "share_percentage": 60, "is_minor": False},
            {"name": "Bob",   "share_percentage": 40, "is_minor": False},
        ],
        "base_premium": 800.0,
        "rider_premium": 200.0,
        "total_premium": 1000.0,
        "annual_contribution_limit": 6000.0,
    }

    def _d(self, **overrides):
        import copy
        d = copy.deepcopy({"data": self._PASS_DATA})
        d["data"].update(overrides)
        return d

    def test_policy_number_present(self):
        assert passed("data.policy_number is present", self._d())

    def test_policy_number_absent(self):
        d = self._d()
        del d["data"]["policy_number"]
        assert failed("data.policy_number is present", d)

    def test_count_beneficiaries(self):
        assert passed("count(data.beneficiaries) >= 1", self._d())

    def test_sum_shares_100(self):
        assert passed("sum(data.beneficiaries[].share_percentage) == 100", self._d())

    def test_all_shares_positive(self):
        assert passed("all(data.beneficiaries where share_percentage > 0)", self._d())

    def test_none_shares_over_100(self):
        assert passed("none(data.beneficiaries where share_percentage > 100)", self._d())

    def test_premium_adds_up(self):
        assert passed(
            "data.base_premium + data.rider_premium == data.total_premium",
            self._d()
        )

    def test_premium_adds_up_fail(self):
        assert failed(
            "data.base_premium + data.rider_premium == data.total_premium",
            self._d(base_premium=900.0)  # 900 + 200 ≠ 1000
        )

    def test_premium_within_limit(self):
        assert passed(
            "data.total_premium <= data.annual_contribution_limit",
            self._d()
        )

    def test_minor_no_guardian_fails_then_branch(self):
        d = self._d(beneficiaries=[
            {"name": "Emma", "share_percentage": 100, "is_minor": True}
        ])
        r = _eval(
            "if any(data.beneficiaries where is_minor == true) "
            "then data.guardian_id is present",
            d
        )
        # guardian_id absent → then-branch fails (not missing — presence predicate)
        assert not r.passed

    def test_minor_with_guardian_passes(self):
        d = self._d(
            beneficiaries=[
                {"name": "Emma", "share_percentage": 100, "is_minor": True}
            ],
            guardian_id="GRD-001"
        )
        assert passed(
            "if any(data.beneficiaries where is_minor == true) "
            "then data.guardian_id is present",
            d
        )
