public without sharing class B { void m(){ List<List<SObject>> r = [FIND :q IN ALL FIELDS RETURNING Sharing_Test__c(Customer_IBAN__c)]; } }
