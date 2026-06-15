import Mathlib

open CategoryTheory

axiom functor_involution : GrpCat.{u} ⥤ Type u


theorem involution_functor_representable :
    CategoryTheory.Functor.IsCorepresentable functor_involution := by
  sorry
