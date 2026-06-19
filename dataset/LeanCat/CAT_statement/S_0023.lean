/-
Difficulty: Medium
Informal statement:
Theorem: Let $A,B$ be rings and $\phi : A \to B$ be a ring homomorphism. The functor $\phi_* : B-\mathcal{M}\mathrm{od} \to A-\mathcal{M}\mathrm{od}$ between their module categories is defined by $(N,l_N) \mapsto (N,l_N \circ (\phi \otimes \mathrm{id}))$. Then the functor $\phi_*$ admits a left adjoint $\phi^* := B \otimes_A -: A-\mathcal{M}\mathrm{od} \to B-\mathcal{M}\mathrm{od}$ and a right adjoint $\phi^! := \hom_A(B,-) : A-\mathcal{M}\mathrm{od} \to B-\mathcal{M}\mathrm{od}$.
-/

import Mathlib

open CategoryTheory

theorem ring_hom_induced_functor_has_adjoints
    {A B : RingCat} (φ : A ⟶ B) :
    ∃ (φ_pull : ModuleCat B ⥤ ModuleCat A)
      (φ_push : ModuleCat A ⥤ ModuleCat B)
      (φ_coind : ModuleCat A ⥤ ModuleCat B),
      Nonempty (Adjunction φ_push φ_pull) ∧ Nonempty (Adjunction φ_pull φ_coind) := by
  sorry
