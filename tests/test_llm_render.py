"""df_to_llm_text: small frames byte-identical, large frames elided."""

import pandas as pd

from beamtimehero_cli.spec_data.scans import df_to_llm_text


def _frame(n):
    return pd.DataFrame({"energy": range(n), "counts": range(n)}).set_index("energy")


def test_small_frame_is_byte_identical():
    df = _frame(200)
    assert df_to_llm_text(df) == df.to_string()


def test_large_frame_is_elided():
    df = _frame(1000)
    out = df_to_llm_text(df)
    assert "800 of 1000 rows elided" in out
    assert len(out) < len(df.to_string()) / 3
    # head block ends at row 99, tail block starts at row 900,
    # the middle is gone
    assert "99" in out and "900" in out and "999" in out
    assert "\n500 " not in out
