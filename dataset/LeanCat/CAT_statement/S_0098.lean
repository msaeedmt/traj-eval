import Mathlib

open CategoryTheory Monad

namespace CAT_statement_S_0098

universe u v

variable {C : Type u} [Category.{v} C]

axiom AdjCat (T : Monad C) : Type (max u v)

axiom adjCatCategory (T : Monad C) : Category (AdjCat T)

attribute [instance] adjCatCategory

variable (T : Monad C)

axiom kleisli_adj_obj : AdjCat T

theorem kleisli_initial : Nonempty (Limits.IsInitial (kleisli_adj_obj T)) := by
  sorry

axiom eilenberg_moore_adj_obj : AdjCat T

theorem eilenberg_moore_terminal : Nonempty (Limits.IsTerminal (eilenberg_moore_adj_obj T)) := by
  sorry

end CAT_statement_S_0098
