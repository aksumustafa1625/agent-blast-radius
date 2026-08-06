/**
 * The v58 half of the E15/E16 matched pair. Byte-identical in body to
 * ShareProbeTrigger; it exists only so both API versions can be live at once and
 * asserted in the SAME execution, which a single file cannot do - a trigger carries
 * exactly one apiVersion.
 *
 * Hosted on HealthRecord__c rather than Casc_Parent__c for the same reason. What is
 * held identical is everything that could explain a difference in the READING: the
 * queried object, its rows, the running user's permissions on it, and both queries.
 * The host object cannot change what a SELECT against Blast_Test__c returns.
 */
trigger ShareProbeV58Trigger on HealthRecord__c (before insert) {
    Integer plainRows = [SELECT COUNT() FROM Blast_Test__c];
    Integer sysRows   = [SELECT COUNT() FROM Blast_Test__c WITH SYSTEM_MODE];
    Trigger.new[0].addError('PLAIN=' + plainRows + ' SYS=' + sysRows);
}
