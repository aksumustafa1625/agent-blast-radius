/**
 * E2 fixture: EXPLICIT without sharing, plain SOQL (no mode clause), API v58.
 * Isolates the apiVersion effect on the database-operation default mode while
 * holding record-level sharing fixed (explicitly bypassed).
 */
public without sharing class BlastRadius_E2_ReaderV58 {
    public Integer countRecords() {
        return [SELECT COUNT() FROM Blast_Test__c];
    }
}
