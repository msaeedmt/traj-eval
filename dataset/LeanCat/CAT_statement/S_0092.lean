/-
Difficulty: Medium
Informal statement:
Theorem: Let $R$ be a ring. The forgetful functor from the category $\mathcal{M}\mathrm{od}_R$ of $R$-modules to the category $\mathcal{A}\mathrm{b}$ of abelian groups creates all colimits that $\mathcal{A}\mathrm{b}$ admits.
-/

import Mathlib

open CategoryTheory Limits

variable {R : Type u} [CommRing R]


theorem ModuleCat.forgetCreatesColimits :
    Nonempty (CreatesColimits (forget₂ (ModuleCat R) AddCommGrpCat)) := by
    sorry
