/-
Difficulty: Medium
Informal statement:
Theorem: If $\mathcal{D}$ admits coequalizers, a functor $G : \mathcal{D} \to \mathcal{C}$ is monadic if $G$ has a left adjoint, conservative and preserves coequalizers.
-/

import Mathlib

open CategoryTheory Limits

universe u₁ u₂ v₁

variable {C : Type u₁} {D : Type u₂} [Category.{v₁} C] [Category.{v₁} D]
variable {G : D ⥤ C} {F : C ⥤ D} (adjFG : F ⊣ G)
variable [HasCoequalizers D]
variable [G.ReflectsIsomorphisms]
variable [PreservesColimitsOfShape WalkingParallelPair G]


theorem monadicOfConservativePreservesCoequalizers :
    Nonempty (MonadicRightAdjoint G) := by
    sorry
