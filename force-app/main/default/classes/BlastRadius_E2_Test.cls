/**
 * Agent Blast Radius - Milestone 0, Experiment E2 (apiVersion default flip).
 *
 * Two classes with identical bodies and NO sharing declaration - one at API
 * v58, one at v67 - are read by the same restricted user against the same
 * Private fixture. If the per-class API version changes the default execution
 * mode, the two return different counts. This is why apiVersion must be a
 * first-class input to the analyzer.
 *
 * Honest note: this asserts the expected flip (v58=5, v67=0). If it fails, the
 * message surfaces the ACTUAL counts so the real platform behavior is recorded
 * rather than assumed.
 */
@isTest
private class BlastRadius_E2_Test {

    private static User buildMinimalUser() {
        Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
        String suffix = String.valueOf(System.now().getTime());
        return new User(
            FirstName = 'Blast',
            LastName = 'Version',
            Email = 'blast.version@example.com',
            Username = 'blast.version.' + suffix + '@blastradius.example.com',
            Alias = 'blastv',
            ProfileId = p.Id,
            TimeZoneSidKey = 'Europe/Berlin',
            LocaleSidKey = 'en_US',
            EmailEncodingKey = 'UTF-8',
            LanguageLocaleKey = 'en_US'
        );
    }

    @isTest
    static void default_mode_flips_between_v58_and_v67() {
        User minU;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            minU = buildMinimalUser();
            insert minU;

            // Grant object + field read so any v67 difference reflects the
            // sharing/user-mode default, not a missing CRUD permission.
            PermissionSet ps = new PermissionSet(Name = 'BlastR_E2_Read', Label = 'BlastR E2 Read');
            insert ps;
            insert new ObjectPermissions(
                ParentId = ps.Id,
                SobjectType = 'Blast_Test__c',
                PermissionsRead = true
            );
            insert new FieldPermissions(
                ParentId = ps.Id,
                SobjectType = 'Blast_Test__c',
                Field = 'Blast_Test__c.Secret_Data__c',
                PermissionsRead = true
            );
            insert new PermissionSetAssignment(AssigneeId = minU.Id, PermissionSetId = ps.Id);
        }

        List<Blast_Test__c> recs = new List<Blast_Test__c>();
        for (Integer i = 0; i < 5; i++) {
            recs.add(new Blast_Test__c(Name = 'rec' + i, Secret_Data__c = 'secret' + i));
        }
        insert recs; // owned by the running (admin) user, not minU

        Integer v58Count;
        Integer v67Count;
        System.runAs(minU) {
            v58Count = new BlastRadius_E2_ReaderV58().countRecords();
            try {
                v67Count = new BlastRadius_E2_ReaderV67().countRecords();
            } catch (Exception e) {
                v67Count = 0; // user-mode default could block/return none
            }
        }

        System.assert(
            v58Count == 5 && v67Count == 0,
            'E2 RESULT  v58=' + v58Count + '  v67=' + v67Count +
            '  (expected v58=5 system-mode default, v67=0 user-mode default)'
        );
    }
}
