/**
 * Agent Blast Radius - Milestone 0, Experiment E6 (trigger-cascade / PS509).
 *
 * Finding (empirically derived across four runs in this org):
 *   A trigger's plain DML runs in the mode of the TRIGGER's own API version,
 *   independent of the initiating action's access level.
 *     - Legacy trigger (<= v66): plain DML = system mode -> cascade escalates,
 *       writing objects the running user cannot create. Happens even when the
 *       agent action itself is a clean user-mode DML.
 *     - v67 trigger: plain DML = user mode -> cascade is bounded and blocked.
 *
 * These two methods run against the CascParentTrigger deployed at API v58 and
 * assert the escalation for both a user-mode and a system-mode action, proving
 * the action's own cleanliness does not save you from a legacy trigger. (The
 * v67-trigger case that blocks both was verified separately in Milestone 0.)
 */
@isTest
private class BlastRadius_E6_Test {

    private static User buildMinimalUser() {
        Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
        String suffix = String.valueOf(System.now().getTime());
        return new User(
            FirstName = 'Blast',
            LastName = 'Cascade',
            Email = 'blast.cascade@example.com',
            Username = 'blast.cascade.' + suffix + '@blastradius.example.com',
            Alias = 'blastc',
            ProfileId = p.Id,
            TimeZoneSidKey = 'Europe/Berlin',
            LocaleSidKey = 'en_US',
            EmailEncodingKey = 'UTF-8',
            LanguageLocaleKey = 'en_US'
        );
    }

    // Restricted user: CREATE on parent only, nothing on the child object.
    private static User setupRestrictedUser() {
        User minU = buildMinimalUser();
        System.runAs(new User(Id = UserInfo.getUserId())) {
            insert minU;
            PermissionSet ps = new PermissionSet(Name = 'BlastR_E6', Label = 'BlastR E6');
            insert ps;
            insert new ObjectPermissions(
                ParentId = ps.Id,
                SobjectType = 'Casc_Parent__c',
                PermissionsRead = true,
                PermissionsCreate = true
            );
            insert new PermissionSetAssignment(AssigneeId = minU.Id, PermissionSetId = ps.Id);
        }
        return minU;
    }

    // A clean user-mode action still escalates through a legacy (v58) trigger.
    @isTest
    static void legacy_trigger_escalates_user_mode_action() {
        User minU = setupRestrictedUser();

        Boolean parentOk = false;
        String err = '';
        System.runAs(minU) {
            try {
                Database.insert(new Casc_Parent__c(Name = 'um'), AccessLevel.USER_MODE);
                parentOk = true;
            } catch (Exception e) {
                err = e.getMessage();
            }
        }
        Integer childCount = [SELECT COUNT() FROM Casc_Child__c];

        System.assert(parentOk && childCount == 1,
            'legacy trigger must escalate a user-mode action. parentOk=' + parentOk +
            ' childCount=' + childCount + ' err=' + err);
    }

    // A system-mode action likewise escalates through the legacy trigger.
    @isTest
    static void legacy_trigger_escalates_system_mode_action() {
        User minU = setupRestrictedUser();

        Boolean parentOk = false;
        String err = '';
        System.runAs(minU) {
            try {
                Database.insert(new Casc_Parent__c(Name = 'sm'), AccessLevel.SYSTEM_MODE);
                parentOk = true;
            } catch (Exception e) {
                err = e.getMessage();
            }
        }
        Integer childCount = [SELECT COUNT() FROM Casc_Child__c];

        System.assert(parentOk && childCount == 1,
            'legacy trigger must escalate a system-mode action. parentOk=' + parentOk +
            ' childCount=' + childCount + ' err=' + err);
    }
}
