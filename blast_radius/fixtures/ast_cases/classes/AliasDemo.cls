public without sharing class AliasDemo {
    public class Response { @InvocableVariable public String summary; }
    @InvocableMethod
    public static List<Response> run() {
        List<Response> out = new List<Response>();
        List<HealthRecord__c> recs = [SELECT Diagnosis__c FROM HealthRecord__c];
        String d = recs[0].Diagnosis__c;
        Response r = new Response();
        r.summary = d;
        out.add(r);
        return out;
    }
}
