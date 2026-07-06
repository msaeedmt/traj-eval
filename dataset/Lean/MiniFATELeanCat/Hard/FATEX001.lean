/-
Source: FATE-X 1
Difficulty: Hard

Informal statement:
Let R be a unique factorization domain with two nonassociate prime elements
p and q.

Assume every prime element of R is associated to either p or q. Prove that
R is a principal ideal domain.
-/

import Mathlib.RingTheory.UniqueFactorizationDomain.Basic
import Mathlib.RingTheory.Ideal.Span

namespace MiniFATELeanCat.Hard.FATEX001

theorem fatex_001_isPrincipalIdealRing_of_associated_or_associated {R : Type} [CommRing R] [IsDomain R]
    [UniqueFactorizationMonoid R] {p q : R} (hp : Prime p) (hq : Prime q) (hpq : ¬ Associated p q)
    (h : ∀ {x : R}, Prime x → Associated x p ∨ Associated x q) :
    IsPrincipalIdealRing R := by
  sorry

end MiniFATELeanCat.Hard.FATEX001
