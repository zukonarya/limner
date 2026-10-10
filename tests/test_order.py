import json

import pytest

from limner.core.order import MAX_ORDER_BYTES, OrderError, parse_fields



def _order(**changes):
    order = {
        "schema_version": "1",
        "action": "send",
        "project": "demo-site",
        "phase": "01-nav",
        "prompt": "A blue square",
        "adjustments": [],
        "references": [{"source": "ref.png", "label": "logo"}],
        "provider": "fal",
        "routing_rule": "R1",
        "settings": {},
        "cost_estimate": {"amount_usd": 0.04, "basis": "one image"},
        "approval": "yes",
        "return_dir": "out",
    }
    for key, value in changes.items():
        if value is ...:
            order.pop(key)
        else:
            order[key] = value
    return json.dumps(order).encode()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[1, 2]",
        b"\xff\xfe",
        b'{"a": 1, "a": 2}',
        b'{"amount": NaN}',
        b"{" + b" " * MAX_ORDER_BYTES + b"}",
    ],
)
def test_malformed_input_is_refused(raw):
    with pytest.raises(OrderError):
        parse_fields(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "2"},
        {"action": "draft"},
        {"project": ...},
        {"prompt": ""},
        {"approval": ""},
        {"surprise": 1},
        {"job_id": "x"},
        {"caller_workspace": "/x"},
        {"received_at": "now"},
        {"project": "Demo_Site"},
        {"phase": "nav"},
        {"caller_name": "Bad Name"},
        {"version": True},
        {"version": 0},
        {"version": 1.5},
        {"parent_version": -1},
        {"adjustments": [{"rule": "r", "before": "a"}]},
        {"adjustments": [{"rule": "r", "before": "a", "after": 1}]},
        {"feedback_on_parent": {"user_verdict": "ok"}},
        {"references": [{"source": "ref.png"}]},
        {"references": "ref.png"},
        {"cost_estimate": {"amount_usd": -1, "basis": "b"}},
        {"cost_estimate": {"amount_usd": True, "basis": "b"}},
        {"cost_estimate": {"amount_usd": 1}},
        {"user_words": 5},
    ],
)
def test_invalid_fields_are_refused(changes):
    with pytest.raises(OrderError):
        parse_fields(_order(**changes))


def test_valid_fields_are_returned():
    fields = parse_fields(_order(caller_name="demo-caller", version=2, user_words="blue"))
    assert fields["project"] == "demo-site" and fields["version"] == 2


def test_error_messages_carry_no_control_characters():
    with pytest.raises(OrderError) as exc:
        parse_fields(_order(project="\x1b[31mevil"))
    assert "\x1b" not in str(exc.value)
