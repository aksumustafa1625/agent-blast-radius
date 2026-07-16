/* Agent Blast Radius - experiment E13: does a v67 trigger still run in system mode?
 *
 * WHY THIS EXISTS, and why it is the dangerous kind of question
 *     An external review cited Summer '26 release notes: "Apex Triggers are an
 *     exception as these will now always run in system mode across all API versions."
 *     If that is true, PS509 is WRONG in the worst direction: it fires only when the
 *     trigger's apiVersion is < 67, so a v67 trigger produces NOTHING - a false
 *     negative sitting in the middle of this tool's own thesis. A tool that misses a
 *     real escalation is worse than no tool.
 *
 *     E6 measured the opposite - a trigger's DML runs in the mode of the TRIGGER's own
 *     apiVersion - but E6's v67 half was "verified separately in Milestone 0": an
 *     assertion in a docstring, with no test that would catch the platform changing
 *     underneath it. That is exactly the shape E10 was written to correct, and this
 *     review found the same shape again.
 *
 * THE SHAPE
 *     BlastTestV67Trigger is at apiVersion 67 and writes Casc_Child__c on insert of a
 *     Blast_Test__c. The running user is granted Create on Blast_Test__c and nothing
 *     at all on Casc_Child__c. So inserting the parent as that user asks the platform
 *     one question and gives it nowhere to hide:
 *         the child write LANDS  -> the trigger ran in SYSTEM mode despite v67
 *                                   -> PS509 is a false negative, the reviewer is right
 *         the child write BLOCKS -> the trigger honoured v67's user-mode default
 *                                   -> E6 stands
 *     Whichever it is, it is recorded here rather than in a docstring.
 */
@isTest
private class BlastRadius_E13_TriggerMode {

    private static User userWithoutChildCreate() {
        User usr;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
            usr = new User(FirstName = 'E13', LastName = 'Trigger',
                Email = 'e13.trigger@example.com',
                Username = 'e13.trigger.' + System.now().getTime() + '@blastradius.example.com',
                Alias = 'e13t', ProfileId = p.Id, TimeZoneSidKey = 'Europe/Berlin',
                LocaleSidKey = 'en_US', EmailEncodingKey = 'UTF-8',
                LanguageLocaleKey = 'en_US');
            insert usr;
            PermissionSet ps = new PermissionSet(Name = 'BR_E13', Label = 'BR E13');
            insert ps;
            // Create on the PARENT only. Nothing whatsoever on Casc_Child__c - so the
            // cascade's write is the only thing that can put a child row in the table.
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Blast_Test__c',
                PermissionsRead = true, PermissionsCreate = true);
            insert new PermissionSetAssignment(AssigneeId = usr.Id, PermissionSetId = ps.Id);
        }
        return usr;
    }

    @isTest
    static void v67_trigger_dml_is_bounded_by_the_running_user() {
        User usr = userWithoutChildCreate();
        String outcome;
        System.runAs(usr) {
            try {
                insert new Blast_Test__c(Name = 'e13');
                outcome = 'CASCADE_LANDED';
            } catch (Exception e) {
                outcome = 'CASCADE_BLOCKED';
            }
        }
        // Counted as the admin: the user cannot read Casc_Child__c either, so asking
        // them would confuse "no rows" with "cannot see rows" - the mistake E4 named.
        Integer kids = [SELECT COUNT() FROM Casc_Child__c WHERE Name = 'e13-e13'];

        System.assertEquals('CASCADE_BLOCKED', outcome,
            'A v67 TRIGGER PERFORMED DML THE RUNNING USER CANNOT. If this fails, the '
            + 'Summer \'26 note is right - triggers always run in system mode - and '
            + 'PS509 is a FALSE NEGATIVE for every v67 trigger. Fix PS509 before '
            + 'trusting any clean report. The org said: ' + outcome);
        System.assertEquals(0, kids,
            'The child row exists, so the cascade wrote it regardless of what the '
            + 'insert reported. Rows written: ' + kids);
    }
}
