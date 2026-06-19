/-
Difficulty: Medium
Informal statement:
Theorem: Let $\{*\}\in\mathcal{S}\mathrm{et}$ be the terminal object in $\mathcal{S}\mathrm{et}$.Then $\hom_{\mathcal{S}\mathrm{et}}(\{*\},-):\mathcal{S}\mathrm{et}\to\mathcal{S}\mathrm{et}$ is an equivalence of categories.
-/

import Mathlib

open CategoryTheory

universe u

opaque fromTerminalFunctor : Type u ⥤ Type u


theorem fromTerminalEquivalence : fromTerminalFunctor.IsEquivalence := sorry
