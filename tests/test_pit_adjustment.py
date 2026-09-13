import pandas as pd

from ty_quant_node.data.pit_adjustment import build_pit_adjustment


def _market():
    return pd.DataFrame([
        {"instrument": "AAA", "datetime": "2024-01-01", "open_raw": 10, "high_raw": 11, "low_raw": 9, "close_raw": 10, "volume_raw": 100},
        {"instrument": "AAA", "datetime": "2024-01-02", "open_raw": 5, "high_raw": 6, "low_raw": 4, "close_raw": 5, "volume_raw": 200},
        {"instrument": "AAA", "datetime": "2024-01-03", "open_raw": 5.5, "high_raw": 6.5, "low_raw": 4.5, "close_raw": 5.5, "volume_raw": 210},
    ])


def test_pit_factor_is_causal_and_future_events_do_not_rewrite_history():
    frame = _market()
    first = build_pit_adjustment(frame, [
        {"instrument": "AAA", "effective_date": "2024-01-02", "price_multiplier": 2.0, "split_multiplier": 2.0, "knowledge_date": "2024-01-02"},
    ], snapshot_id="s1")
    second = build_pit_adjustment(frame, [
        {"instrument": "AAA", "effective_date": "2024-01-02", "price_multiplier": 2.0, "split_multiplier": 2.0, "knowledge_date": "2024-01-02"},
        {"instrument": "AAA", "effective_date": "2024-01-03", "price_multiplier": 1.1, "split_multiplier": 1.0, "knowledge_date": "2024-01-03"},
    ], snapshot_id="s2")
    first_hist = first[first.datetime <= pd.Timestamp("2024-01-02")]
    second_hist = second[second.datetime <= pd.Timestamp("2024-01-02")]
    assert first_hist["ty_close"].tolist() == second_hist["ty_close"].tolist()
    assert first_hist["ty_price_factor"].tolist() == [1.0, 2.0]
    assert first_hist["ty_volume"].tolist() == [100.0, 100.0]


def test_pit_rejects_duplicate_or_missing_event_multiplier():
    frame = _market()
    duplicate = [
        {"instrument": "AAA", "effective_date": "2024-01-02", "price_multiplier": 2.0, "split_multiplier": 2.0},
        {"instrument": "AAA", "effective_date": "2024-01-02", "price_multiplier": 2.0, "split_multiplier": 2.0},
    ]
    try:
        build_pit_adjustment(frame, duplicate, snapshot_id="bad")
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("expected duplicate event failure")


def test_pit_accepts_announcement_before_effective_date():
    adjusted = build_pit_adjustment(
        _market(),
        [
            {
                "instrument": "AAA",
                "effective_date": "2024-01-02",
                "knowledge_date": "2024-01-01",
                "price_multiplier": 2.0,
                "split_multiplier": 2.0,
            }
        ],
        snapshot_id="announcement-before-effective",
    )
    assert adjusted.loc[adjusted["datetime"] == "2024-01-01", "ty_price_factor"].iloc[0] == 1.0
    assert adjusted.loc[adjusted["datetime"] == "2024-01-02", "ty_price_factor"].iloc[0] == 2.0


def test_pit_accepts_empty_event_list_as_identity_adjustment():
    adjusted = build_pit_adjustment(_market(), [], snapshot_id="no-events")

    assert adjusted["ty_price_factor"].tolist() == [1.0, 1.0, 1.0]
    assert adjusted["ty_split_factor"].tolist() == [1.0, 1.0, 1.0]
