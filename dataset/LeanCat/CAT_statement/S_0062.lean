/-
Difficulty: High
Informal statement:
Definition: Let $\mathcal C$ be a category. Let $S$ be a family of subobjects $(s_n,i_n)$ of an object $c\in \mathcal C$, indexed by a class $I$.
A subobject $(x,i:x\to c)$ of $c$ is called an $\textbf{intersection}$ of $S$ provided that the following two conditions are satisfied:

(1) $i$ factors through each $i_n$ i.e., for each $n$ there exists an $f_n:x\to s_n$ with $i = i_n \circ  f_n$,

(2) if a morphism $f: z\to c$ factors through each $i_n$, then it factors through $i$.

Definition: A category $\mathcal C$ is said to $\textbf{have intersections}$ if for each object $c\in\mathcal C$ and every family of subobjects of $c$, there exists an intersection.

Definition: A category is said to be $\textbf{strongly complete}$ if it is complete and has intersections.


Theorem: A strongly cocomplete category with a separating set is strongly complete.
-/

import Mathlib

open CategoryTheory Limits

namespace CAT_statement_S_0062

universe u v
variable {C : Type u} [Category.{v} C]

def IsSeparating (S : Set C) : Prop :=
  ObjectProperty.IsSeparating (fun X => X ∈ S : ObjectProperty C)

def IsIntersectionOf {B : C} (A : Subobject B) (S : Set (Subobject B)) : Prop :=
   (∀ Ai, Ai ∈ S → A ≤ Ai) ∧
  (∀ A' : Subobject B, (∀ Ai, Ai ∈ S → A' ≤ Ai) → A' ≤ A)

def HasIntersections (C : Type u) [Category.{v} C]: Prop :=
  ∀ (B : C) (S : Set (Subobject B)),
    ∃ A : Subobject B, IsIntersectionOf (C := C) (B := B) A S

class StronglyComplete (C : Type u) [Category.{v} C] : Prop where
  complete: HasLimits C
  hasinter: HasIntersections C

class StronglyCocomplete (C : Type u) [Category.{v} C] : Prop where
  dual: StronglyComplete (C:=Cᵒᵖ)

theorem strongly_complete_of_strongly_cocomplete_of_separating_set [StronglyComplete Cᵒᵖ] {𝒢 : Set C} [Small.{v} 𝒢] (h𝒢 : IsSeparating 𝒢) :
    StronglyComplete C := by
  sorry

end CAT_statement_S_0062
