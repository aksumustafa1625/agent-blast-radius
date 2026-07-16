/**
 * E2b FLS-axis reader: without sharing, API v67. Identical body to the v58
 * reader; only the API version differs, isolating the v67 default's effect on
 * FLS enforcement under an explicit `without sharing` declaration.
 */
public without sharing class BlastRadius_FieldReaderV67 {
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
