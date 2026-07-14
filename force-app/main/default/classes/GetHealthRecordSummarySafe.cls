/**
 * Safe counterpart for the demo: with sharing + WITH USER_MODE at API v67.
 * The runtime enforces the running user's CRUD/FLS/sharing, so this action
 * cannot exceed its user. The tool should report it clean (no escalation).
 */
public with sharing class GetHealthRecordSummarySafe {

    public class Request {
        @InvocableVariable(required=true label='Patient name')
        public String patientName;
    }

    public class Response {
        @InvocableVariable(label='Summary')
        public String summary;
    }

    @InvocableMethod(label='Get Health Record Summary (Safe)'
                     description='User-mode summary of a patient health record')
    public static List<Response> run(List<Request> requests) {
        List<Response> results = new List<Response>();
        for (Request req : requests) {
            List<HealthRecord__c> recs = [
                SELECT Patient_Name__c, Diagnosis__c
                FROM HealthRecord__c
                WHERE Patient_Name__c = :req.patientName
                WITH USER_MODE
                LIMIT 1
            ];
            Response r = new Response();
            r.summary = recs.isEmpty()
                ? 'No record found.'
                : recs[0].Patient_Name__c + ' - ' + recs[0].Diagnosis__c;
            results.add(r);
        }
        return results;
    }
}
