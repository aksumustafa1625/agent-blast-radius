"""Agent Authority Benchmark v1 - the labelled corpus.

WHY THIS EXISTS
    "119 tests green" is not an accuracy claim. A test suite proves the code does
    what its author expected; a benchmark measures how often that expectation is
    RIGHT, per rule, against labels fixed independently of the implementation.
    An external review named this the single highest-leverage next step, and it is
    the only thing that turns "deterministic" into "deterministic AND correct".

THE TRAP THIS FILE AVOIDS
    Generating expected outcomes from the precedence law would test the analyzer
    against a re-implementation of itself - a mirror, not an oracle. So every label
    below is hand-written with an explicit `truth` field naming WHERE the ground
    truth comes from. Read that field sceptically: it is the benchmark's real
    quality metric.

    truth = "experiment:EN"  the outcome was MEASURED in a real org (Milestone 0).
                             These are the strong labels.
    truth = "experiment:oracle"
                             MEASURED by the runtime oracle (oracle.py), which
                             deploys the case, runs it as the modelled user, and
                             lets the ORG decide. Re-runnable on demand - the
                             strongest label available, because nothing about it
                             depends on the author being right.
    truth = "sfge"           an independent engine agrees (differential oracle).
    truth = "platform-doc"   documented Salesforce semantics, not measured here.
    truth = "reasoned"       derived by the author from the above. WEAKEST label:
                             it shares a mind with the implementation, so it proves
                             consistency, not correctness. Counted and reported
                             separately for exactly that reason.

A case carrying `runtime={...}` can be settled by oracle.py. Adding a runtime shape
to a `reasoned` case is worth more than adding ten new reasoned cases.

Each case declares the EXACT set of graded rules it must produce. Anything else
that fires is a false positive; anything declared that doesn't fire is a false
negative. Ungraded rules (see GRADED) are ignored so INFO inventory noise like
PS511 cannot flatter or pollute the score.
"""
from __future__ import annotations

# Rules the benchmark grades. PS511 (legacy-API inventory) and PS507/PS508
# (opaque/chain markers) are deliberately excluded: they are inventory and
# honest-unknown markers, not accuracy claims about an escalation.
GRADED = {"PS501", "PS502", "PS503", "PS504", "PS505", "PS506",
          "PS509", "PS512", "PS514"}

