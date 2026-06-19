/-
Difficulty: High
Informal statement:
Theorem: Let $\mathcal{C}$ be a complete, wellpowered, cowellpowered and have a separator $s$.
    Then $\mathcal{C}$ is cocomplete if and only if for each set $I$, there exists an $I$-th copower of $S$ in $\mathcal{C}$.
-/

import Mathlib

open CategoryTheory Limits

variable {C : Type u} [Category.{v} C]

def LeanCatIsSeparator (_S : C) : Prop := True

theorem hasColimits_iff_hasCoprod_of_separator
    [HasLimits C]
    [WellPowered.{v} C]
    [WellPowered.{v} Cᵒᵖ]
    (S : C) (hS : LeanCatIsSeparator S) :
    HasColimits C ↔ ∀ (I : Type v), HasColimit (Discrete.functor (fun (_ : I) => S)) := by
  sorry
