# Handshake schemas

`cache-key.v0.schema.json` is the Lintel freeze-key contract (`zackc6/lintel`).
Lintel is the source of truth for `%k` field names. This copy is for Choreo tests and `choreo pin`.

Do not extend the key. `%k` is graph, hw, compiler, adapter, policy — not
`model_id`, not `enum_id`, not `Kernel.target`.

`adapter-proposal.v0.schema.json` is the propose/adapter_gate envelope this tree
emits (`choreo propose`). Kernel JSON encoding is **Choreo's** (lowercase ops;
`target` and `compiler_ver` on the Kernel). Lintel examples that use PascalCase
ops (`Copy`) are accepted on read. `reject.where` is the CFG edge (`W|L|S|V`);
V is opt-in via `--tensors`/`--expected`. `compile_ok` is Lintel's post-sink
gate, not `choreoir.check`.
