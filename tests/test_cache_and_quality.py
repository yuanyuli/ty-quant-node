import pandas as pd
import pytest

from ty_quant_node.backend.qlib_backend import build_dataset_from_frame
from ty_quant_node.core.cache import ArtifactCache, cache_key


def test_cache_key_is_deterministic_and_versioned(tmp_path):
    first = cache_key({"adjustment": "qfq"}, {"raw": "abc"}, {"qlib": "0.9.7"})
    second = cache_key({"adjustment": "qfq"}, {"raw": "abc"}, {"qlib": "0.9.7"})
    changed = cache_key({"adjustment": "hfq"}, {"raw": "abc"}, {"qlib": "0.9.7"})
    assert first == second and first != changed
    cache = ArtifactCache(tmp_path)
    path = cache.path_for(first, ".json")
    path.write_text("{}", encoding="utf-8")
    assert cache.valid(first, ".json")


def test_missing_factor_blocks_dataset_build(market_frame):
    broken = market_frame.copy()
    broken.loc[0, "adj_factor"] = None
    with pytest.raises(ValueError, match="复权因子"):
        build_dataset_from_frame(broken, adjustment="qfq")
