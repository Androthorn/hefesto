"""
Importer for Simulator Output Data.

This script parses the specific folder structure and CSV files produced by the simulator/analyzer
and converts them into ADRS ExperimentRun objects.
"""

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from adrs.core.importer import BaseImporter
from adrs.schemas.input import ExperimentRun, LogEntry, MetricStats, AgentPrompt, PromptTemplate


class SimulatorImporter(BaseImporter):
    def import_runs(self, source: Path, **kwargs: Any) -> list[ExperimentRun]:
        """
        Import simulator runs from output directory.
        
        Args:
            source: Path to the analyzer/output directory
            **kwargs: Optional arguments:
                - pattern: Glob pattern to filter run directories (e.g., "google-gemini*0.5*")
                - prompt_file: Path to the prompt text file to import
                - prompt_output: Directory to save the imported prompt JSON
        """
        runs = []
        pattern = kwargs.get('pattern', '*')
        prompt_file = kwargs.get('prompt_file')
        prompt_output = kwargs.get('prompt_output')
        
        # The simulator output has folders like:
        # anthropic-claude-haiku-4.5_input_const_v2_0.1_run1
        # [MODEL]_[PROMPT_VERSION]_[RUN_ID]
        
        if not source.is_dir():
            raise ValueError(f"Source must be a directory: {source}")
            
        # Iterate over all run directories matching the pattern
        for run_dir in source.glob(pattern):
            if not run_dir.is_dir():
                continue
                
            dir_name = run_dir.name
            
            # Basic parsing of directory name
            # Expecting format: agent-name_prompt-version_runX
            # This regex is a best-effort approximation based on observed folder names
            # "anthropic-claude-haiku-4.5_input_const_v2_0.1_run1"
            
            # Let's try to extract run_id (last part) and treat the rest as agent/config
            match = re.search(r'_run(\d+)$', dir_name)
            if not match:
                # Skip directories that don't look like runs
                continue
                
            run_number = match.group(1)
            # Everything before the last underscore is the "agent configuration"
            agent_config = dir_name[:match.start()]
            
            # Try to extract temperature (last float before run)
            # e.g. ..._v2_0.1_run1 -> 0.1
            temperature = None
            temp_match = re.search(r'_(\d+\.\d+)$', agent_config)
            if temp_match:
                temperature = float(temp_match.group(1))
                # Remove temperature from config string for further parsing
                agent_config = agent_config[:temp_match.start()]
            
            # Try to grab version if present (e.g. v2)
            version_match = re.search(r'_(v\d+.*)$', agent_config)
            if version_match:
                version = version_match.group(1)
                model_name = agent_config[:version_match.start()]
            else:
                version = "unknown"
                model_name = agent_config
            
            # The agent_name is always "consolidator_agent" since the summary
            # represents the final output from the multi-agent system
            agent_name = "consolidator_agent"

            summary_dir = run_dir / "summary"
            if not summary_dir.exists():
                print(f"Skipping {dir_name}: no summary directory")
                continue
                
            # Find the summary metrics CSV file
            csv_files = list(summary_dir.glob("summary_metrics_*.csv"))
            if not csv_files:
                print(f"Skipping {dir_name}: no summary_metrics CSV found")
                continue
                
            # Use the first one found
            csv_file = csv_files[0]
            
            try:
                metrics = self._parse_summary_csv(csv_file)
                
                # Get timestamp from file metadata or filename
                timestamp_str = csv_file.stem.replace("summary_metrics_", "")
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d-%H-%M-%S")
                except ValueError:
                    timestamp = datetime.now()

                run = ExperimentRun(
                    run_id=dir_name,  # Use full directory name as unique ID
                    timestamp=timestamp,
                    prompt_version=version,
                    agent_name=agent_name,
                    metrics=metrics,
                    logs=[], # Logs not currently in summary CSV
                    metadata={
                        "original_dir": str(run_dir),
                        "temperature": temperature,
                        "model": model_name
                    }
                )
                runs.append(run)
                
            except Exception as e:
                print(f"Error processing {dir_name}: {e}")
                continue
        
        # Import prompt file if provided
        if prompt_file and prompt_output:
            try:
                self._import_prompt(prompt_file, prompt_output, runs)
            except Exception as e:
                print(f"Warning: Could not import prompt file: {e}")
                
        return runs
    
    def _import_prompt(self, prompt_file: Path, output_dir: Path, runs: list[ExperimentRun]) -> None:
        """Import a prompt text file and convert to ADRS format."""
        if not prompt_file.exists():
            print(f"Prompt file not found: {prompt_file}")
            return
        
        # Read the prompt file
        with open(prompt_file, 'r') as f:
            prompt_text = f.read()
        
        # Extract version from runs if available
        version = "v2" if runs and runs[0].prompt_version else "v1.0"
        
        # Create AgentPrompt structure
        # For the consolidator agent, the prompt is typically a system prompt
        agent_prompt = AgentPrompt(
            agent_name="consolidator_agent",
            version=version,
            template=PromptTemplate(
                system=prompt_text.strip(),
                user="{{input_data}}",
                variables=["input_data"]
            ),
            constraints=[
                "Must output valid JSON",
                "Must provide clear reasoning",
                "Must balance performance and cost considerations"
            ]
        )
        
        # Save to output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"consolidator_agent_{version}.json"
        
        with open(output_file, 'w') as f:
            json.dump(agent_prompt.model_dump(), f, indent=2)
        
        print(f"✓ Imported prompt to: {output_file}")

    def _parse_summary_csv(self, file_path: Path) -> dict[str, MetricStats]:
        metrics = {}
        
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            # The CSV format seems to be:
            # ,mean,min,max,std,median
            # metric_name,val,val,val,val,val
            
            # The first column name is empty string based on "view_file" output
            
            for row in reader:
                # The first key is likely '' or None for the metric name column
                metric_name = row.get('', row.get(None)) 
                
                if not metric_name:
                    # iterate to find the key that corresponds to the name
                    # assuming it's the first one
                    metric_name = list(row.values())[0]

                if not metric_name:
                    continue
                    
                metrics[metric_name] = MetricStats(
                    mean=float(row.get('mean', 0) or 0),
                    min=float(row.get('min', 0) or 0),
                    max=float(row.get('max', 0) or 0),
                    std=float(row.get('std', 0) or 0),
                    median=float(row.get('median', 0) or 0)
                )
                
        return metrics
