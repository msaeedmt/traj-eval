import Mathlib

open CategoryTheory Limits

theorem forget_Grp_createsLimits_but_not_coproducts :
    Nonempty (CreatesLimits (forget GrpCat.{u})) ∧
    ¬ Nonempty (PreservesColimitsOfShape (Discrete Bool) (forget GrpCat.{u})) := by
  sorry

theorem forget_Ab_createsLimits_but_not_coproducts :
    Nonempty (CreatesLimits (forget Ab.{u})) ∧
    ¬ Nonempty (PreservesColimitsOfShape (Discrete Bool) (forget Ab.{u})) := by
  sorry

theorem forget_RingCat_createsLimits_but_not_coproducts :
    Nonempty (CreatesLimits (forget RingCat.{u})) ∧
    ¬ Nonempty (PreservesColimitsOfShape (Discrete Bool) (forget RingCat.{u})) := by
  sorry
