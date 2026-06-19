/-
Difficulty: Medium
Informal statement:
Definition: A functor is called $\textbf{left exact}$ if it preserves all finite limits.


Theorem: Let $\mathcal{A}$ and $\mathcal{B}$ be abelian categories and $F:\mathcal{A}\to\mathcal{B}$ be a functor. Then $F$ is left exact if and only if $F$ is additive and $F$ maps each exact sequence $0\to x\to y\to z$ to an exact sequence $0\to F(x)\to F(y)\to F(z)$.
-/

import Mathlib

open CategoryTheory Functor Limits ShortComplex

variable {C D : Type*} [Category C] [Category D]
variable [Abelian C] [Abelian D]

theorem preservesFiniteLimits_tfae
    (F : C ⥤ D) [F.Additive] : List.TFAE
    [
      ∀ (S : ShortComplex C), S.ShortExact → (S.map F).Exact ∧ Mono (F.map S.f),
      ∀ (S : ShortComplex C), S.Exact ∧ Mono S.f → (S.map F).Exact ∧ Mono (F.map S.f),
      ∀ ⦃X Y : C⦄ (f : X ⟶ Y), PreservesLimit (parallelPair f 0) F,
      PreservesFiniteLimits F
    ] := by
  sorry
