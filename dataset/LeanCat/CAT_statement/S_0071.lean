/-
Difficulty: Medium
Informal statement:
Definition: A functor $F : \mathcal C \to \mathcal D$ is said to $\textbf{lift limits}$ if for every diagram $D: \mathcal I\to \mathcal C$ and every limit $L$ of $F\circ D$, there exists a limit $L'\in\mathcal D$ such that $F(L')\cong L$.


Theorem: A functor that lifts equalizers is faithful if and only if it reflects epimorphisms.
-/

import Mathlib

open CategoryTheory Limits

namespace CAT_statement_S_0071

universe uC vC uD vD w w'

variable {C : Type uC} [Category.{vC} C]
variable {D : Type uD} [Category.{vD} D]
variable (F : C ⥤ D)
variable {J : Type w} [Category.{w'} J]

class LiftsLimit  (K : J ⥤ C) (F : C ⥤ D): Prop where
    lifts {c : Cone (K ⋙ F)} (hc : IsLimit c) :
      ∃ c' : Cone K, Nonempty (IsLimit c') ∧ Nonempty (F.mapCone c' ≅ c)

class LiftsLimitsOfShape (J : Type w) [Category.{w'} J] (F : C ⥤ D) : Prop where
  liftsLimit : ∀ {K : J ⥤ C}, LiftsLimit K F := by infer_instance

theorem functor_faithful_iff_reflectsEpimorphisms_of_liftsEqualizers
    [LiftsLimitsOfShape Limits.WalkingParallelPair F] :
    F.Faithful ↔ F.ReflectsEpimorphisms := by
  sorry

end CAT_statement_S_0071
