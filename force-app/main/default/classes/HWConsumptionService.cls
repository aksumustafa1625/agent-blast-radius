/**
 * HWConsumptionService — computes a customer's electricity consumption anomaly
 * (latest period vs trailing average) from unified meter-reading data.
 *
 * The same figure is grounded in Data 360 (validated via scripts/datacloud_ci_anomaly.sql
 * over the Meter Reading DLO — Lena = 520 kWh vs 316 avg = +64.6%). This service reads the
 * readings (present in both the Salesforce core and Data 360) so the agent gets a correct,
 * testable, credit-free number. Production can swap the source to the Data 360 Query API
 * (scripts/datacloud_query.ps1) or a Data Cloud retriever without changing the contract.
 *
 * Standard (ADR-006): with sharing, SOQL WITH USER_MODE, bulk-safe, no DML-in-loop.
 */
public with sharing class HWConsumptionService {

    /** The grounded consumption figures for one customer. */
    public class Anomaly {
        public Decimal latestKwh;
        public Decimal averageKwh;     // trailing average of prior readings
        public Decimal anomalyPercent; // (latest - avg) / avg * 100
        public Integer readingCount;
        public String  explanation;    // a draft, human-readable grounding the agent can use
    }

    /**
     * Bulk-safe: one query for all accounts, anomaly computed per account.
     * @param accountIds the customer Account ids
     * @return map of accountId -> Anomaly (only accounts with at least one reading)
     */
    public static Map<Id, Anomaly> anomaliesByAccount(Set<Id> accountIds) {
        Map<Id, List<Decimal>> kwhByAccount = new Map<Id, List<Decimal>>();
        if (accountIds == null || accountIds.isEmpty()) {
            return new Map<Id, Anomaly>();
        }
        // Newest reading first per account so index 0 = latest period.
        // NOTE: uses Database.queryWithBinds (explicit bind map) rather than an inline
        // `:accountIds` bind. When this class is invoked from the Agentforce action runtime
        // the platform cannot resolve inline SOQL bind variables against the Apex stack frame
        // and throws `System.QueryException: Variable does not exist: tmpVar1`. An explicit
        // bind map resolves correctly in that context while preserving USER_MODE (ADR-006).
        String query =
            'SELECT kWh__c, Read_Date__c, Meter__r.Account__c ' +
            'FROM Meter_Reading__c ' +
            'WHERE Meter__r.Account__c IN :accIds AND kWh__c != null ' +
            'ORDER BY Meter__r.Account__c, Read_Date__c DESC';
        Map<String, Object> binds = new Map<String, Object>{ 'accIds' => accountIds };
        for (Meter_Reading__c r : (List<Meter_Reading__c>) Database.queryWithBinds(query, binds, AccessLevel.USER_MODE)) {
            Id acc = r.Meter__r.Account__c;
            if (!kwhByAccount.containsKey(acc)) {
                kwhByAccount.put(acc, new List<Decimal>());
            }
            kwhByAccount.get(acc).add(r.kWh__c);
        }
        Map<Id, Anomaly> out = new Map<Id, Anomaly>();
        for (Id acc : kwhByAccount.keySet()) {
            out.put(acc, fromReadings(kwhByAccount.get(acc)));
        }
        return out;
    }

    /** Compute the anomaly from a newest-first list of kWh readings. */
    @TestVisible
    private static Anomaly fromReadings(List<Decimal> readingsNewestFirst) {
        Anomaly a = new Anomaly();
        a.readingCount = readingsNewestFirst.size();
        if (readingsNewestFirst.isEmpty()) {
            a.explanation = 'No consumption data available for this customer.';
            return a;
        }
        a.latestKwh = readingsNewestFirst[0];
        if (readingsNewestFirst.size() == 1) {
            a.averageKwh = a.latestKwh;
            a.anomalyPercent = 0;
            a.explanation = 'Only one reading available (' + a.latestKwh
                + ' kWh); not enough history to detect a trend yet.';
            return a;
        }
        Decimal sumPrior = 0;
        for (Integer i = 1; i < readingsNewestFirst.size(); i++) {
            sumPrior += readingsNewestFirst[i];
        }
        a.averageKwh = (sumPrior / (readingsNewestFirst.size() - 1)).setScale(1);
        a.anomalyPercent = (a.averageKwh == 0) ? 0
            : ((a.latestKwh - a.averageKwh) / a.averageKwh * 100).setScale(1);
        a.explanation = buildExplanation(a);
        return a;
    }

    private static String buildExplanation(Anomaly a) {
        if (a.anomalyPercent >= 30) {
            return 'Your latest usage was ' + a.latestKwh + ' kWh — ' + a.anomalyPercent
                + '% above your ' + a.averageKwh + ' kWh trailing average. The increase is '
                + 'recent and pronounced, consistent with a new high-draw appliance such as an '
                + 'EV charger or heat pump.';
        }
        if (a.anomalyPercent <= -30) {
            return 'Your latest usage was ' + a.latestKwh + ' kWh — ' + a.anomalyPercent.abs()
                + '% below your ' + a.averageKwh + ' kWh trailing average.';
        }
        return 'Your latest usage was ' + a.latestKwh + ' kWh, in line with your '
            + a.averageKwh + ' kWh trailing average (' + a.anomalyPercent + '%).';
    }
}