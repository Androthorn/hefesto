from typing import Protocol
from pydantic import BaseModel, Field
from hefesto.schemas.core import TestCase


class DatasetSplit(BaseModel):
    dev: list[TestCase] = Field(default_factory=list)
    test: list[TestCase] = Field(default_factory=list)


class DatasetSource(Protocol):
    def provide(self) -> DatasetSplit: ...
