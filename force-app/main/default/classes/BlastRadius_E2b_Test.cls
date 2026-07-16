/**
 * E2b - the decisive two-axis experiment (Milestone 0 follow-up, 2026-07-14).
 *
 * Settles a disputed claim raised in adversarial review: at API v67, does an
 * EXPLICIT `without sharing` class running a plain SOQL enforce RECORD-level
 * sharing, or only FLS? Measured independently, the org's answer is: BOTH are
 * enforced. The v67 user-mode default runs the operation in user mode, and that
 * takes precedence over the class's `without sharing` declaration (which only
 * governs record access when the operation is in system mode). So the analyzer's
 * (enforces_sharing=True, enforces_fls=True) for v67 plain SOQL is correct.
 *
 * Verified matrix (this test locks it in as a regression guard):
 *   RECORD axis: v58 without = 5 (bypass), v67 without = 0 (enforced)
 *   FLS axis:    v58 without = READ (bypass), v67 without = BLOCKED (enforced)
 *
 * Note: an explicit WITH SYSTEM_MODE / AccessLevel.SYSTEM_MODE re-opens the
 * bypass at v67 - that path is handled by the precedence chain (clause > default).
 */
@isTest
private class BlastRadius_E2b_Test {

    private static User minimalUser(String tag) {
        Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
        String suffix = String.valueOf(System.now().getTime()) + tag;
        return new User(
            FirstName = 'Blast', LastName = 'E2b' + tag,
            Email = 'blast.e2b@example.com',
            Username = 'blast.e2b.' + suffix + '@blastradius.example.com',
            Alias = 'be2b', ProfileId = p.Id,
            TimeZoneSidKey = 'Europe/Berlin', LocaleSidKey = 'en_US',
            EmailEncodingKey = 'UTF-8', LanguageLocaleKey = 'en_US'
        );
    }

    @isTest
    static void record_axis_v67_without_sharing_enforces_records() {
        User u;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            u = minimalUser('R');
            insert u;
            PermissionSet ps = new PermissionSet(Name = 'E2b_ObjReadR', Label = 'E2b Obj Read R');
            insert ps;
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Blast_Test__c',
                PermissionsRead = true);
            insert new PermissionSetAssignment(AssigneeId = u.Id, PermissionSetId = ps.Id);
        }

        List<Blast_Test__c> recs = new List<Blast_Test__c>();
        for (Integer i = 0; i < 5; i++) {
            recs.add(new Blast_Test__c(Name = 'r' + i, Customer_IBAN__c = 'IBAN' + i));
        }
        insert recs; // owned by the running (admin) user, not u

        Integer v58, v67;
        System.runAs(u) {
            v58 = new BlastRadius_E2_ReaderV58().countRecords();
            v67 = new BlastRadius_E2_ReaderV67().countRecords();
        }

        System.assertEquals(5, v58, 'v58 without sharing should BYPASS record sharing (see all 5)');
        System.assertEquals(0, v67, 'v67 without sharing should ENFORCE record sharing (user-mode default)');
    }

    @isTest
    static void fls_axis_v67_without_sharing_enforces_fls() {
        User u;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            u = minimalUser('F');
            insert u;
            PermissionSet ps = new PermissionSet(Name = 'E2b_ObjReadF', Label = 'E2b Obj Read F');
            insert ps;
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Blast_Test__c',
                PermissionsRead = true, PermissionsCreate = true);
            insert new PermissionSetAssignment(AssigneeId = u.Id, PermissionSetId = ps.Id);
        }

        String v58, v67;
        System.runAs(u) {
            insert new Blast_Test__c(Name = 'mine', Customer_IBAN__c = 'SECRET-IBAN');
            v58 = new BlastRadius_FieldReaderV58().readIban();
            v67 = new BlastRadius_FieldReaderV67().readIban();
        }

        System.assert(v58.startsWith('READ='),
            'v58 without sharing should BYPASS FLS and read the field. Got: ' + v58);
        System.assert(v67.startsWith('BLOCKED='),
            'v67 without sharing should ENFORCE FLS and block the field. Got: ' + v67);
    }
}
