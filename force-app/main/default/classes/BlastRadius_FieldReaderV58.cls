/**
 * E2b FLS-axis reader: without sharing, API v58. Selects a field the running
 * user has no FLS on, to isolate whether FLS is enforced (independent of
 * record sharing - the caller ensures record access via ownership).
 */
public without sharing class BlastRadius_FieldReaderV58 {
    public String readIban() {
        try {
            List<Blast_Test__c> r = [SELECT Customer_IBAN__c FROM Blast_Test__c LIMIT 1];
            if (r.isEmpty()) return 'NO_ROWS';
            return 'READ=' + r[0].Customer_IBAN__c;
        } catch (Exception e) {
            String m = e.getMessage();
            return 'BLOCKED=' + (m.length() > 60 ? m.substring(0, 60) : m);
        }
    }
}
