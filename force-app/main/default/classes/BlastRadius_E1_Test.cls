/**
 * Agent Blast Radius - Milestone 0, Experiment E1 (mechanism proof).
 *
 * Demonstrates, with a controlled fixture, that the execution mode of Apex -
 * not the running user's permissions - decides what an agent action can read.
 * Two independent scenarios isolate the two layers the thesis depends on.
 *
 * No real org users or data are touched: the test builds its own minimal user
 * and its own Private object, then compares system-mode vs user-mode reads.
 */
@isTest
private class BlastRadius_E1_Test {

    // Reads in system context: ignores the running user's CRUD/FLS and sharing.
    private without sharing class SystemModeReader {
        public Integer countRecords() {
            return [SELECT COUNT() FROM Blast_Test__c];
        }
    }

    // Reads in user context: honors the running user's CRUD/FLS and sharing.
    private with sharing class UserModeReader {
        public Integer countRecords() {
            return [SELECT COUNT() FROM Blast_Test__c WITH USER_MODE];
        }
    }

    private static User buildMinimalUser() {
        Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
        String suffix = String.valueOf(System.now().getTime());
        return new User(
            FirstName = 'Blast',
            LastName = 'Restricted',
            Email = 'blast.restricted@example.com',
            Username = 'blast.restricted.' + suffix + '@blastradius.example.com',
            Alias = 'blastr',
            ProfileId = p.Id,
            TimeZoneSidKey = 'Europe/Berlin',
            LocaleSidKey = 'en_US',
            EmailEncodingKey = 'UTF-8',
            LanguageLocaleKey = 'en_US'
        );
    }

    private static List<Blast_Test__c> seedFiveRecords() {
        List<Blast_Test__c> recs = new List<Blast_Test__c>();
        for (Integer i = 0; i < 5; i++) {
            recs.add(new Blast_Test__c(Name = 'rec' + i, Secret_Data__c = 'secret' + i));
        }
        insert recs;
        return recs;
    }

    // Scenario A - the running user has NO object permission (CRUD-layer gap).
    @isTest
    static void crud_layer_gap() {
        User minU;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            minU = buildMinimalUser();
            insert minU;
        }

        seedFiveRecords();

        Integer sysCount;
        Integer userCount;
        System.runAs(minU) {
            sysCount = new SystemModeReader().countRecords();
            try {
                userCount = new UserModeReader().countRecords();
            } catch (Exception e) {
                userCount = 0; // access blocked = user sees none
            }
        }

        System.assertEquals(5, sysCount, 'system-mode read must return all 5 records');
        System.assertEquals(0, userCount, 'user-mode read must return 0 (no object permission)');
    }

    // Scenario B - the running user CAN read the object, but records are owned
    // by another user under a Private sharing model (record-level gap, PS501).
    @isTest
    static void sharing_layer_gap() {
        User minU;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            minU = buildMinimalUser();
            insert minU;

            PermissionSet ps = new PermissionSet(Name = 'BlastR_Read', Label = 'BlastR Read');
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

        seedFiveRecords(); // owned by the running (admin) user, not minU

        Integer sysCount;
        Integer userCount;
        System.runAs(minU) {
            sysCount = new SystemModeReader().countRecords();
            try {
                userCount = new UserModeReader().countRecords();
            } catch (Exception e) {
                userCount = -1; // unexpected: object read was granted
            }
        }

        System.assertEquals(5, sysCount, 'system-mode read must return all 5 records');
        System.assertEquals(0, userCount, 'user-mode read must return 0 (Private OWD, not owner)');
    }
}
