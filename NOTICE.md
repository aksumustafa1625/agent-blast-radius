# NOTICE

These notes used to live at the bottom of `LICENSE`, after a `---` rule. They are
here instead because GitHub's licence detector reads the whole file: with sixteen
extra lines appended, the MIT text fell under the similarity threshold and the
repository was reported as **`NOASSERTION` / "Other"** while the README claimed MIT.
Nothing about the licence had changed — only what everyone else's tooling could see.
That is the same shape as the CRLF-digest incident in `CLAUDE.md` §7: a local file
that looks right to its author and reads wrong to every machine downstream.

## Licence

This project is MIT-licensed. `LICENSE` now contains the MIT text and nothing else.

## Third-party dependencies

The optional AST and Agent Script backends call npm packages —
`@apexdevtools/apex-parser`, `@sf-agentscript/parser`, and their transitive
dependencies. They are governed by their own licences and are **not vendored** into
this repository. The analyzer runs without them, on the regex extractor, which is
why Node is optional rather than required.

## Trademarks and affiliation

Salesforce, Agentforce, Apex, and Einstein are trademarks of Salesforce, Inc.

This project reads Salesforce metadata through the official `sf` CLI under standard
developer-org terms. It is **not affiliated with, sponsored by, or endorsed by
Salesforce**. The comparison against Salesforce Graph Engine (`sfge`) uses Salesforce
Code Analyzer under its own licence; that engine is marked *(Developer Preview)* by
Salesforce, and any published comparison should say so in the same breath.

## What this project is not

Agent Blast Radius is **not a certificate** and does not certify or guarantee
anything. It measures *reach* — what an agent's code can read or write beyond the
identity it runs as — and produces evidence for a DPIA or a security review. A human
still decides what the evidence means.
