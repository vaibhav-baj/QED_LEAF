import Lean

open Lean Elab Command in
def qedLeafExtract (modules : List String) : CommandElabM Unit := do
  let env ← getEnv
  let mut rows : Array Json := #[]
  for (name, ci) in env.constants.toList do
    let some idx := env.getModuleIdxFor? name | continue
    let modName := env.header.moduleNames[idx.toNat]!.toString
    if !modules.contains modName then continue
    let axioms ← collectAxioms name
    let kind := match ci with
      | .thmInfo _ => "theorem"
      | .axiomInfo _ => "axiom"
      | .defnInfo _ => "definition"
      | .opaqueInfo _ => "opaque"
      | .inductInfo _ => "inductive"
      | .ctorInfo _ => "constructor"
      | .recInfo _ => "recursor"
      | .quotInfo _ => "quotient"
    let body := ""
    rows := rows.push <| Json.mkObj [
      ("name", toJson name.toString), ("module", toJson modName),
      ("kind", toJson kind), ("type", toJson (reprStr ci.type)),
      ("levels", toJson (ci.levelParams.map Name.toString)),
      ("body", toJson body), ("axioms", toJson (axioms.map Name.toString))]
  logInfo ("QED_LEAF_FACTS=" ++ (Json.arr rows).compress)
