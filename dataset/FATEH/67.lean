import Mathlib

open scoped TensorProduct

set_option synthInstance.maxHeartbeats 200000

open Polynomial

noncomputable section

local instance : Semiring ((AdjoinRoot (X ^ 3 - 2 : Polynomial (ZMod 7))) ⊗[ZMod 7]
    (AdjoinRoot (X ^ 3 - 2 : Polynomial (ZMod 7)))) :=
  Algebra.TensorProduct.instSemiring

/--
Difficulty: Hard (FATE-H)

Prove that the prime ideals of $\mathbb{F}_7[\alpha] \otimes_{\mathbb{F}_7} \mathbb{F}_7[\alpha]$ are principal, where $\alpha^3 = 2$.
-/
theorem isPrincipal_of_ideal_tensor_zMod_seven
    (p : Ideal ((AdjoinRoot (X ^ 3 - 2 : Polynomial (ZMod 7))) ⊗[ZMod 7] (AdjoinRoot (X ^ 3 - 2 : Polynomial (ZMod 7))))) [p.IsPrime] : p.IsPrincipal := sorry
