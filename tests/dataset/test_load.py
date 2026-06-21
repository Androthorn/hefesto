from hefesto.dataset.load import LoadedDataset


def test_loads_jsonl(tmp_path):
    p = tmp_path / "cases.jsonl"
    p.write_text(
        '{"input": "a", "expected": "1"}\n'
        '{"input": "b"}\n'
        '{"input": "c"}\n'
        '{"input": "d"}\n'
    )
    split = LoadedDataset(path=str(p), test_fraction=0.5).provide()
    assert len(split.dev) == 2 and len(split.test) == 2
    assert split.dev[0].input == "a" and split.dev[0].expected == "1"
