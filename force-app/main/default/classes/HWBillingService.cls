/**
 * HWBillingService — returns a customer's most recent energy bill (amount, period, usage,
 * status). The agent uses this for "what's my latest bill / how much do I owe?" so it quotes
 * the real figure from the billing record, never an invented number.
 *
 * Energy_Bill__c is HanseWatt's local projection of the (simulated) SAP IS-U billing system —
 * the honest-demo boundary: the Salesforce read path is real, the upstream system is mocked.
 *
 * Standard (ADR-006): with sharing, SOQL USER_MODE via Database.queryWithBinds (an inline
 * bind throws "Variable does not exist: tmpVar1" in the Agentforce action runtime), bulk-safe.
 */
public with sharing class HWBillingService {

    /** One customer's latest bill. */
    public class Bill {
        public String  billNumber;
        public Date    periodStart;
        public Date    periodEnd;
        public Decimal amount;
        public String  currencyCode;
        public Decimal consumptionKwh;
        public String  status;
    }

    /**
     * Bulk-safe: latest bill per account (by period end).
     * @param accountIds the customer Account ids
     * @return map of accountId -> latest Bill (only accounts that have at least one bill)
     */
    public static Map<Id, Bill> latestByAccount(Set<Id> accountIds) {
        Map<Id, Bill> out = new Map<Id, Bill>();
        if (accountIds == null || accountIds.isEmpty()) {
            return out;
        }
        String query =
            'SELECT Account__c, Name, Period_Start__c, Period_End__c, Amount__c, ' +
            'CurrencyIsoCode, Consumption_kWh__c, Status__c ' +
            'FROM Energy_Bill__c ' +
            'WHERE Account__c IN :accs ' +
            'ORDER BY Account__c, Period_End__c DESC';
        Map<String, Object> binds = new Map<String, Object>{ 'accs' => accountIds };
        for (Energy_Bill__c b : (List<Energy_Bill__c>) Database.queryWithBinds(query, binds, AccessLevel.USER_MODE)) {
            if (out.containsKey(b.Account__c)) {
                continue; // ORDER BY ... DESC => the first row per account is the latest
            }
            Bill bill = new Bill();
            bill.billNumber     = b.Name;
            bill.periodStart    = b.Period_Start__c;
            bill.periodEnd      = b.Period_End__c;
            bill.amount         = b.Amount__c;
            bill.currencyCode   = (String) b.get('CurrencyIsoCode');
            bill.consumptionKwh = b.Consumption_kWh__c;
            bill.status         = b.Status__c;
            out.put(b.Account__c, bill);
        }
        return out;
    }
}