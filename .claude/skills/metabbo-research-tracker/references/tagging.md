# MetaBBO Tagging Guide

Use this guide to interpret or correct auto-generated tags.

## Meta Task Tags

- `AS` (Algorithm Selection)
- `AC` (Algorithm Configuration)
- `SM` (Solution Manipulation / Learned Optimizer)
- `AG` (Algorithm Generation)

## Learning Paradigm Tags

- `RL` (Reinforcement Learning)
- `SL` (Supervised Learning / Imitation)
- `NE` (Neuroevolution)
- `ICL` (In-Context Learning / LLM prompting)

## Problem Type Tags

- `SOP` Single-objective optimization
- `MOOP` Multi-objective optimization
- `CMOP` Constrained multi-objective optimization
- `MMOP` Multimodal optimization
- `LSOP` Large-scale optimization
- `COP` Combinatorial optimization
- `Other` Unclear or mixed

## Priority Recommendation

- `P1`: Directly proposes MetaBBO methods, benchmarks, or cross-problem generalization studies.
- `P2`: Focuses on one MetaBBO sub-task (AS/AC/SM/AG) with clear empirical evidence.
- `P3`: Adjacent work (LLM optimization, neuroevolution, AutoML optimizer design) that may influence MetaBBO.

## Quick Manual Checks

- If abstract mentions "policy" + "operator/parameter control", prefer `AC` + `RL`.
- If abstract mentions "learned optimizer" or trajectory prediction, prefer `SM`.
- If abstract mentions generating algorithm code/rules/expressions, prefer `AG`.
- If abstract only says "optimize hyperparameters for model training" without BBO framing, tag `Other` and lower priority.
