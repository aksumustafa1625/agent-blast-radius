/**
 * Agent Blast Radius - Milestone 0, Experiment E3 (precedence proof).
 *
 * The anti-false-positive experiment. Claim: an operation-level mode clause
 * (WITH USER_MODE) overrides the class-level `without sharing` declaration.
 * A single `without sharing` class runs two queries against the same fixture -
 * one plain, one WITH USER_MODE - for the same restricted user. If the counts
 * differ, the precedence law holds and the analyzer must NOT flag PS501 on the
 * WITH USER_MODE query just because the class is declared `without sharing`.
 */
@isTest
private class BlastRadius_E3_Test {

    // Same class, two operation modes. `without sharing` at class level.
    private without sharing class MixedReader {
        public Integer countSystemMode() {
            return [SELECT COUNT() FROM Blast_Test__c];
        }
        public Integer countUserMode() {
            return [SELECT COUNT() FROM Blast_Test__c WITH USER_MODE];
        }
    }

    private static User buildMinimalUser() {
        Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
        String suffix = String.valueOf(System.now().getTime());
        return new User(
            FirstName = 'Blast',
            LastName = 'Precedence',
            Email = 'blast.precedence@example.com',
            Username = 'blast.precedence.' + suffix + '@blastradius.example.com',
            Alias = 'blastp',
            ProfileId = p.Id,
            TimeZoneSidKey = 'Europe/Berlin',
            LocaleSidKey = 'en_US',
            EmailEncodingKey = 'UTF-8',
            LanguageLocaleKey = 'en_US'
        );
    }

    @isTest
    static void user_mode_overrides_without_sharing() {
        User minU;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            minU = buildMinimalUser();
            insert minU;

            // Grant object + field read so the USER_MODE query is not blocked by
            // CRUD - isolating the result to the record-level sharing decision.
            PermissionSet ps = new PermissionSet(Name = 'BlastR_E3_Read', Label = 'BlastR E3 Read');
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

        Integer sysCount;
        Integer userCount;
        System.runAs(minU) {
            MixedReader r = new MixedReader();
            sysCount = r.countSystemMode();
            userCount = r.countUserMode();
        }

        // Same class, same user, same records: only the mode clause differs.
        System.assertEquals(5, sysCount, 'plain query in a without sharing class reads all 5 (system mode)');
        System.assertEquals(0, userCount, 'WITH USER_MODE overrides without sharing -> 0; analyzer must NOT flag PS501 here');
    }
}
