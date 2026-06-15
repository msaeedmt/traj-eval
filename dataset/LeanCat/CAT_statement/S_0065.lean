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
