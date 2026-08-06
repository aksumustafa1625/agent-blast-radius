/* E16 caller, declared `with sharing`, pre-v67 on purpose.
 *
 * Phil W's edge-case claim, in the form most likely to matter: a trigger fired by DML
 * from a caller that itself enforces sharing. If the trigger BODY inherits its
 * caller's sharing context, this caller and E16WithoutSharingCaller will report
 * different numbers from the same trigger. If the body has its own fixed context, the
 * two will agree and the caller is irrelevant.
 */
public with sharing class E16WithSharingCaller {
    public static void fire() {
        insert new Casc_Parent__c(Name = 'e16-with');
    }
}
