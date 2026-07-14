/**
 * E2 fixture: identical body to the v58 reader, EXPLICIT without sharing,
 * plain SOQL (no mode clause), API v67. Tests whether Summer '26's
 * user-mode-by-default for database operations overrides an explicit
 * without sharing declaration.
 */
public without sharing class BlastRadius_E2_ReaderV67 {
    public Integer countRecords() {
        return [SELECT COUNT() FROM Blast_Test__c];
    }
}
