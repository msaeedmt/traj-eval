/-
Difficulty: Medium
Informal statement:
Theorem: Let $G_1$ and $G_2$ be two objects in the category $\mathcal{G}\mathrm{rp}$ of groups.\nomenclature{$\mathcal{G}\mathrm{rp}$}{the category of groups}
The coproduct of $G_1$ and $G_2$ in $\mathcal{G}\mathrm{rp}$ is equivalent to the free product of $G_1$ and $G_2$.
-/

import Mathlib

open CategoryTheory Limits

universe u
variable {G H : GrpCat.{u}}


theorem freeProdGrp_iso_coprod [HasBinaryCoproduct G H] :
     Nonempty (Monoid.Coprod G H ≅ coprod G H) := by
  sorry
