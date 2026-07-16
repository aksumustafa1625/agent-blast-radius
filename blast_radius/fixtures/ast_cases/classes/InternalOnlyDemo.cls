public without sharing class InternalOnlyDemo {
    public class Response { @InvocableVariable public String summary; }
    @InvocableMethod
    public static List<Response> run() {
        List<Response> out = new List<Response>();
        List<HealthRecord__c> recs = [SELECT Patient_Name__c, Diagnosis__c FROM HealthRecord__c];
        Response r = new Response();
        if (recs[0].Diagnosis__c == 'Diabetes') {
            r.summary = recs[0].Patient_Name__c;
        }
        out.add(r);
        return out;
    }
}
