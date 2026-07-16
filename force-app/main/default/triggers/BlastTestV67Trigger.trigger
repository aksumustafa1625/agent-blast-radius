/**
 * Agent Blast Radius - experiment E13.
 *
 * THE CLAIM UNDER TEST, and it is the dangerous kind: an external review cited
 * Summer '26 release notes saying "Apex Triggers are an exception as these will
 * now always run in system mode across all API versions". If that is true, PS509
 * is WRONG - it treats a v67 trigger as safe and fires nothing, which would be a
 * FALSE NEGATIVE sitting in the middle of this tool's own thesis.
 *
 * E6 measured the opposite (a trigger's DML runs in the mode of the trigger's OWN
 * apiVersion), but E6's v67 half was "verified separately in Milestone 0" - i.e.
 * asserted in a docstring with no test to catch a platform change. Exactly the
 * shape E10 was written to correct.
 *
 * This trigger is v67 and writes Casc_Child__c, which the modelled user has no
 * Create on. If the write LANDS, the trigger ran in system mode despite v67 and
 * the reviewer is right. If it is BLOCKED, E6 stands.
 */
trigger BlastTestV67Trigger on Blast_Test__c (after insert) {
    List<Casc_Child__c> kids = new List<Casc_Child__c>();
    for (Blast_Test__c b : Trigger.new) {
        kids.add(new Casc_Child__c(Name = 'e13-' + b.Name));
    }
    insert kids;
}
