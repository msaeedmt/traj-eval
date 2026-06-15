import Mathlib

open CategoryTheory Limits

namespace CAT_statement_S_0062

universe u v
variable {C : Type u} [Category.{v} C]

def IsSeparating (S : Set C) : Prop :=
  ObjectProperty.IsSeparating (fun X => X ∈ S : ObjectProperty C)

def IsIntersectionOf {B : C} (A : Subobject B) (S : Set (Subobject B)) : Prop :=
   (∀ Ai, Ai ∈ S → A ≤ Ai) ∧
  (∀ A' : Subobject B, (∀ Ai, Ai ∈ S → A' ≤ Ai) → A' ≤ A)

def HasIntersections (C : Type u) [Category.{v} C]: Prop :=
  ∀ (B : C) (S : Set (Subobject B)),
    ∃ A : Subobject B, IsIntersectionOf (C := C) (B := B) A S

class StronglyComplete (C : Type u) [Category.{v} C] : Prop where
  complete: HasLimits C
  hasinter: HasIntersections C

class StronglyCocomplete (C : Type u) [Category.{v} C] : Prop where
  dual: StronglyComplete (C:=Cᵒᵖ)

theorem strongly_complete_of_strongly_cocomplete_of_separating_set [StronglyComplete Cᵒᵖ] {𝒢 : Set C} [Small.{v} 𝒢] (h𝒢 : IsSeparating 𝒢) :
    StronglyComplete C := by
  sorry

end CAT_statement_S_0062
