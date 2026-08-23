# Agent Authority Benchmark

**Version 1.1 (2026-08-19).** *v1.0 carried a defect in its scoring field — see
[Errata](#errata) before comparing against a copy you already hold.*

**28 Apex cases about Salesforce execution semantics. 21 of them adjudicated by a real
org — not by an opinion, and not by mine.**

If you build or review static analysis for Salesforce, this is a scoring surface you
can use without trusting anything I say.

---

## The question this benchmark answers

Given a piece of Apex, at a stated API version, executed as a user with known
permissions:

> **Does the field actually come back, or does the platform bound the read?**

That question has exactly one right answer per case, it was measured in a live org,
and any analyzer can be scored against it.

## Why it exists

I was writing an analyzer that resolves Apex execution semantics — API version,
sharing declaration, mode clauses — and I hit the problem every such project hits:

**If I generate the expected outcomes from my own model of the rules, I am testing my
implementation against a re-implementation of itself.** That is a mirror, not an
oracle. It proves consistency and says nothing about correctness.

So every case here carries a `label_provenance` field naming *where the ground truth
came from*. Read it sceptically — it is the benchmark's real quality metric, more
than any pass rate:

| provenance | meaning | count |
|---|---|---|
| `experiment:E<n>` | measured in a real org during the original experiments | strongest |
| `experiment:oracle` | measured by the runtime oracle — deployed, executed as the modelled user, the org decided | strongest |
| `platform-doc` | documented semantics, **not measured here** | weak |
| `reasoned` | my own reasoning — proves consistency, **not correctness** | weakest |

Current distribution across the 28 cases: **21 experiment · 3 platform-doc · 4
reasoned**.

## The finding most people do not expect

```
public without sharing class B { void m(){
    List<Sharing_Test__c> r = [SELECT Customer_IBAN__c FROM Sharing_Test__c];
} }
```

Byte-identical source. Same org, same user, same rows.

| API version | records returned |
|---|---|
| **v58** | **5** |
| **v67** | **0** |

From API v67, Salesforce enforces the running user's field-level security and object
permissions **by default**. Below it, the same source runs in system mode. And at v67
the read of an FLS-hidden field does not come back quietly empty — it **throws**
(`No such column`). The platform blocks rather than silently stripping.

That is a platform security win, and it is the reason a large part of this benchmark
exists: an analyzer that flags the v67 case is producing a **false positive** on code
the platform has already made safe.

**Do not take my word for it.** The full recipe — object, fields, permission set,
both classes, and the negative control — is here, and reproduces in about 15 minutes
in a fresh scratch org:

**→ [Reproducing the v58 / v67 measurement](https://gist.github.com/aksumustafa1625/114747da631f9a368aeef187e2e704b4)**

It uses the same fixture as this corpus, so a reader who follows the recipe and a
reader who runs the cases build the same thing.

## The fixture

Every case runs against the same shape:

- **`Sharing_Test__c`** — a custom object with `Private` org-wide default
- **`Customer_IBAN__c`** — the field under test; the modelled user has **no field
  permission on it**
- **The running user** — object `READ` on `Sharing_Test__c`, and deliberately nothing
  else: no create, no edit, no delete, no FLS on the tested field
- **`Secret_Data__c`** — the **negative control**: a field the user *is* entitled to,
  seeded with a real value

The negative control matters more than it looks. Without it, a "successful read"
could be a null that would have passed either way. An escape means **the data came
back AND the user was not entitled to it** — both facts, never one.

## Using it

```
public-benchmark/
  corpus.json          28 cases: conditions, provenance, rationale, org verdict
  cases/<id>.cls       the Apex source of each case
```

1. Run your analyzer over `cases/<id>.cls` at the case's `api_version`, modelling the
   running user described in `fixture`.
2. Compare your verdict against `org_verdict.bounded_by_running_user`.

That field is what a real Salesforce org did. If your analyzer disagrees with it, the
org is right.

Each verdict also says which **axis** the case adjudicates, and publishes the raw
observation it was derived from, so the derivation itself can be checked:

| `org_verdict.axis` | raw observation | `bounded_by_running_user` is true when |
|---|---|---|
| `field-level security` | `field_returned`, `user_is_entitled` | NOT (the field came back AND the user was not entitled to it) |
| `record sharing` | `rows_without_share_returned` | rows the user holds no share on did **not** come back |
| `object CRUD` | `operation`, `write_landed_without_permission` | the insert / publish did **not** land |

```json
{
  "id": "prec-v67-without-plain",
  "api_version": 67.0,
  "label_provenance": "experiment:E2,E2b",
  "org_verdict": {
    "axis": "field-level security",
    "sharing_declaration": "without",
    "mode_clause": null,
    "field_returned": false,
    "user_is_entitled": false,
    "field_returned_to_unentitled_user": false,
    "bounded_by_running_user": true
  }
}
```

## Seven cases carry no org verdict — on purpose

`not_adjudicable_cases` holds the ones no org can settle, and they are separated
rather than quietly dropped.

Those cases assert what an **analyzer must report** — an honest unknown (dynamic
SOQL, a SOSL with no `RETURNING`), or a hand-off it does not follow — not what the
platform does. Running the code would simply execute the query; it cannot pronounce
on whether the analyzer was right to call its own knowledge incomplete. **An org
cannot measure the absence of an analyzer's knowledge.**

Counting them as gaps would overstate what is missing. Counting them as measured
would overstate what is proven. So they are published, labelled, and excluded from
the adjudicated set.

## What this benchmark is not

- **Not a claim that any particular tool is wrong.** It is a set of measured cases.
  Run whatever you like against them and draw your own conclusions.
- **Not exhaustive.** 28 cases around one object and one user. It covers execution
  semantics, not the whole surface of Salesforce security.
- **Not a product.** Nothing here is for sale and there is nothing to sign up for.

## Contributing

The most valuable contribution is a **case that breaks something** — a shape whose
real-org behaviour differs from what any reasonable analyzer would predict. If you
measure one, open an issue with the Apex, the API version, the user's permissions,
and what the org actually did.

The second most valuable: an **org verdict for one of the seven** — if you find a way
to make a platform adjudicate a case I marked unadjudicable, I would rather be wrong
about that than keep the label.

## Integrity

The corpus is committed by hash, so a later version cannot be quietly substituted and
no case can be tuned after the fact without the hash moving.

**Every hash lives in [`CHECKSUMS.md`](CHECKSUMS.md) — the corpus and each case — and
that file is generated by the exporter, never typed.** This README deliberately does
not repeat the hash. It used to, and that copy went stale the first time the corpus
was regenerated: a hand-maintained integrity seal is the silent edit it claims to
prevent, just with an extra step. If the seal and the corpus can disagree, the seal
is decoration.

From this directory, every file at once (the hash lines are written in the exact
format `sha256sum -c` reads, with paths relative to here):

```
grep -E '^    [0-9a-f]{64}  ' CHECKSUMS.md | sed 's/^ *//' | sha256sum -c
```

A `.gitattributes` ships with the corpus and pins every text file to LF, so the same
bytes — and the same hashes — come out of a Windows checkout.

A benchmark whose author can edit it silently is not a benchmark.

## Errata

A benchmark that changes silently is not a benchmark either. Every change to a
published value is listed here, and in `corpus.json` under `errata`, in the same
words. If you hold an earlier copy, its `CHECKSUMS.md` will not match this one — that
is the point.

### v1.1 — 2026-08-19 — `org_verdict.bounded_by_running_user` was wrong for 5 of 21 cases

v1.0 derived that field as *"the field did not come back"* for **every** case. That is
correct only for the field-level-security read cases. The record-axis cases observe
**rows**, not a field; the write and publish cases observe whether the **DML landed**,
not a field — none of them carries a "field came back" observation, so all of them
were published as `bounded: true`, including the v58 cases whose own rationale says the
operation lands past the user. And the two read cases that return a field the user
**is** entitled to — the negative control — were published as `bounded: false` and
`field_returned_to_unentitled_user: true`: the control mislabelled as an escape.

Affected ids (old value → new value of `bounded_by_running_user`):

| id | v1.0 | v1.1 | why |
|---|---|---|---|
| `record-v58-without-plain` | true | **false** | rows the user holds no share on came back |
| `write-v58-plain-insert` | true | **false** | the insert landed for a user with no Create |
| `publish-v58-bypasses-create` | true | **false** | the publish landed for a user with no Create |
| `field-user-can-see-is-clean` | false | **true** | the field came back **and** the user was entitled to it |
| `field-id-only-is-clean` | false | **true** | same — `Id` needs no field permission |

Also in v1.1, none of which changes a measured outcome:

- `bounded_by_running_user` is now derived **per axis**, and every `org_verdict` carries
  `axis` plus the raw observation it was derived from (table above).
- Two ids renamed: `prec-v58-without-systemmode-clause` → `prec-v67-without-systemmode-clause`
  (it was always an `api_version: 67.0` case; the old id read as a claim about v58), and
  `field-untagged-escalates-ps502` → `field-untagged-escalates` (the suffix was one tool's
  rule number, in a corpus published with no tool named).
- `label_provenance` for oracle-settled cases is spelled `experiment:oracle` everywhere; an
  earlier draft of this README said `experiment:runtime` for the same thing.
- Rationale text no longer carries the exporting project's internal vocabulary.
- No case source, API version, fixture, or measured outcome changed. The case-file hashes
  of unrenamed cases are identical to v1.0.

## Measured on

Salesforce **Summer '26**. Platform behaviour changes; if a case stops reproducing on
a later release, that is a finding and I want to hear about it.

## Licence

Cases and corpus data: **CC BY 4.0** — use, adapt and redistribute with attribution.
The full legal text is in [`LICENSE`](LICENSE); SPDX identifier `CC-BY-4.0`.

Run your own analyzer against this corpus and publish the score — that is what it
is for, and no permission is needed. Attribution, if you want a form to copy:

    Agent Authority Benchmark, Mustafa Aksu, CC BY 4.0
    https://github.com/aksumustafa1625/agent-authority-benchmark

Two things worth knowing before you fork it. The licence requires that a modified
version **say** it was modified (CC BY 4.0 §3(a)(1)(B)); that matters more here
than in most repositories, because the value of this corpus is its labels, and a
silently retuned label set carrying the same name would be worth nothing to
anyone. And the licence covers the text and data, not the name — so a fork is
your benchmark, published under your own name, with attribution back to this one.

If you think a label is wrong, that is the most useful thing you can send: 21 of
the 28 carry an org verdict, and a case that stops reproducing on a later
Salesforce release is a finding, not a nuisance.

---

*Built while writing a static analyzer for Agentforce agent authority. The analyzer
is a separate matter; this benchmark stands on its own, and is published because a
measurement nobody else can check is not much of a measurement.*
