/**
 * PS509 demo action: a spotless v67, with sharing, user-mode insert of
 * Casc_Parent__c. Its own DML is clean - but Casc_Parent__c has a legacy (v58)
 * trigger, so the cascade runs system mode and can write beyond the user. The
 * analyzer flags PS509 even though the action itself looks safe.
 */
public with sharing class BlastRadius_DmlDemo {
    @InvocableMethod(label='Create Casc Parent'
                     description='Creates parent records (user mode)')
    public static void run(List<String> names) {
        List<Casc_Parent__c> items = new List<Casc_Parent__c>();
        for (String n : names) {
            items.add(new Casc_Parent__c(Name = n));
        }
        insert as user items;
    }
}
