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

WHAT NO ORACLE CAN SETTLE - a limit of the method, not a to-do list
    Some cases assert what the ANALYZER must REPORT, not what the platform does, so
    there is nothing for an org to judge. Running the code would simply execute the
    query; it cannot pronounce on whether we were right to call our own knowledge
    incomplete. These stay `reasoned`/`platform-doc` permanently and honestly:
      unknown-dynamic-soql, unknown-sosl-without-returning   - PS504 says "we do not
          know". An org cannot measure the absence of our knowledge.
      async-queueable, async-callout, async-none-is-clean    - PS514 says "we flag a
          hand-off we do not follow". Same shape of claim.
      field-untagged-escalates-ps502                         - its platform half (a
          v58 read escapes) is already measured by prec-v58-without-plain; the half
          that distinguishes it (PS502 vs PS506) is our own labelling design, which
          the org has no opinion about.
    Counting these as gaps would overstate what is missing, exactly as counting them
    as measured would overstate what is proven.

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

# The whole SOSL reader rests on ONE claim - that SOSL obeys the SAME mode
# precedence as SOQL. It was asserted from the docs when the SOSL blind spot was
# closed; if it is false, that fix is false. So the oracle settles it. SOSL returns
# nothing inside an Apex test unless the results are fixed first, hence the
# `fixed_search` flag on those cases.
_SOSL_BODY = """            List<List<SObject>> res = [FIND 'SECRET' IN ALL FIELDS
                RETURNING Blast_Test__c(Customer_IBAN__c)];
            List<Blast_Test__c> b = (List<Blast_Test__c>) res[0];
            if (b.isEmpty()) return 'NO_ROWS';
            return 'READ=' + b[0].Customer_IBAN__c;"""


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
         expect=set(), truth="experiment:oracle",
         # THE ORACLE'S NEGATIVE CONTROL, and the reason it is worth the fixture work.
         # Every other read case ends in BLOCKED, which invites the obvious objection:
         # this user is so crippled that BLOCKED is vacuous and the oracle proves
         # nothing. So grant FLS on exactly one field and read it under USER_MODE - the
         # same enforcement that blocks Customer_IBAN__c must let Secret_Data__c
         # through. If this case ever goes BLOCKED, the oracle's other greens are
         # worthless and we need to know that before a reviewer finds it.
         # USER_MODE is forced although the case is v58: under v58's system mode FLS
         # is bypassed for every field, so a green would prove nothing about FLS.
         runtime=dict(sharing="with", clause=None, expect_read=True,
                      perms=dict(read_fields=["Secret_Data__c"]),
                      body="            List<Blast_Test__c> r = [SELECT Secret_Data__c "
                           "FROM Blast_Test__c WITH USER_MODE LIMIT 1];\n"
                           "            if (r.isEmpty()) return 'NO_ROWS';\n"
                           "            return 'READ=' + r[0].Secret_Data__c;"),
         why="user_minimal HAS FLS read on Secret_Data__c, and `with sharing` covers "
             "the record axis, so there is nothing beyond the user. A tool that "
             "flags this is crying wolf."),

    dict(id="field-id-only-is-clean", api=58.0,
         apex=_cls("List<Blast_Test__c> r = [SELECT Id FROM Blast_Test__c];", "with"),
         expect=set(), truth="experiment:oracle",
         why="Id has no FieldPermissions row and is always readable; flagging it "
             "would be a guaranteed false positive on almost every query.",
         # The shape forces USER_MODE although the case itself is v58. Deliberate:
         # under v58's system mode FLS is bypassed for EVERY field, so Id coming
         # back would prove nothing about Id. The premise worth measuring is that Id
         # survives FLS *enforcement* - that is what makes not flagging it correct.
         runtime=dict(sharing="with", clause=None, expect_read=True,
                      body="            List<Blast_Test__c> r = [SELECT Id FROM Blast_Test__c "
                           "WITH USER_MODE LIMIT 1];\n"
                           "            if (r.isEmpty()) return 'NO_ROWS';\n"
                           "            return 'READ=' + r[0].Id;")),

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
         expect={"PS501", "PS506"}, truth="experiment:oracle",
         runtime=dict(sharing="without", clause=None, expect_read=True,
                      fixed_search=True, body=_SOSL_BODY),
         why="SOSL obeys the same mode precedence as SOQL, so a legacy SOSL that "
             "RETURNs an invisible GDPR field is the same escalation. Measured: the "
             "org hands the field over."),

    dict(id="sosl-returning-gdpr-v67", api=67.0,
         apex=_cls("List<List<SObject>> r = [FIND :q IN ALL FIELDS RETURNING "
                   "Blast_Test__c(Customer_IBAN__c)];", "without"),
         expect=set(), truth="experiment:oracle",
         runtime=dict(sharing="without", clause=None, expect_read=False,
                      fixed_search=True, body=_SOSL_BODY),
         why="...and is equally safe at v67. Negative twin of the case above - and "
             "the pair is what proves the SOSL reader inherits the precedence law "
             "rather than merely being assumed to."),

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
         expect={"PS501", "PS506", "PS512"}, truth="experiment:oracle",
         # THE CASE THAT CAUGHT US. The label used to read "UPDATABLE strips nothing
         # on a read path, so the escalation stays proven" - believed from the docs,
         # never measured - and on that basis PS506 fired ERROR. The oracle refuted it
         # on both branches: with no object Edit the call THROWS; with object Edit the
         # field is STRIPPED. Neither leaks. Our ERROR was a false positive, and the
         # rule now gates on result_used alone. Kept at WARN rather than removed
         # because we still cannot prove WHICH list reaches the sink without alias
         # tracking - sanitizer present, path unproven, exactly what WARN means.
         why="Measured in-org: stripInaccessible(UPDATABLE) on a read path does NOT "
             "leak the field - it throws without object Edit, and strips the field "
             "with it (FLS cannot grant Edit without Read, so unreadable implies "
             "un-updatable). It errs safe. WARN because the sanitized list is present "
             "but we cannot prove it, not the original, is what reaches the model.",
         runtime=dict(sharing="without", clause=None, expect_read=False,
                      body="            List<Blast_Test__c> r = [SELECT Customer_IBAN__c "
                           "FROM Blast_Test__c LIMIT 1];\n"
                           "            if (r.isEmpty()) return 'NO_ROWS';\n"
                           "            List<Blast_Test__c> s = Security.stripInaccessible(\n"
                           "                AccessType.UPDATABLE, r).getRecords();\n"
                           "            return 'READ=' + s[0].Customer_IBAN__c;"),
         expect_severity={"PS512": "WARN", "PS506": "WARN"}),

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
    # The three write cases carry the same precedence law as the reads, on the OTHER
    # axis (object CRUD, not FLS). Their runtime shape therefore runs as a user with
    # no Create at all - see oracle.py for why that user cannot be the reader.
    dict(id="write-v58-plain-insert", api=58.0,
         apex=_cls("insert new Blast_Test__c(Name='x');", "with"),
         expect={"PS503"}, truth="experiment:oracle",
         why="Legacy DML defaults to system mode; user_minimal has no create. "
             "Measured: the insert LANDS for a user holding no Create at all.",
         runtime=dict(kind="write", sharing="with", clause=None, expect_write=True)),

    dict(id="write-as-user-is-clean", api=58.0,
         apex=_cls("insert as user new Blast_Test__c(Name='x');", "with"),
         expect=set(), truth="experiment:oracle",
         why="`as user` enforces CRUD even at v58 - the clause beats the version. "
             "Measured: the same insert that lands without the clause is blocked.",
         runtime=dict(kind="write", sharing="with", clause="as user", expect_write=False)),

    dict(id="write-v67-plain-is-clean", api=67.0,
         apex=_cls("insert new Blast_Test__c(Name='x');", "with"),
         expect=set(), truth="experiment:oracle",
         # Was labelled experiment:E2, which was borrowed evidence: E2 measured a
         # v58/v67 READ (5 rows vs 0) and never wrote anything, so it could not
         # speak for DML's default. The oracle now measures the write itself.
         why="v67 DML defaults to user mode. Measured directly: the insert is "
             "blocked at v67 and lands at v58. E2 never wrote, so it never "
             "evidenced this - the oracle does.",
         runtime=dict(kind="write", sharing="with", clause=None, expect_write=False)),
]


def case_ids():
    return [c["id"] for c in CASES]
