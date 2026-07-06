/-
Source: FATE-X 48
Difficulty: Hard

Informal statement:
A commutative ring A is absolutely flat if every A-module is flat.

Prove that A is absolutely flat if and only if every principal ideal is
idempotent.
-/

import Mathlib.RingTheory.Flat.Basic
import Mathlib.RingTheory.Ideal.Operations

namespace MiniFATELeanCat.Hard.FATEX048

/--
A commutative ring is absolutely flat if every module over it is flat.
-/
class IsAbsolutelyFlat (R : Type) [CommRing R] : Prop where
  out ⦃P : Type⦄ [AddCommGroup P] [Module R P] : Module.Flat R P


theorem fatex_048_isAbsolutelyFlat_iff_principal_ideal_idempotent
    (R : Type) [CommRing R] :
    IsAbsolutelyFlat R ↔ (∀ I : Ideal R, I.IsPrincipal → I ^ 2 = I) := by
  sorry

end MiniFATELeanCat.Hard.FATEX048
