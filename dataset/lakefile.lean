import Lake
open Lake DSL

package TrajEvalBenchmarks where
  leanOptions := #[
    ⟨`pp.unicode.fun, true⟩,
    ⟨`pp.proofs.withType, false⟩
  ]

require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @ "v4.30.0"

@[default_target]
lean_lib FATEH

@[default_target]
lean_lib FATEM

@[default_target]
lean_lib FATEX

@[default_target]
lean_lib LeanCat.CAT_statement

lean_lib TrajEvalBenchmarks where
  roots := #[`Benchmarks]
