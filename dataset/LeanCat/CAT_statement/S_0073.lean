/-
Difficulty: Medium
Informal statement:
Definition: A functor $F : \mathcal C \to \mathcal D$ is said to $\textbf{lift limits}$ if for every diagram $D: \mathcal I\to \mathcal C$ and every limit $L$ of $F\circ D$, there exists a limit $L'\in\mathcal D$ such that $F(L')\cong L$.


Theorem: The forgetful functor $U:\mathcal{T}\mathrm{op}\to \mathcal{S}\mathrm{et}$ lifts limits, but not reflects limits.
-/

import Mathlib

open CategoryTheory Limits

namespace CAT_statement_S_0073

universe w' w₂' w w₂ v₁ v₂ v₃ u₁ u₂ u₃

variable {C : Type u₁} [Category.{v₁} C]
variable {D : Type u₂} [Category.{v₂} D]
variable {J : Type w} [Category.{w'} J] {K : J ⥤ C}

class LiftsLimit  (K : J ⥤ C) (F : C ⥤ D): Prop where
    lifts {c : Cone (K ⋙ F)} (hc : IsLimit c) :
      ∃ c' : Cone K, Nonempty (IsLimit c') ∧ Nonempty (F.mapCone c' ≅ c)

class LiftsLimitsOfShape (J : Type w) [Category.{w'} J] (F : C ⥤ D) : Prop where
  liftsLimit : ∀ {K : J ⥤ C}, LiftsLimit K F := by infer_instance

@[nolint checkUnivs, pp_with_univ]
class LiftsLimitsOfSize (F : C ⥤ D) : Prop where
  liftsLimitsOfShape : ∀ {J : Type w} [Category.{w'} J], LiftsLimitsOfShape J F := by
    infer_instance

abbrev LiftsLimits (F : C ⥤ D) :=
  LiftsLimitsOfSize.{v₂, v₂} F

theorem TopCat_forget_lifts_and_not_reflects_limits :
    LiftsLimits (forget TopCat) ∧ IsEmpty (ReflectsLimits (forget TopCat)):= by
  sorry

end CAT_statement_S_0073
