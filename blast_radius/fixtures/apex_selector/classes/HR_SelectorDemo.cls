public without sharing class HR_SelectorDemo {
    public List<String> getIbans() {
        List<String> out = new List<String>();
        for (Blast_Test__c r : [SELECT Customer_IBAN__c FROM Blast_Test__c]) {
            out.add(HR_HelperDemo.mask(r.Customer_IBAN__c));
        }
        return out;
    }
}
