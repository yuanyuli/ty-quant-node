from ty_quant_node.factors.registry import load_factor_specs


def test_builtin_ty_factor_registry_has_versioned_specs():
    specs = load_factor_specs()
    names = {spec.name for spec in specs}
    assert {"TY_MOM_5", "TY_MOM_20", "TY_VOL_20", "TY_VOLUME_RATIO_20"}.issubset(names)
    assert all(spec.version for spec in specs)
    assert all(spec.lookback >= 0 for spec in specs)


def test_registry_rejects_duplicate_factor_names(tmp_path):
    (tmp_path / "a.yaml").write_text("name: DUP\nversion: '1'\nexpression: '$ty_close'\ninputs: [ty_close]\nlookback: 0\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("name: DUP\nversion: '1'\nexpression: '$ty_close'\ninputs: [ty_close]\nlookback: 0\n", encoding="utf-8")
    try:
        load_factor_specs(tmp_path)
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("expected duplicate factor failure")
