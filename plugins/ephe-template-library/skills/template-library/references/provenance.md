# Provenance contract

Every entry in `templates/PROVENANCE.json` names an id, the shipped file,
its licence file, the upstream URL, the licence identifier and the sha256
of the shipped bytes. A template that fails any check is refused with a
reason code; the agent never falls back to a network fetch.
