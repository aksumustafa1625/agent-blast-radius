/* Agent Blast Radius - experiment E10: does a declaration-less class enforce
 * sharing, and may we say so?
 *
 * WHAT THIS MEASURES, PRECISELY
 *     Three invocables, byte-identical except for the declaration: none, `with
 *     sharing`, `without sharing`. All pre-v67, all called from the SAME caller (this
 *     test class, itself declaration-less), as the SAME minimal user, against the SAME
 *     rows - owned by the admin, on a Private object. The declaration is the only
 *     variable, so the row count is the answer.
 *
 * RESULT (measured)
 *     without sharing -> 5    no declaration -> 0    with sharing -> 0
 *     The declaration-less class inherited its caller and enforced sharing.
 *
 * WHY IT IS NOT A RERUN OF E2
 *     E2's round 1 measured the no-declaration reader ALONE and got 0 rows at v58,
 *     which is where "no declaration != without sharing" comes from. It had no
 *     controls, so 0 could equally have meant the user had nothing to see. Both
 *     controls are here, and both are load-bearing: `without sharing` must return 5
 *     or a silently failed permission assignment would read 0 everywhere and pass
 *     every assertion while measuring nothing - which is precisely what an empty
 *     muting set did to E9's first draft.
 *
 * WHAT IT DOES NOT SETTLE - say this out loud
 *     This is one cell of the entry-point matrix: a declaration-less Apex CALLER.
 *     An agent invokes an @InvocableMethod with no calling Apex class at all, and
 *     that cell cannot be measured without invoking the agent (Flex Credits, which
 *     this tool exists to avoid) or authenticating as the fixture user. Routing
 *     through a Flow would measure Flow -> invocable and drag in the Flow's own
 *     runInMode, answering a question nobody asked. So enforces_sharing stays None
 *     for a declaration-less pre-v67 class: honestly undetermined, not assumed safe
 *     and not assumed hostile.
 */
@isTest
private class BlastRadius_E10_Test {

    private static User minimalReader() {
        User usr;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
            usr = new User(FirstName = 'E10', LastName = 'Reader',
                Email = 'e10.reader@example.com',
                Username = 'e10.reader.' + System.now().getTime() + '@blastradius.example.com',
                Alias = 'e10r', ProfileId = p.Id, TimeZoneSidKey = 'Europe/Berlin',
                LocaleSidKey = 'en_US', EmailEncodingKey = 'UTF-8',
                LanguageLocaleKey = 'en_US');
            insert usr;
            PermissionSet ps = new PermissionSet(Name = 'BR_E10_Read', Label = 'BR E10 Read');
            insert ps;
            // Object read only. No create: this user must NOT own the rows, or the
            // record axis would be satisfied by ownership and measure nothing.
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Blast_Test__c',
                PermissionsRead = true);
            insert new PermissionSetAssignment(AssigneeId = usr.Id, PermissionSetId = ps.Id);
        }
        return usr;
    }

    @isTest
    static void declaration_is_the_only_variable() {
        // Seeded by the admin, so every row belongs to someone else. Blast_Test__c is
        // Private, so a sharing-enforcing read must return 0.
        List<Blast_Test__c> seed = new List<Blast_Test__c>();
        for (Integer i = 0; i < 5; i++) {
            seed.add(new Blast_Test__c(Name = 'e10-' + i, Customer_IBAN__c = 'SECRET-' + i));
        }
        insert seed;

        User usr = minimalReader();
        Integer noDecl, withSharing, withoutSharing;
        System.runAs(usr) {
            noDecl = BlastRadius_E10_NoDecl.read(new List<String>{'x'})[0].visible;
            withSharing = BlastRadius_E10_WithSharing.read(new List<String>{'x'})[0].visible;
            withoutSharing = BlastRadius_E10_WithoutSharing.read(new List<String>{'x'})[0].visible;
        }

        // POSITIVE CONTROL, and the one that makes the rest mean anything. If the
        // permission assignment silently failed the user would see nothing at all and
        // EVERY arm would read 0 - passing the assertions below while measuring
        // nothing. An empty muting set did exactly that to E9's first draft.
        System.assertEquals(5, withoutSharing,
            'FIXTURE BROKEN: an unfiltered system-mode read returned ' + withoutSharing
            + ' of 5 rows, so 0 elsewhere proves nothing about sharing.');

        // NEGATIVE CONTROL: the same rows, filtered by an explicit declaration.
        System.assertEquals(0, withSharing,
            'CONTROL FAILED: `with sharing` returned rows the user should not see, so '
            + 'this fixture cannot measure the record axis at all. Rows: ' + withSharing);

        // The measurement. Recorded either way - the assert states what the org said,
        // so a future platform change surfaces as a failure rather than a silent drift.
        System.assertEquals(0, noDecl,
            'A declaration-less class called from a declaration-less caller returned '
            + noDecl + ' rows, i.e. it did NOT inherit sharing. If this fails, the '
            + '"no declaration != without sharing" result (E2) does not hold from this '
            + 'entry point and PS501 could prove what it currently only suspects.');
    }
}
