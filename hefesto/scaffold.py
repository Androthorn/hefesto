CONFIG_YAML = """\
providers:
  default: { provider: <required>, model: <required> }
  runner:  { provider: <required>, model: <required>, temperature: 0.7 }
  judge:   { provider: <required>, model: <required>, temperature: 0.0 }
  refiner: { provider: <required>, model: <required>, temperature: 0.7 }
  dataset: { provider: <required>, model: <required>, temperature: 1.0 }

objective: ./objective.yaml
prompt: ./prompt.txt

dataset:
  source: generate
  count: 20
  test_fraction: 0.4

grader: llm_judge

judge:
  mode: pairwise
  require_different_model: true
  min_agreement: 0.7

loop:
  max_iter: 5
  patience: 2
  k: 3  # best and worst dev cases shown to the refiner
  delta_min: 0.05  # minimum improvement a candidate must beat
  alpha: 0.05  # one-sided significance level of the promotion gate
  judge_samples: 1
  headroom_min: 0.05

store_path: ./hefesto.db
"""

OBJECTIVE_YAML = """\
goal: "Describe what 'better' means for this prompt, in plain language."
weights: {}
success_criteria: []
invariants: []
"""

PROMPT_TXT = "You are a helpful assistant.\n\nUser request: {{input}}\n"
