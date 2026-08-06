/* Agent Blast Radius - E15/E16: the record axis inside a trigger body, both halves.
 *
 * WHY IT EXISTS
 *     E13 measured the object-CRUD axis of DML a trigger's own body performs and said
 *     plainly that sharing and FLS were NOT measured. A Stack Exchange thread then
 *     produced three positions that could not all be right:
 *
 *       v67 Apex Developer Guide: user mode "effectively enforces a with sharing
 *           context in the trigger body"                              -> BOUNDED
 *       A commenter (Phil W): v67 rectified edge cases, so triggers are "now always
 *           effectively without sharing"                              -> UNBOUNDED
 *       Another commenter: measured bounded SOQL in a v67 trigger, in their own org
 *
 *     The third is a report to us, not a measurement by us. So this measures it, and
 *     the answer is that the first two are BOTH right about different things.
 *
 * WHAT THE TWO NUMBERS SEPARATE - this is the whole design
 *     PLAIN  a SOQL with no mode clause. At v67 the operation defaults to user mode,
 *            so this reads the OPERATION's mode.
 *     SYS    the same SOQL WITH SYSTEM_MODE. The operation's mode is now pinned, so by
 *            the precedence law the record axis falls to the trigger's AMBIENT SHARING
 *            CONTEXT. It is the only way to observe that context at v67 at all, because
 *            a plain read there is user mode and overrides it.
 *
 * MEASURED 2026-08-05, org ORG-LAB-A, Summer '26
 *
 *     trigger v58 :  PLAIN=5  SYS=5     from all three callers
 *     trigger v67 :  PLAIN=0  SYS=5     from all three callers
 *
 *     PLAIN 5 -> 0 : a plain read in a v67 trigger body IS bounded by the running user.
 *     SYS staying 5: the ambient context is still WITHOUT sharing at v67. It did not
 *                    change - the operation's user-mode default overrides it.
 *
 *     So the guide's sentence is confirmed in both of its halves, in one experiment:
 *     "Triggers always run implicitly in a without sharing context" (SYS=5) "However,
 *     database operations within trigger bodies... run in user mode... User mode
 *     overrides the trigger's without sharing context" (PLAIN=0).
 *
 * AND THE CALLER DOES NOT MATTER
 *     Three callers - direct, a `with sharing` class, a `without sharing` class - give
 *     identical readings at BOTH versions. The trigger body does not inherit its
 *     caller's sharing declaration. That refutes the edge-case claim in the form an
 *     Apex caller can express it, and ONLY in that form: Phil W said "certain
 *     automation contexts", and Flow, Process Builder, platform-event subscribers,
 *     Aura/LWC controllers and guest-user contexts are NOT tested here.
 *
 * WHAT ISOLATES SHARING
 *     Blast_Test__c is Private OWD with rows seeded by the ADMIN. The probe user holds
 *     object READ on it and owns none of those rows. CRUD cannot be what hides them -
 *     the v58 half returns 5 with the identical permission set. FLS cannot either -
 *     COUNT() touches no field. Sharing is the only remaining explanation for a zero.
 *
 * THE CONTROL IS LOAD-BEARING
 *     If the v58 half ever returns 0, the permission set failed silently or the seed
 *     did not land, and both halves would read 0 while measuring nothing - which is
 *     exactly what an empty muting set did to E9's first draft. A zero at v67 means
 *     something only once the v58 half has shown the query CAN see those rows.
 */
@isTest
private class BlastRadius_E15_TriggerSharing {

