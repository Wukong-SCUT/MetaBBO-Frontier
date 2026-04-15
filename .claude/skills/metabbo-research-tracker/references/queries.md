# MetaBBO Query Set

Use these queries for arXiv scans. Keep query syntax compatible with arXiv API `search_query`.

## Priority 1: Core MetaBBO

- `all:"meta black box optimization"`
- `all:"meta-black-box-optimization"`
- `all:"learning to optimize" AND all:"black-box"`
- `ti:"learned optimizer" AND all:"evolutionary"`
- `all:"automated algorithm design" AND all:"black-box optimization"`

## Priority 2: Meta-Level Algorithm Design

- `all:"algorithm selection" AND all:"black-box optimization"`
- `all:"algorithm configuration" AND all:"differential evolution"`
- `all:"adaptive operator selection" AND all:"evolutionary algorithm"`
- `all:"hyperparameter control" AND all:"evolutionary computation"`
- `all:"dynamic algorithm selection" AND all:"evolutionary"`

## Priority 3: Emerging Directions

- `all:"LLM" AND all:"algorithm design" AND all:"black-box optimization"`
- `all:"in-context optimization" AND all:"black-box"`
- `all:"symbolic optimizer" AND all:"evolutionary"`
- `all:"neuroevolution" AND all:"optimizer"`
- `all:"foundation model" AND all:"optimization algorithm"`
- `all:"meta learning" AND all:"black-box optimization"`

## Notes

- Preferred sort: submitted date descending.
- Recommended scan frequency: weekly.
- If recall is too low, add broader queries temporarily, then tighten by manual filtering.
