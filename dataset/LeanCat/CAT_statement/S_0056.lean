import Mathlib

open CategoryTheory Functor

variable {C : Type u₁} [Category.{v₁} C] {D : Type u₂} [Category.{v₂} D]

theorem hasLeftAdjoint_iff_ran_id_preserved (G : D ⥤ C) :
    G.IsRightAdjoint ↔
    ∃ (R : C ⥤ D) (α : G ⋙ R ⟶ 𝟭 D),
      R.IsRightKanExtension α ∧
      (R ⋙ G).IsRightKanExtension ((associator G R G).inv ≫ whiskerRight α G ≫ (leftUnitor G).hom) := by
  sorry
