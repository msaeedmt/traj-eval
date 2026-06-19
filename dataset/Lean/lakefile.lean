import Lake
open Lake DSL

package TrajEvalBenchmarks where

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @ "v4.30.0"

lean_lib TrajEvalBenchmarks where
  roots := #[`Benchmarks]
