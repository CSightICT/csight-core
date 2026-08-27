# Policy Evaluation Semantics v1

| Input state | Condition status |
|---|---|
| Present, typed, condition true | `SATISFIED` |
| Present, typed, condition false | `UNSATISFIED` |
| Missing or invalid typed input | configured missing state or `UNKNOWN` |
| Source is not qualified | `NOT_EVALUATED` |
| Condition does not apply | `NOT_APPLICABLE` |

A rule is `NOT_MATCHED` when any condition is unsatisfied, `MATCHED` when all evaluated required
conditions satisfy, `NOT_APPLICABLE` when every condition is non-applicable, and otherwise
`INDETERMINATE`. Indeterminate rules emit only safety effects already declared by the rule plus
`REQUIRE_HUMAN_REVIEW`; they never emit eligibility, exception facts, or manager review based on
an unknown condition.

Summary precedence is additional evidence, human/manager review, evaluated, and no applicable
rule. These summaries are workflow guidance, never a final business result.
