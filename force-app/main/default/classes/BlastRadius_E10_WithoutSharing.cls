/* Agent Blast Radius - experiment E10: the POSITIVE control.
 *
 * `with sharing` returning 0 only proves the read was filtered IF an unfiltered read
 * can return rows for this same user. Without this arm, a silently failed permission
 * assignment would give 0 everywhere and the experiment would pass while measuring
 * nothing - the same vacuous green that an empty muting set produced in E9. This one
 * must return every row, or the fixture is broken and the comparison is void.
 */
public without sharing class BlastRadius_E10_WithoutSharing {

    public class Result {
        @InvocableVariable
        public Integer visible;
    }

    @InvocableMethod(label='BR E10 WithoutSharing Read' description='Counts Blast_Test__c rows visible to the caller.')
    public static List<Result> read(List<String> ignored) {
        Result r = new Result();
        r.visible = [SELECT COUNT() FROM Blast_Test__c];
        return new List<Result>{ r };
    }
}
