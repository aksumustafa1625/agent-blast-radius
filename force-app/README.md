# `force-app/` — measurement evidence, not a deployable package

This directory holds Salesforce metadata **retrieved from four different orgs**.
It is the evidence behind the experiments, and it will not deploy anywhere as a
whole — nor could it, in any arrangement. TechnoStore's invoice actions need
TechnoStore's fields and its `Invoice_Payment_Requested__e` platform event;
HanseWatt's actions need HanseWatt's objects. Metadata from one org does not
install into another, and a folder collecting four of them is not a package.

That is stated here rather than in the top-level README because the command a
visitor reaches for is `sf project deploy start`, and by then they are already
inside this directory.

## What DOES deploy, and reproduces a measurement

The experiment classes and the objects they use are self-contained. That is
measured, not assumed: assembled on their own and sent to a live org as a
validation-only deploy, the 17 `BlastRadius_*` classes plus the objects, triggers
and permission sets below returned `success: true` with **zero** errors.

    force-app/main/default/classes/BlastRadius_E*.cls
    force-app/main/default/objects/{Blast_Test__c,Casc_Parent__c,Casc_Child__c,
                                    HealthRecord__c,Blast_Event__e}
    force-app/main/default/triggers/
    force-app/main/default/permissionsets/

Deploy those and the recipe in [`docs/REPRO_v58_v67.md`](../docs/REPRO_v58_v67.md)
reproduces the v58 = 5 rows / v67 = 0 rows result in about fifteen minutes.

## What was removed, and why it is not a loss

Eight `HW*Action` classes — the HanseWatt agent's actions — were deleted on
2026-08-29. They called a service layer (`HWIds`, `HWCaseService`,
`HWBillingService`, `HWConsumptionService`, `HWKnowledgeService`,
`HWTariffService`, `HWCustomerService`, `HWMoveService`) that exists in **no**
copy of this repository, so they were a partial retrieval: not the source the
analyzer measured, but half of it.

Measured against a live org, they produced **176 of the 199** validation errors
in this directory. The remaining 23 are the org-specific ones described above.

Two of them are named in `examples/HanseWatt_AksuIndex.md`. That report stands on
its own fingerprint and its own numbers; publishing an incomplete copy of the
code beside it, in a way that implies it is what was analysed, is worth less than
saying plainly that the HanseWatt action sources are not published.
