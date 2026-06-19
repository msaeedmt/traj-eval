/-
Source: LeanCat S_0041
Difficulty: Hard
Informal statement:
Definition: Let $(\mathcal C, U)$ be a concrete category over $\mathcal B$. A universal arrow over $x \in \mathcal B$ is a morphism $u:x\to U(c)$ with the usual universal property.

Definition: A free object over $x \in \mathcal B$ is an object $c\in \mathcal C$ equipped with such a universal arrow.

Theorem: In the non-full subcategory of complete lattices whose morphisms preserve meets and joins, there exists a free object over a set $X$ if and only if $|X| \leq 2$.

-/

import Mathlib.Order.Category.CompleteLat
import Mathlib.SetTheory.Cardinal.Basic

open CategoryTheory

universe u v w

namespace MiniFATELeanCat.Hard.LeanCat041

axiom FreeObject {C : Type u} [Category.{v} C] (x : Type w) : Type (max u v w)

theorem leancat_s0041_complete_lattice_category (X : Type u) :
    Nonempty (FreeObject (C := CompleteLat) X) ↔ Cardinal.mk X ≤ 2 := by
  sorry

end MiniFATELeanCat.Hard.LeanCat041
