/**
 * Agentforce action for the Agent Blast Radius live demo.
 *
 * Deliberately escalating: `without sharing` at API v58, plain SOQL that reads
 * the GDPR/HIPAA-classified Diagnosis__c and returns it to the agent (the model).
 * The agent's running user is not granted FLS on Diagnosis__c, so this surfaces
 * a field the user cannot see - exactly what the tool should flag (PS506).
 */
public without sharing class GetHealthRecordSummary {

    public class Request {
        @InvocableVariable(required=true label='Patient name')
        public String patientName;
    }

    public class Response {
        @InvocableVariable(label='Summary')
        public String summary;
    }

    @InvocableMethod(label='Get Health Record Summary'
                     description='Returns a short summary of a patient health record')
    public static List<Response> run(List<Request> requests) {
        List<Response> results = new List<Response>();
        for (Request req : requests) {
            List<HealthRecord__c> recs = [
                SELECT Patient_Name__c, Diagnosis__c
                FROM HealthRecord__c
                WHERE Patient_Name__c = :req.patientName
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
