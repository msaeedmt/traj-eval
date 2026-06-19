/-
Difficulty: Medium
Informal statement:
Theorem: Let $F:\mathcal{G}\mathrm{rp}\to \mathcal{S}\mathrm{et}$ be the functor that $G\mapsto \{g\in G\mid g^2=1\}$.
    Then $F$ is representable.
-/

import Mathlib

open CategoryTheory

axiom functor_involution : GrpCat.{u} ⥤ Type u


theorem involution_functor_representable :
    CategoryTheory.Functor.IsCorepresentable functor_involution := by
  sorry
