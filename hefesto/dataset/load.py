import json
from hefesto.schemas.core import TestCase
from hefesto.dataset.base import DatasetSplit
from hefesto.dataset.split import split_cases


class LoadedDataset:
    def __init__(self, path: str, test_fraction: float) -> None:
        self.path = path
        self.test_fraction = test_fraction

    def provide(self) -> DatasetSplit:
        cases: list[TestCase] = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                cases.append(TestCase.model_validate(json.loads(line)))
        return split_cases(cases, self.test_fraction)
