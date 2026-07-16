/* Agent Blast Radius - experiment E10: the entry-point matrix, the ONE cell that
 * matters for an agent.
 *
 * THE QUESTION
 *     A class with NO sharing declaration inherits its CALLER's sharing context, so
 *     its record axis is genuinely undetermined from source alone - which is why
 *     apex_introspect reports enforces_sharing=None for it at pre-v67, and why E2
 *     established "no declaration" != "without sharing".
 *
 *     But undetermined-in-general is not undetermined-here. E2 measured exactly one
 *     entry point: an Apex TEST class calling the reader (v58 -> 0 records, i.e.
 *     sharing enforced). An agent does not call Apex that way. It invokes an
 *     @InvocableMethod, where there IS no calling Apex class - the invocable is the
 *     top of the stack. The matrix's other cells (LWC, REST, anonymous) are real but
 *     irrelevant to an agent's blast radius; this one is the agent's actual path.
 *
 * WHY IT MATTERS
 *     If a no-declaration invocable runs WITHOUT sharing because it is the entry
 *     point, then for the agent path a pre-v67 declaration-less class is a PROVEN
 *     record-scope bypass, not an honest unknown - PS501 evidence we are currently
 *     leaving on the table. If it enforces sharing instead, None stays right.
 *     Either answer improves the tool; only guessing does not.
 *
 * This class deliberately carries NO sharing declaration. Do not add one.
 */
public class BlastRadius_E10_NoDecl {

    public class Result {
        @InvocableVariable
        public Integer visible;
    }

    @InvocableMethod(label='BR E10 NoDecl Read' description='Counts Blast_Test__c rows visible to the caller.')
    public static List<Result> read(List<String> ignored) {
        Result r = new Result();
        r.visible = [SELECT COUNT() FROM Blast_Test__c];
        return new List<Result>{ r };
    }
}
