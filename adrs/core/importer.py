"""
Base importer interface for ADRS.
Allows users to implement custom logic for importing experiment runs from various sources.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from adrs.schemas.input import ExperimentRun


class BaseImporter(ABC):
    """
    Abstract base class for experiment run importers.
    
    Users should subclass this and implement the `import_runs` method
    to convert their custom data format into ADRS ExperimentRun objects.
    """
    
    @abstractmethod
    def import_runs(self, source: Path, **kwargs: Any) -> list[ExperimentRun]:
        """
        Import experiment runs from a source.
        
        Args:
            source: Path to the data source (directory or file)
            **kwargs: Additional arguments passed from the CLI
            
        Returns:
            List of ExperimentRun objects
        """
        pass
