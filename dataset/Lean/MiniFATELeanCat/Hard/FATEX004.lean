/-
Source: FATE-X 4
Difficulty: Hard

Informal statement:
Let p be an odd prime number, and let G be a finite group of order
p times p plus one.

Assume that G has no normal Sylow p-subgroup. Prove that p plus one is a
power of two.
-/

import Mathlib.GroupTheory.Sylow

namespace MiniFATELeanCat.Hard.FATEX004

theorem fatex_004_add_one_eq_two_pow_of_sylow_subgroup_not_normal
    (p : ℕ) (h_odd : Odd p) (G : Type) (hp : p.Prime) [Finite G] [Group G]
    (h_card : Nat.card G = p * (p + 1)) (h_sylow : ∀ (H : Sylow p G), ¬ H.Normal) :
    ∃ (n : ℕ), p + 1 = 2 ^ n := by
  sorry

end MiniFATELeanCat.Hard.FATEX004
