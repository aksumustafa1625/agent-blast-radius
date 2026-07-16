/* Agent Blast Radius - experiment E10: the CONTROL for BlastRadius_E10_NoDecl.
 *
 * Identical invocable, identical apiVersion, one difference: it declares `with
 * sharing`. If this one also returned every row, the experiment would prove nothing
 * about declarations - it would just mean the fixture user can see everything. A
 * measurement without a control that can fail is not a measurement.
 */
public with sharing class BlastRadius_E10_WithSharing {

    public class Result {
        @InvocableVariable
        public Integer visible;
    }

    @InvocableMethod(label='BR E10 WithSharing Read' description='Counts Blast_Test__c rows visible to the caller.')
    public static List<Result> read(List<String> ignored) {
        Result r = new Result();
        r.visible = [SELECT COUNT() FROM Blast_Test__c];
        return new List<Result>{ r };
    }
}
