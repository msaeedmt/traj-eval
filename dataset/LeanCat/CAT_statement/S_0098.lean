/-
Difficulty: Medium
Informal statement:
Definition: For any monad $T$ on $\mathcal C$, we define a category $\mathrm{Adj}_T$ whose objects are adjunctions $(F:\mathcal C\to \mathcal D,G,\eta,\epsilon)$ which induce the same monad $T$, and a morphism between $(F:\mathcal C\to \mathcal D,G,\eta,\epsilon)$ and $(F':\mathcal C\to \mathcal D',G',\eta',\epsilon')$ in $\mathrm{Adj}_T$ is given by a functor $K:\mathcal D \to \mathcal D'$ such that $KF=F'$ and $G'K=G$.


Theorem: Let $(T,\mu,\eta)$ be a monad on a category $\mathcal{C}$.
    The Kleisli category $\mathcal{C}_T$ is initial in $\mathrm{Adj}_T$ and the Eilenberg-Moore category $\mathcal{C}^T$ is terminal,
-/

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
