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

    /* THE CONTROL THIS TEST ORIGINALLY LACKED - added 2026-08-04 after a verified
     * external brief re-asserted the Summer '26 claim as CONFIRMED against primary
     * sources, which sent us back to our own evidence.
     *
     * The first version caught a bare Exception, discarded the message, and read
     * "something threw and no child rows exist" as "the trigger ran in user mode".
     * Two different worlds produce that same observation:
     *     (a) parent inserted -> trigger ran in user mode -> child write denied ->
     *         the throw rolls the parent back too
     *     (b) the PARENT insert failed on its own -> the trigger never ran at all
     * With no parent count and no error message, the test could not tell them apart -
     * the exact absence of a control this project writes controls to avoid, found in
     * its own evidence.
     *
     * MEASURED 2026-08-04, org ORG-LAB-A, Summer '26. The org's verbatim answer:
     *     DmlException: CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY,
     *       BlastTestV67Trigger: execution of AfterInsert
     *       caused by: System.SecurityException: Access to entity 'Casc_Child__c' denied
     *       Trigger.BlastTestV67Trigger: line 24
     * The error names the CHILD entity and the TRIGGER's own line, so the parent
     * insert did reach the trigger and the trigger's DML is what the platform denied.
     * E6 stands, and now it stands on evidence rather than on a docstring.
     *
     * SCOPE OF THE CLAIM - do not widen it: this measures the CRUD axis of DML the
     * trigger's OWN body performs. Whether a v67 trigger enforces sharing or FLS is
     * NOT measured here.
     */
    @isTest
    static void v67_trigger_dml_is_bounded_by_the_running_user() {
        User usr = userWithoutChildCreate();
        String errMsg = '';
        System.runAs(usr) {
            try {
                insert new Blast_Test__c(Name = 'e13');
            } catch (Exception e) {
                errMsg = e.getMessage();
            }
        }
        // Counted as the admin: the user can read neither table, so asking them would
        // confuse "no rows" with "cannot see rows" - the mistake E4 named.
        Integer parents = [SELECT COUNT() FROM Blast_Test__c WHERE Name = 'e13'];
        Integer kids    = [SELECT COUNT() FROM Casc_Child__c WHERE Name = 'e13-e13'];

        // 1. The child write must not have landed.
        System.assertEquals(0, kids,
            'A v67 TRIGGER WROTE A ROW THE RUNNING USER CANNOT. The Summer \'26 note '
            + 'is then right - triggers always run in system mode - and PS509 is a '
            + 'FALSE NEGATIVE for every v67 trigger. Fix PS509 before trusting any '
            + 'clean report. Rows written: ' + kids);

        // 2. THE CONTROL. An after-insert trigger that throws rolls the parent back,
        //    so parents=0 is what "the trigger ran and was denied" looks like. If the
        //    parent had landed while the child did not, the trigger never fired and
        //    this test would be measuring nothing.
        System.assertEquals(0, parents,
            'The parent survived while the child did not, so the cascade never ran and '
            + 'this test proves nothing about trigger execution mode. Parents: ' + parents);

        // 3. THE DISCRIMINATOR. Without this, a parent-side failure would pass 1 and 2
        //    and be misread as user-mode enforcement.
        System.assert(errMsg.contains('Casc_Child__c'),
            'The transaction rolled back for a reason that does not name the CHILD '
            + 'entity, so whatever was denied, it was not the trigger\'s own DML. '
            + 'The org said: ' + errMsg);
        System.assert(errMsg.contains('BlastTestV67Trigger'),
            'The error does not name the trigger, so the parent insert may have failed '
            + 'before the cascade ran. The org said: ' + errMsg);
    }
}