# Shared fixture vocabulary -------------------------------------------------
# Blast_Test__c is Private OWD. Customer_IBAN__c is tagged GDPR;PII. The
# `user_minimal` snapshot has object READ on Blast_Test__c but NO FLS on
# Customer_IBAN__c, and no create/edit/delete anywhere. Both were used by the
# Milestone 0 experiments, so the org-measured labels below apply to them.
GDPR = {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR;PII"}}
SHARING = {"Blast_Test__c": "Private"}

_READ = "List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c];"


def _cls(body: str, sharing: str = "without") -> str:
    decl = "" if sharing == "none" else f"{sharing} sharing "
    return "public %sclass B { void m(){ %s } }" % (decl, body)


CASES = [
    # ---------------------------------------------------------------- precedence
    # The core law. E1/E2/E2b/E3 measured these exact shapes in a real org, so
    # these are the benchmark's strongest labels.
    #
    # `runtime` marks a case the ORACLE can settle in a live org (see oracle.py):
    # it deploys the same shape as real Apex, runs it as the modelled user, and
    # checks whether the field actually comes back. `expect_read` is what the
    # ANALYZER's verdict predicts the org will do - True when it claims the field
    # escapes past the user (FLS bypassed), False when it claims the field is out
    # of reach (FLS enforced). The org, not the author, decides who was right.
    dict(id="prec-v58-without-plain", api=58.0, apex=_cls(_READ, "without"),
         expect={"PS501", "PS506"}, truth="experiment:E1,E2",
         runtime=dict(sharing="without", clause=None, expect_read=True),
         why="legacy + without sharing + plain SOQL: system mode on BOTH axes. "
             "E1 measured 5 records read vs 0 for the user; E2 measured v58=5."),

    dict(id="prec-v67-without-plain", api=67.0, apex=_cls(_READ, "without"),
         expect=set(), truth="experiment:E2,E2b",
         runtime=dict(sharing="without", clause=None, expect_read=False),
         why="THE false-positive killer. Same `without sharing` source at v67 is "
             "SAFE: E2 measured v67=0 records, E2b measured the field read BLOCKED "
             "('No such column'). Version-blind flagging here is wrong - and sfge "
             "does exactly that (see Appendix AD)."),

    dict(id="prec-v58-without-usermode-clause", api=58.0,
         apex=_cls("List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c "
                   "WITH USER_MODE];", "without"),
         expect=set(), truth="experiment:E3",
         runtime=dict(sharing="without", clause="WITH USER_MODE", expect_read=False),
         why="Operation clause beats the class declaration. E3 measured the same "
             "`without sharing` class returning 0 with WITH USER_MODE."),

    dict(id="prec-v67-no-declaration", api=67.0, apex=_cls(_READ, "none"),
         expect=set(), truth="experiment:E2",
         runtime=dict(sharing="none", clause=None, expect_read=False),
         why="v67 default is user mode even with no sharing declaration."),

    dict(id="prec-v58-with-sharing-plain", api=58.0, apex=_cls(_READ, "with"),
         expect={"PS506"}, truth="experiment:E1,E2b",
         runtime=dict(sharing="with", clause=None, expect_read=True),
         why="TWO AXES, the distinction most reviews get wrong: `with sharing` "
             "enforces the RECORD axis (so no PS501) but at v58 CRUD/FLS is still "
             "bypassed, so the GDPR field still escapes (PS506)."),

    dict(id="prec-v58-without-systemmode-clause", api=67.0,
         apex=_cls("List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c "
                   "WITH SYSTEM_MODE];", "without"),
         expect={"PS501", "PS506"}, truth="experiment:oracle",
         runtime=dict(sharing="without", clause="WITH SYSTEM_MODE", expect_read=True),
         why="An explicit WITH SYSTEM_MODE re-opens both axes even at v67. This "
             "label started as `platform-doc` - believed from the docs, never "
             "measured. The runtime oracle settled it in a live org: the field DOES "
             "come back past the user. Earned, not assumed."),

    # ------------------------------------------------------------ field vs GDPR
    dict(id="field-untagged-escalates-ps502", api=58.0,
         apex=_cls("List<Blast_Test__c> r = [SELECT Internal_Note__c FROM Blast_Test__c];",
                   "without"),
         expect={"PS501", "PS502"}, truth="reasoned",
         why="An UNTAGGED field the user cannot see is PS502, not PS506 - the GDPR "
             "label is what separates the two rules. Internal_Note__c has no "
             "FieldPermissions row in user_minimal, so it is beyond the user."),

    dict(id="field-user-can-see-is-clean", api=58.0,
         apex=_cls("List<Blast_Test__c> r = [SELECT Secret_Data__c FROM Blast_Test__c];",
                   "with"),
         expect=set(), truth="reasoned",
         why="user_minimal HAS FLS read on Secret_Data__c, and `with sharing` covers "
             "the record axis, so there is nothing beyond the user. A tool that "
             "flags this is crying wolf."),

    dict(id="field-id-only-is-clean", api=58.0,
         apex=_cls("List<Blast_Test__c> r = [SELECT Id FROM Blast_Test__c];", "with"),
         expect=set(), truth="platform-doc",
         why="Id has no FieldPermissions row and is always readable; flagging it "
             "would be a guaranteed false positive on almost every query."),

    # ------------------------------------------------------------- honest unknown
    dict(id="unknown-dynamic-soql", api=58.0,
         apex=_cls("List<SObject> r = Database.query(q);", "without"),
         expect={"PS504"}, truth="reasoned",
         why="Reach is not statically determinable. A silent clean here is the "
             "worst outcome; an honest unknown is the contract."),

    dict(id="unknown-sosl-without-returning", api=58.0,
         apex=_cls("List<List<SObject>> r = [FIND :q IN ALL FIELDS];", "without"),
         expect={"PS504"}, truth="reasoned",
         why="SOSL with no RETURNING searches every searchable object; reach unknown."),

    dict(id="sosl-returning-gdpr-v58", api=58.0,
         apex=_cls("List<List<SObject>> r = [FIND :q IN ALL FIELDS RETURNING "
                   "Blast_Test__c(Customer_IBAN__c)];", "without"),
         expect={"PS501", "PS506"}, truth="platform-doc",
         why="SOSL obeys the same mode precedence as SOQL, so a legacy SOSL that "
             "RETURNs an invisible GDPR field is the same escalation."),

    dict(id="sosl-returning-gdpr-v67", api=67.0,
         apex=_cls("List<List<SObject>> r = [FIND :q IN ALL FIELDS RETURNING "
                   "Blast_Test__c(Customer_IBAN__c)];", "without"),
         expect=set(), truth="platform-doc",
         why="...and is equally safe at v67. Negative twin of the case above."),

    # -------------------------------------------------------------- sanitizer
    # PS512 rests entirely on two claims about how the PLATFORM behaves. If either
    # is wrong the rule is wrong, so both are settled by the oracle rather than
    # believed: does stripInaccessible actually remove the field, and does
    # discarding its decision actually leave the original readable?
    dict(id="sanitizer-readable-used-caps-severity", api=58.0,
         apex=_cls(_READ + " List<Blast_Test__c> safe = "
                   "Security.stripInaccessible(AccessType.READABLE, r).getRecords();",
                   "without"),
         expect={"PS501", "PS506"}, truth="experiment:oracle",
         runtime=dict(sharing="without", clause=None, expect_read=False, body="""            List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c LIMIT 1];
            if (r.isEmpty()) return 'NO_ROWS';
            List<Blast_Test__c> safe = Security.stripInaccessible(
                AccessType.READABLE, r).getRecords();
            return 'READ=' + safe[0].Customer_IBAN__c;"""),
         why="The sanitizer is real - the oracle confirms the stripped list will not "
             "hand the field over - so the finding must NOT be asserted as proven. "
             "But we cannot prove WHICH list reaches the sink, so it must not be "
             "cleared either: it fires, capped at WARN. This is the case where the "
             "org proves the analyzer is being conservative rather than wrong.",
         expect_severity={"PS506": "WARN"}),

    dict(id="sanitizer-discarded-is-a-bug", api=58.0,
         apex=_cls(_READ + " Security.stripInaccessible(AccessType.READABLE, r);",
                   "without"),
         expect={"PS501", "PS506", "PS512"}, truth="experiment:oracle",
         runtime=dict(sharing="without", clause=None, expect_read=True, body="""            List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c LIMIT 1];
            if (r.isEmpty()) return 'NO_ROWS';
            Security.stripInaccessible(AccessType.READABLE, r);
            return 'READ=' + r[0].Customer_IBAN__c;"""),
         why="stripInaccessible returns sanitized COPIES; discarding the decision "
             "sanitizes nothing, so the original list still hands the field over. "
             "PS512 depends on that being true - measured, not assumed.",
         expect_severity={"PS512": "ERROR", "PS506": "ERROR"}),

    dict(id="sanitizer-wrong-accesstype", api=58.0,
         apex=_cls(_READ + " List<Blast_Test__c> s = "
                   "Security.stripInaccessible(AccessType.UPDATABLE, r).getRecords();",
                   "without"),
         expect={"PS501", "PS506", "PS512"}, truth="platform-doc",
         why="UPDATABLE strips nothing on a read path, so the escalation stays proven.",
         expect_severity={"PS512": "WARN", "PS506": "ERROR"}),

    # ------------------------------------------------------------ async / events
    dict(id="async-platform-event", api=67.0,
         apex=_cls("EventBus.publish(evts);", "with"),
         expect={"PS514"}, truth="platform-doc",
         why="The subscriber runs in its own transaction and mode. Dropping it "
             "silently is the worst false negative a security tool can have."),

    dict(id="async-queueable", api=67.0, apex=_cls("System.enqueueJob(new J());", "with"),
         expect={"PS514"}, truth="platform-doc", why="Separate async transaction."),

    dict(id="async-callout", api=67.0, apex=_cls("HttpRequest q = new HttpRequest();", "with"),
         expect={"PS514"}, truth="platform-doc",
         why="Org data can leave, or external data can enter the model."),

    dict(id="async-none-is-clean", api=67.0, apex=_cls("Integer i = 1;", "with"),
         expect=set(), truth="reasoned",
         why="Negative guard: a plain action must not attract an async warning."),

    # ------------------------------------------------------------------- writes
    dict(id="write-v58-plain-insert", api=58.0,
         apex=_cls("insert new Blast_Test__c(Name='x');", "with"),
         expect={"PS503"}, truth="reasoned",
         why="Legacy DML defaults to system mode; user_minimal has no create."),

    dict(id="write-as-user-is-clean", api=58.0,
         apex=_cls("insert as user new Blast_Test__c(Name='x');", "with"),
         expect=set(), truth="platform-doc",
         why="`as user` enforces CRUD even at v58 - the clause beats the version."),

    dict(id="write-v67-plain-is-clean", api=67.0,
         apex=_cls("insert new Blast_Test__c(Name='x');", "with"),
         expect=set(), truth="experiment:E2",
         why="v67 DML defaults to user mode."),
]


def case_ids():
    return [c["id"] for c in CASES]
