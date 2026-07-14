/**
 * E6 fixture trigger. After a Casc_Parent__c is inserted, it writes a
 * Casc_Child__c. Triggers run in system mode; this experiment observes whether
 * that system context lets the write land even when the initiating user has no
 * create permission on the child, and whether API v67's user-mode default
 * changes that inside a trigger.
 */
trigger CascParentTrigger on Casc_Parent__c (after insert) {
    List<Casc_Child__c> kids = new List<Casc_Child__c>();
    for (Casc_Parent__c p : Trigger.new) {
        kids.add(new Casc_Child__c(Name = p.Name));
    }
    insert kids;
}
