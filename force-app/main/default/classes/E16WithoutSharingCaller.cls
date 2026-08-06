/* E16 caller, declared `without sharing`, pre-v67. The control half of the pair -
 * byte-identical to E16WithSharingCaller except the declaration.
 */
public without sharing class E16WithoutSharingCaller {
    public static void fire() {
        insert new Casc_Parent__c(Name = 'e16-without');
    }
}
