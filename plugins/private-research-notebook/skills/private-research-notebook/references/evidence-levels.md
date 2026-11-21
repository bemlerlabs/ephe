# Evidence Levels

Every claim in a notebook answer carries one level. The level is part of the claim, not a footnote.

| Level | Meaning | How it may be used |
|---|---|---|
| `primary` | The claim appears in a source file supplied by the user and is quoted with a chunk ID. | May support a conclusion. |
| `secondary` | The claim appears in a source that itself reports another source. | May support a conclusion only when the primary source is named or the limitation is stated. |
| `user-provided` | The user stated the fact in the request but no file backs it. | May be used, labelled as user-provided; never counted as source evidence. |
| `external` | The claim comes from opt-in web research, not from the local notebook. | Must be labelled external and kept separate from the local evidence register. |
| `assumption` | The claim is needed to proceed but no evidence backs it. | Must be named as an assumption and kept out of the conclusion when it changes the decision. |

Rules:

- An assumption never becomes a finding by repetition.
- A secondary source never outranks a primary source that contradicts it.
- A claim with no chunk ID is at most `user-provided` or `assumption`.
- An empty evidence set is reported as empty; it is not filled with general knowledge.
