/* Agent Blast Radius - experiment E9: muting permission sets.
 *
 * THE CLAIM UNDER TEST
 *     snapshot_loader reads a Permission Set Group through its platform-computed
 *     aggregate PermissionSet (Type='Group'), which E8 measured to equal the union
 *     of the group's components. It then ASSUMED that because the platform computes
 *     that aggregate as (components MINUS muting), reading it applies muting too.
 *     That assumption was architectural, never measured - no muting set existed in
 *     any test org. It mattered: if the aggregate did NOT reflect muting, the tool
 *     would credit the user with permissions they do not have, decide "the user can
 *     already see this field", and stay silent about a real escalation. Over-reporting
 *     permissions is how a static analyzer produces a FALSE CLEAN.
 *
 * THE FIXTURE (deployed alongside this class)
 *     BR_Mute_Component  grants object read/create on Blast_Test__c AND FLS read on
 *                        Customer_IBAN__c, so the muter has something real to remove.
 *     BR_Mute_Muter      mutes Customer_IBAN__c. It must mute editable AND readable:
 *                        the platform rejects muting Read alone. A muting set whose
 *                        permissions were silently dropped is EMPTY, and an empty
 *                        muter makes this whole test vacuously green - which is
 *                        exactly what happened on the first attempt, and why the
 *                        assertions below check the escape, not just the block.
 *     BR_Mute_Group      component + muter.
 *
 * WHAT IT MEASURED
 *     aggregate PermissionSet -> NO FieldPermissions row for Customer_IBAN__c, while
 *     the component still carries PermissionsRead=true. So the aggregate DOES apply
 *     muting, and the tool's assumption was right. Runtime agrees, below.
 */
@isTest
private class BlastRadius_E9_Muting {

    private static User mutedUser() {
        User usr;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
            usr = new User(FirstName = 'Mute', LastName = 'Probe',
                Email = 'mute.probe@example.com',
                Username = 'mute.probe.' + System.now().getTime() + '@blastradius.example.com',
                Alias = 'mprb', ProfileId = p.Id, TimeZoneSidKey = 'Europe/Berlin',
                LocaleSidKey = 'en_US', EmailEncodingKey = 'UTF-8',
                LanguageLocaleKey = 'en_US');
            insert usr;
            PermissionSetGroup g = [SELECT Id FROM PermissionSetGroup
                                    WHERE DeveloperName = 'BR_Mute_Group' LIMIT 1];
            insert new PermissionSetAssignment(AssigneeId = usr.Id,
                                               PermissionSetGroupId = g.Id);
        }
        return usr;
    }

    @isTest
    static void muting_takes_effect_and_the_field_still_escapes_in_system_mode() {
        User usr = mutedUser();
        String viaUserMode, viaSystemMode;
        System.runAs(usr) {
            insert new Blast_Test__c(Name = 'e9', Customer_IBAN__c = 'SECRET-IBAN');
            try {
                List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c
                                         WITH USER_MODE LIMIT 1];
                viaUserMode = r.isEmpty() ? 'NO_ROWS' : 'READ=' + r[0].Customer_IBAN__c;
            } catch (Exception e) {
                viaUserMode = 'BLOCKED';
            }
            // This class is pre-v67, so a plain query runs in system mode.
            List<Blast_Test__c> r2 = [SELECT Customer_IBAN__c FROM Blast_Test__c LIMIT 1];
            viaSystemMode = r2.isEmpty() ? 'NO_ROWS' : 'READ=' + r2[0].Customer_IBAN__c;
        }

        // Muting is real: the granted field is gone for the running user, and it is
        // BLOCKED rather than silently null - the same signature E2b measured for FLS.
        System.assertEquals('BLOCKED', viaUserMode,
            'MUTING DID NOT TAKE EFFECT. Either the muting set is empty (the platform '
            + 'drops permissions it will not mute) or muting no longer applies - and if '
            + 'so, every other assertion here is vacuous. The org said: ' + viaUserMode);

        // And the point of the whole tool: system mode does not care that it was muted.
        // Without this assertion a broken fixture would still pass the one above.
        System.assertEquals('READ=SECRET-IBAN', viaSystemMode,
            'A pre-v67 class should still reach the muted field - that is the escalation '
            + 'PS506 reports. The org said: ' + viaSystemMode);
    }
}