    private static User probeUser() {
        User usr;
        System.runAs(new User(Id = UserInfo.getUserId())) {
            Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
            usr = new User(FirstName = 'E15', LastName = 'Share',
                Email = 'e15.share@example.com',
                Username = 'e15.share.' + System.now().getTime() + '@blastradius.example.com',
                Alias = 'e15s', ProfileId = p.Id, TimeZoneSidKey = 'Europe/Berlin',
                LocaleSidKey = 'en_US', EmailEncodingKey = 'UTF-8',
                LanguageLocaleKey = 'en_US');
            insert usr;
            PermissionSet ps = new PermissionSet(Name = 'BR_E15', Label = 'BR E15');
            insert ps;
            // Read on the Private object, and deliberately NO create: this user must
            // not own the rows, or ownership would satisfy the record axis and the
            // probe would measure nothing.
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Blast_Test__c',
                PermissionsRead = true);
            // Create on both trigger hosts, so each half of the pair can fire.
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Casc_Parent__c',
                PermissionsRead = true, PermissionsCreate = true);
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'HealthRecord__c',
                PermissionsRead = true, PermissionsCreate = true);
            insert new PermissionSetAssignment(AssigneeId = usr.Id, PermissionSetId = ps.Id);
        }
        return usr;
    }

    /* Pull just the probe's reading out of the DmlException wrapper. Returns the raw
     * text when the marker is absent, because losing the evidence to a tidy parser is
     * how a probe stops being one. */
    private static String reading(String raw) {
        if (raw == null) return '(null)';
        Integer i = raw.indexOf('PLAIN=');
        if (i < 0) return raw;
        Integer j = raw.indexOf(':', i);
        return (j > i) ? raw.substring(i, j).trim() : raw.substring(i).trim();
    }

    @isTest
    static void trigger_body_record_axis_v58_vs_v67() {
        List<Blast_Test__c> seed = new List<Blast_Test__c>();
        for (Integer i = 0; i < 5; i++) {
            seed.add(new Blast_Test__c(Name = 'e15-' + i));
        }
        insert seed;                                    // owned by the admin
        Integer asAdmin = [SELECT COUNT() FROM Blast_Test__c];

        User usr = probeUser();
        String v67Direct = '', v67FromWith = '', v67FromWithout = '', v58Direct = '';
        System.runAs(usr) {
            try { insert new Casc_Parent__c(Name = 'e15-direct'); }
            catch (Exception e) { v67Direct = reading(e.getMessage()); }

            try { E16WithSharingCaller.fire(); }
            catch (Exception e) { v67FromWith = reading(e.getMessage()); }

            try { E16WithoutSharingCaller.fire(); }
            catch (Exception e) { v67FromWithout = reading(e.getMessage()); }

            try { insert new HealthRecord__c(Name = 'e15-v58'); }
            catch (Exception e) { v58Direct = reading(e.getMessage()); }
        }
        String all = 'admin=' + asAdmin + ' | v67 direct[' + v67Direct + '] fromWith['
            + v67FromWith + '] fromWithout[' + v67FromWithout + '] | v58[' + v58Direct + ']';

        // Every path must actually have reported, or nothing below means anything.
        System.assert(v67Direct.startsWith('PLAIN=') && v58Direct.startsWith('PLAIN='),
            'A probe path never reported. ' + all);

        // THE CONTROL. If this ever reads 0 the fixture is broken, not the platform,
        // and every other assertion here would pass while measuring nothing.
        System.assertEquals('PLAIN=5 SYS=5', v58Direct,
            'The v58 control no longer bypasses sharing. Either the seed did not land, '
            + 'the permission set failed silently, or pre-v67 trigger semantics changed. '
            + 'Nothing else in this test is trustworthy until this is 5. ' + all);

        // A plain read in a v67 trigger body is BOUNDED by the running user...
        System.assert(v67Direct.startsWith('PLAIN=0'),
            'A v67 trigger body read rows the running user cannot see. The guide says '
            + 'user mode overrides the trigger context; if this fires, it does not. ' + all);

        // ...while the AMBIENT context underneath is still WITHOUT sharing.
        System.assert(v67Direct.endsWith('SYS=5'),
            'WITH SYSTEM_MODE inside a v67 trigger no longer bypasses sharing, so the '
            + 'ambient context is no longer without-sharing. That would contradict both '
            + 'the guide and the measurement this test was written from. ' + all);

        // The caller's own declaration changes nothing, at either version.
        System.assertEquals(v67Direct, v67FromWith,
            'A `with sharing` caller changed what the trigger body saw, so the body '
            + 'inherits its caller. ' + all);
        System.assertEquals(v67Direct, v67FromWithout,
            'A `without sharing` caller changed what the trigger body saw. ' + all);
    }
}
