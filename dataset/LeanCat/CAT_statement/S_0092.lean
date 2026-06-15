import Mathlib

open CategoryTheory Limits

variable {R : Type u} [CommRing R]


theorem ModuleCat.forgetCreatesColimits :
    Nonempty (CreatesColimits (forget₂ (ModuleCat R) AddCommGrpCat)) := by
    sorry
